import hashlib
import hmac
import logging
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from app.config import settings

BASE_URL = "https://api.pionex.com"
TIME_PATH = "/api/v1/common/timestamp"
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 20
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)
MAX_RETRIES = 2
TEMPORARY_STATUSES = {502, 503, 504}
logger = logging.getLogger("uvicorn.error")


class PionexErrorCode:
    RELAY_UNAVAILABLE = "PIONEX_RELAY_UNAVAILABLE"
    RELAY_TIMEOUT = "PIONEX_RELAY_TIMEOUT"
    AUTH_ERROR = "PIONEX_AUTH_ERROR"
    RATE_LIMIT = "PIONEX_RATE_LIMIT"
    API_ERROR = "PIONEX_API_ERROR"
    PERMISSION_ERROR = "PIONEX_PERMISSION_ERROR"
    TIMESTAMP_ERROR = "PIONEX_TIMESTAMP_ERROR"
    SIGNATURE_ERROR = "PIONEX_SIGNATURE_ERROR"
    IP_RESTRICTED = "PIONEX_IP_RESTRICTED"


ERROR_DETAILS = {
    PionexErrorCode.RELAY_UNAVAILABLE: "Pionex relay недоступен",
    PionexErrorCode.RELAY_TIMEOUT: "Превышено время ожидания Pionex relay",
    PionexErrorCode.AUTH_ERROR: "Ошибка авторизации Pionex",
    PionexErrorCode.RATE_LIMIT: "Превышен лимит запросов Pionex",
    PionexErrorCode.API_ERROR: "Pionex API недоступен",
    PionexErrorCode.PERMISSION_ERROR: "Недостаточно прав Pionex API key",
    PionexErrorCode.TIMESTAMP_ERROR: "Время запроса Pionex рассинхронизировано",
    PionexErrorCode.SIGNATURE_ERROR: "Ошибка подписи Pionex",
    PionexErrorCode.IP_RESTRICTED: "IP relay не разрешён в Pionex",
}


class PionexAPIError(RuntimeError):
    def __init__(self, code: str, *, http_status: int = 502, pionex_code: str | None = None) -> None:
        self.code = code
        self.http_status = http_status
        self.pionex_code = pionex_code
        self.detail = ERROR_DETAILS[code]
        super().__init__(self.detail)


class PionexAdapter:
    exchange = "PIONEX"
    _server_time_offset_ms = 0

    def __init__(self, operation: str, *, require_auth: bool = True) -> None:
        if not settings.pionex_enabled:
            raise PionexAPIError(PionexErrorCode.PERMISSION_ERROR, http_status=503)
        if require_auth and (not settings.pionex_api_key or not settings.pionex_api_secret):
            raise PionexAPIError(PionexErrorCode.AUTH_ERROR, http_status=401)
        self.operation = operation
        self.session = requests.Session()
        self.proxy_url = settings.pionex_proxy_url.strip()
        if self.proxy_url:
            self.session.proxies.update({"http": self.proxy_url, "https": self.proxy_url})

    @staticmethod
    def normalize_position_direction(payload: dict[str, Any]) -> str:
        """Return only an explicit position direction; never infer it from order side or PnL."""
        for field in ("positionSide", "position_side", "posSide"):
            value = str(payload.get(field, "")).strip().upper()
            if value in {"LONG", "SHORT"}:
                return value
        return "UNKNOWN"

    @staticmethod
    def _classify_payload(code: str) -> PionexAPIError:
        normalized = code.upper()
        if normalized == "INVALID_TIMESTAMP":
            return PionexAPIError(PionexErrorCode.TIMESTAMP_ERROR, http_status=401, pionex_code=code)
        if normalized in {"SIGNATURE_LOST", "INVALID_SIGNATURE"}:
            return PionexAPIError(PionexErrorCode.SIGNATURE_ERROR, http_status=401, pionex_code=code)
        if normalized == "IP_NOT_WHITELISTED":
            return PionexAPIError(PionexErrorCode.IP_RESTRICTED, http_status=403, pionex_code=code)
        if normalized in {"APIKEY_LOST", "INVALIE_APIKEY", "INVALID_APIKEY", "APIKEY_EXPIRED"}:
            return PionexAPIError(PionexErrorCode.AUTH_ERROR, http_status=401, pionex_code=code)
        if "PERMISSION" in normalized or "OPERATION_DENIED" in normalized:
            return PionexAPIError(PionexErrorCode.PERMISSION_ERROR, http_status=403, pionex_code=code)
        return PionexAPIError(PionexErrorCode.API_ERROR, pionex_code=code)

    @classmethod
    def _timestamp_ms(cls) -> int:
        return int(time.time() * 1000) + cls._server_time_offset_ms

    @classmethod
    def _update_server_offset(cls, server_timestamp: Any, sent_at_ms: int, received_at_ms: int) -> None:
        try:
            server_ms = int(server_timestamp)
        except (TypeError, ValueError):
            return
        cls._server_time_offset_ms = server_ms - ((sent_at_ms + received_at_ms) // 2)

    def _request(self, path: str, params: dict[str, Any] | None = None, *, private: bool = True) -> dict[str, Any]:
        if not self.proxy_url:
            raise PionexAPIError(PionexErrorCode.RELAY_UNAVAILABLE, http_status=503)
        query = {key: value for key, value in (params or {}).items() if value is not None}
        for attempt in range(MAX_RETRIES + 1):
            request_query = dict(query)
            headers: dict[str, str] = {}
            if private:
                request_query["timestamp"] = self._timestamp_ms()
                # Sign the original api.pionex.com path/query, never the proxy URL.
                canonical_query = "&".join(f"{key}={value}" for key, value in sorted(request_query.items()))
                signature_payload = f"GET{path}?{canonical_query}".encode()
                headers = {
                    "PIONEX-KEY": settings.pionex_api_key,
                    "PIONEX-SIGNATURE": hmac.new(
                        settings.pionex_api_secret.encode(), signature_payload, hashlib.sha256,
                    ).hexdigest(),
                }
            started = time.monotonic()
            sent_at_ms = int(time.time() * 1000)
            try:
                response = self.session.get(
                    f"{BASE_URL}{path}", params=sorted(request_query.items()), headers=headers, timeout=TIMEOUT,
                )
            except requests.Timeout as exc:
                error = PionexAPIError(PionexErrorCode.RELAY_TIMEOUT, http_status=504)
            except requests.RequestException as exc:
                error = PionexAPIError(PionexErrorCode.RELAY_UNAVAILABLE, http_status=503)
            else:
                if response.status_code == 429:
                    raise PionexAPIError(PionexErrorCode.RATE_LIMIT, http_status=429)
                if response.status_code in TEMPORARY_STATUSES:
                    error = PionexAPIError(PionexErrorCode.API_ERROR)
                elif response.status_code in {401, 403}:
                    raise PionexAPIError(PionexErrorCode.AUTH_ERROR, http_status=response.status_code)
                else:
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise PionexAPIError(PionexErrorCode.API_ERROR) from exc
                    self._update_server_offset(payload.get("timestamp"), sent_at_ms, int(time.time() * 1000))
                    if response.status_code >= 400 or not payload.get("result", False):
                        remote_code = str(payload.get("code", ""))
                        error = self._classify_payload(remote_code)
                        logger.error(
                            "operation=%s endpoint=GET %s http_status=%s pionex_code=%s request_id=%s code=%s",
                            self.operation, path, response.status_code, remote_code or "UNKNOWN",
                            response.headers.get("x-request-id", "-"), error.code,
                        )
                        raise error
                    return payload
            elapsed = round((time.monotonic() - started) * 1000)
            if attempt >= MAX_RETRIES:
                logger.error("operation=%s code=%s elapsed_ms=%s exhausted=true", self.operation, error.code, elapsed)
                raise error
            time.sleep(attempt + 1)
        raise AssertionError("unreachable")

    def check_health(self) -> dict[str, Any]:
        started = time.monotonic()
        self._request("/uapi/v1/account/balances")
        return {"latency_ms": round((time.monotonic() - started) * 1000)}

    def iter_history_positions(
        self, start_date: datetime, end_date: datetime, *, position_flag: str = "CLOSED",
    ) -> Iterator[dict[str, Any]]:
        def fetch_window(window_start: datetime, window_end: datetime) -> Iterator[dict[str, Any]]:
            payload = self._request("/uapi/v1/account/historyPositions", {
                "positionFlag": position_flag, "startTime": int(window_start.timestamp() * 1000),
                "endTime": int(window_end.timestamp() * 1000), "limit": 200,
            })
            positions = payload.get("data", {}).get("positions", [])
            # Pionex documents 200 as the maximum page size.  A full page is
            # therefore never complete, even when the API does not expose a
            # cursor for this endpoint; split the time interval until each
            # leaf is strictly below the limit.
            if len(positions) < 200:
                yield from positions
                return
            if window_end - window_start <= timedelta(seconds=1):
                raise PionexAPIError(PionexErrorCode.API_ERROR)
            midpoint = window_start + (window_end - window_start) / 2
            yield from fetch_window(window_start, midpoint)
            yield from fetch_window(midpoint + timedelta(milliseconds=1), window_end)

        current = start_date.astimezone(UTC)
        final = min(end_date.astimezone(UTC), datetime.now(tz=UTC) + timedelta(milliseconds=self._server_time_offset_ms - 1000))
        seen: set[str] = set()
        while current < final:
            chunk_end = min(current + timedelta(days=7), final)
            for position in fetch_window(current, chunk_end):
                position_id = str(position.get("positionId", ""))
                if position_id and position_id not in seen:
                    seen.add(position_id)
                    yield position
            current = chunk_end + timedelta(milliseconds=1)

    def iter_closed_trades(self, start_date: datetime, end_date: datetime) -> Iterator[dict[str, Any]]:
        yield from self.iter_history_positions(start_date, end_date, position_flag="CLOSED")

    def iter_taken_over_trades(self, start_date: datetime, end_date: datetime) -> Iterator[dict[str, Any]]:
        yield from self.iter_history_positions(start_date, end_date, position_flag="TAKEOVER")

    def get_balance(self) -> dict[str, Any]:
        return self._request("/uapi/v1/account/balances")

    def get_fills(self, symbol: str, start_date: datetime, end_date: datetime) -> list[dict[str, Any]]:
        return self._get_windowed_records("/uapi/v1/trade/fills", "fills", start_date, end_date, symbol)

    def get_funding(self, start_date: datetime, end_date: datetime, symbol: str | None = None) -> list[dict[str, Any]]:
        return self._get_windowed_records("/uapi/v1/trade/fundingFee", "fundings", start_date, end_date, symbol)

    def _get_windowed_records(
        self, path: str, collection: str, start_date: datetime, end_date: datetime, symbol: str | None,
    ) -> list[dict[str, Any]]:
        final = min(end_date.astimezone(UTC), datetime.now(tz=UTC) + timedelta(milliseconds=self._server_time_offset_ms - 1000))
        if final <= start_date:
            return []

        def fetch(start: datetime, end: datetime) -> list[dict[str, Any]]:
            payload = self._request(path, {
                "symbol": symbol, "startTime": int(start.timestamp() * 1000),
                "endTime": int(end.timestamp() * 1000), "limit": 200,
            })
            rows = payload.get("data", {}).get(collection, [])
            # The fills/funding endpoints also cap a response at 200 rows and
            # do not provide cursor pagination.  Treat a full page as
            # truncated and split the interval.
            if len(rows) < 200:
                return rows
            if end - start <= timedelta(seconds=1):
                raise PionexAPIError(PionexErrorCode.API_ERROR)
            midpoint = start + (end - start) / 2
            return fetch(start, midpoint) + fetch(midpoint + timedelta(milliseconds=1), end)

        unique: dict[str, dict[str, Any]] = {}
        for row in fetch(start_date.astimezone(UTC), final):
            identity = str(row.get("id") or f"{row.get('symbol')}:{row.get('timestamp')}:{row.get('fundingFee')}")
            unique[identity] = row
        return sorted(unique.values(), key=lambda row: int(row.get("timestamp", 0)))


def check_pionex() -> dict[str, Any]:
    base = {"enabled": settings.pionex_enabled, "proxy_configured": bool(settings.pionex_proxy_url.strip())}
    if not settings.pionex_enabled:
        return {"status": "disabled", **base, "relay_reachable": False, "pionex_reachable": False, "authenticated": False}
    try:
        result = PionexAdapter("health_pionex").check_health()
    except PionexAPIError as exc:
        relay_ok = exc.code not in {PionexErrorCode.RELAY_UNAVAILABLE, PionexErrorCode.RELAY_TIMEOUT}
        auth_error = exc.code in {PionexErrorCode.AUTH_ERROR, PionexErrorCode.PERMISSION_ERROR}
        return {"status": "error", **base, "relay_reachable": relay_ok, "pionex_reachable": relay_ok, "authenticated": False if auth_error else False, "code": exc.code}
    return {"status": "ok", **base, "relay_reachable": True, "pionex_reachable": True, "authenticated": True, **result}
