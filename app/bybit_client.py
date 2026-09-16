import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

import requests
from pybit.exceptions import FailedRequestError, InvalidRequestError
from pybit.unified_trading import HTTP

from app.config import settings


CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 20
REQUEST_TIMEOUT = (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS)
MAX_RETRIES = 2
RETRY_DELAYS_SECONDS = (1, 2)
BYBIT_TIME_URL = "https://api.bybit.com/v5/market/time"
TEMPORARY_HTTP_STATUSES = {502, 503, 504}

logger = logging.getLogger("uvicorn.error")
T = TypeVar("T")


class BybitErrorCode:
    RELAY_UNAVAILABLE = "BYBIT_RELAY_UNAVAILABLE"
    RELAY_TIMEOUT = "BYBIT_RELAY_TIMEOUT"
    API_ERROR = "BYBIT_API_ERROR"
    AUTH_ERROR = "BYBIT_AUTH_ERROR"
    IP_BANNED = "BYBIT_IP_BANNED"
    RATE_LIMIT = "BYBIT_RATE_LIMIT"


ERROR_DETAILS = {
    BybitErrorCode.RELAY_UNAVAILABLE: "Bybit relay недоступен",
    BybitErrorCode.RELAY_TIMEOUT: "Превышено время ожидания Bybit relay",
    BybitErrorCode.API_ERROR: "Bybit временно недоступен",
    BybitErrorCode.AUTH_ERROR: "Ошибка авторизации Bybit",
    BybitErrorCode.IP_BANNED: "Bybit заблокировал IP relay",
    BybitErrorCode.RATE_LIMIT: "Превышен лимит запросов Bybit",
}


class BybitAPIError(RuntimeError):
    """A classified, sanitized Bybit error safe to return through the API."""

    def __init__(self, code: str, *, http_status: int = 502) -> None:
        self.code = code
        self.http_status = http_status
        self.detail = ERROR_DETAILS[code]
        super().__init__(self.detail)


def _bybit_error(exc: FailedRequestError | InvalidRequestError) -> BybitAPIError:
    status_code = getattr(exc, "status_code", None)
    message = str(getattr(exc, "message", "")).lower()

    if status_code == 10009 or (status_code == 403 and "ip" in message):
        return BybitAPIError(BybitErrorCode.IP_BANNED, http_status=503)
    if status_code in {10003, 10004, 10005, 10007, 10010} or any(
        marker in message for marker in ("permission", "signature", "api key")
    ):
        return BybitAPIError(BybitErrorCode.AUTH_ERROR, http_status=401)
    if status_code == 10006 or "rate limit" in message:
        return BybitAPIError(BybitErrorCode.RATE_LIMIT, http_status=429)
    return BybitAPIError(BybitErrorCode.API_ERROR, http_status=502)


def _network_error(exc: requests.RequestException) -> BybitAPIError:
    if isinstance(exc, requests.exceptions.Timeout):
        return BybitAPIError(BybitErrorCode.RELAY_TIMEOUT, http_status=504)
    return BybitAPIError(BybitErrorCode.RELAY_UNAVAILABLE, http_status=503)


class BybitReadOnlyClient:
    @staticmethod
    def normalize_closed_pnl_direction(payload: dict[str, Any]) -> str:
        """Map Bybit Closed PnL's closing-order side to the closed position direction.

        This mapping is specific to ``GET /v5/position/closed-pnl`` in one-way
        mode. It must not be reused for ordinary Bybit orders or other exchanges.
        """
        closing_side = str(payload.get("side", "")).strip().lower()
        if closing_side == "sell":
            return "LONG"
        if closing_side == "buy":
            return "SHORT"
        return "UNKNOWN"

    def __init__(self, operation: str) -> None:
        if not settings.bybit_api_key or not settings.bybit_api_secret:
            raise ValueError("BYBIT_API_KEY and BYBIT_API_SECRET are required")
        self.operation = operation
        self.proxy_url = os.getenv("BYBIT_PROXY_URL", "").strip()
        self.session = HTTP(
            testnet=settings.bybit_testnet,
            api_key=settings.bybit_api_key,
            api_secret=settings.bybit_api_secret,
            timeout=REQUEST_TIMEOUT,
            max_retries=1,
            force_retry=False,
        )
        if self.proxy_url:
            self.session.client.proxies.update(
                {"http": self.proxy_url, "https": self.proxy_url}
            )

    def _with_retry(self, request: Callable[[], T]) -> T:
        for attempt in range(1, MAX_RETRIES + 2):
            started = time.monotonic()
            try:
                return request()
            except requests.RequestException as exc:
                error = _network_error(exc)
            except FailedRequestError as exc:
                if getattr(exc, "status_code", None) not in TEMPORARY_HTTP_STATUSES:
                    error = _bybit_error(exc)
                    logger.error(
                        "operation=%s code=%s attempt=%s elapsed_ms=%s retry=false",
                        self.operation,
                        error.code,
                        attempt,
                        round((time.monotonic() - started) * 1000),
                    )
                    raise error from exc
                error = BybitAPIError(BybitErrorCode.API_ERROR, http_status=502)
            except InvalidRequestError as exc:
                error = _bybit_error(exc)
                logger.error(
                    "operation=%s code=%s attempt=%s elapsed_ms=%s retry=false",
                    self.operation,
                    error.code,
                    attempt,
                    round((time.monotonic() - started) * 1000),
                )
                raise error from exc
            except BybitAPIError as error:
                logger.error(
                    "operation=%s code=%s attempt=%s elapsed_ms=%s retry=false",
                    self.operation,
                    error.code,
                    attempt,
                    round((time.monotonic() - started) * 1000),
                )
                raise

            elapsed_ms = round((time.monotonic() - started) * 1000)
            if attempt > MAX_RETRIES:
                logger.error(
                    "operation=%s code=%s attempt=%s elapsed_ms=%s exhausted=true",
                    self.operation,
                    error.code,
                    attempt,
                    elapsed_ms,
                )
                raise error
            delay = RETRY_DELAYS_SECONDS[attempt - 1]
            logger.warning(
                "operation=%s code=%s attempt=%s elapsed_ms=%s retry_in_seconds=%s",
                self.operation,
                error.code,
                attempt,
                elapsed_ms,
                delay,
            )
            time.sleep(delay)
        raise AssertionError("unreachable")

    def check_relay(self) -> int:
        if not self.proxy_url:
            raise BybitAPIError(BybitErrorCode.RELAY_UNAVAILABLE, http_status=503)

        started = time.monotonic()

        def request() -> None:
            response = self.session.client.get(BYBIT_TIME_URL, timeout=REQUEST_TIMEOUT)
            if response.status_code in TEMPORARY_HTTP_STATUSES:
                raise FailedRequestError(
                    request="GET Bybit market time",
                    message="Temporary upstream HTTP error",
                    status_code=response.status_code,
                    time="",
                    resp_headers=None,
                )
            if response.status_code != 200:
                raise BybitAPIError(BybitErrorCode.API_ERROR, http_status=502)
            try:
                payload = response.json()
            except ValueError as exc:
                raise BybitAPIError(BybitErrorCode.API_ERROR, http_status=502) from exc
            if payload.get("retCode") != 0:
                raise BybitAPIError(BybitErrorCode.API_ERROR, http_status=502)

        self._with_retry(request)
        latency_ms = round((time.monotonic() - started) * 1000)
        logger.info(
            "operation=%s relay=success latency_ms=%s", self.operation, latency_ms
        )
        return latency_ms

    def iter_closed_pnl(self, start_date: datetime, end_date: datetime):
        current = start_date.astimezone(UTC)
        final = end_date.astimezone(UTC)
        while current < final:
            chunk_end = min(current + timedelta(days=7), final)
            cursor = None
            seen_cursors: set[str] = set()
            while True:
                params: dict[str, Any] = {
                    "category": "linear",
                    "startTime": int(current.timestamp() * 1000),
                    "endTime": int(chunk_end.timestamp() * 1000),
                    "limit": 100,
                }
                if cursor:
                    params["cursor"] = cursor

                response = self._with_retry(
                    lambda: self.session.get_closed_pnl(**params)
                )
                result = response.get("result", {})
                for item in result.get("list", []):
                    yield item

                cursor = result.get("nextPageCursor")
                if not cursor:
                    break
                if cursor in seen_cursors:
                    raise BybitAPIError(BybitErrorCode.API_ERROR, http_status=502)
                seen_cursors.add(cursor)
            current = chunk_end

    def get_wallet_balance(self) -> dict[str, Any]:
        return self._with_retry(
            lambda: self.session.get_wallet_balance(accountType="UNIFIED")
        )


def check_bybit_relay() -> dict[str, Any]:
    proxy_configured = bool(os.getenv("BYBIT_PROXY_URL", "").strip())
    if not proxy_configured:
        return {
            "status": "error",
            "proxy_configured": False,
            "relay_reachable": False,
            "bybit_reachable": False,
            "code": BybitErrorCode.RELAY_UNAVAILABLE,
        }

    client = BybitReadOnlyClient(operation="health_bybit_relay")
    try:
        latency_ms = client.check_relay()
    except BybitAPIError as exc:
        return {
            "status": "error",
            "proxy_configured": True,
            "relay_reachable": exc.code not in {
                BybitErrorCode.RELAY_UNAVAILABLE,
                BybitErrorCode.RELAY_TIMEOUT,
            },
            "bybit_reachable": False,
            "code": exc.code,
        }
    return {
        "status": "ok",
        "proxy_configured": True,
        "relay_reachable": True,
        "bybit_reachable": True,
        "latency_ms": latency_ms,
    }
