from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
import ssl
from typing import Any

from config import config


logger = logging.getLogger("zenithionpay_client")


class ZenithionPayApiError(Exception):
    def __init__(self, status: int, payload: Any, url: str) -> None:
        self.status = status
        self.payload = payload
        self.url = url
        super().__init__(f"ZenithionPay API error {status} for {url}: {payload}")


def _http_request_json(
    method: str,
    url: str,
    headers: dict[str, str],
    timeout: float = 10.0,
    json_body: Any | None = None,
) -> tuple[int, Any]:
    data = None
    req_headers = dict(headers or {})

    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json; charset=utf-8")

    req = urllib.request.Request(url, method=method.upper(), headers=req_headers, data=data)

    skip_verify = True
    ssl_context = None
    if url.lower().startswith("https://"):
        ssl_context = ssl._create_unverified_context() if skip_verify else ssl.create_default_context()

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        status = getattr(e, "code", 0) or 0
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""

    try:
        return status, json.loads(body)
    except Exception:
        return status, body


def _join_url(base: str, endpoint: str) -> str:
    base = (base or "").rstrip("/") + "/"
    endpoint = (endpoint or "").lstrip("/")
    return base + endpoint


def _with_query_params(url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return url
    return f"{url}?{urllib.parse.urlencode(params, doseq=True)}"


async def get_json(
    endpoint: str,
    headers: dict[str, str],
    timeout: float = 10.0,
    params: dict[str, Any] | None = None,
) -> Any:
    url = _with_query_params(_join_url(config.merchant_api_url_start, endpoint), params)
    started = time.perf_counter()

    try:
        status, payload = await asyncio.to_thread(_http_request_json, "GET", url, headers, timeout, None)
    except Exception:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        logger.exception("GET %s failed (%.1f ms)", url, elapsed_ms)
        raise

    elapsed_ms = (time.perf_counter() - started) * 1000.0

    if 200 <= int(status) <= 299:
        logger.info("GET %s -> %s (%.1f ms)", url, status, elapsed_ms)
        return payload

    logger.warning("GET %s -> %s (%.1f ms), payload=%r", url, status, elapsed_ms, payload)
    raise ZenithionPayApiError(status=int(status), payload=payload, url=url)


async def post_json(
    endpoint: str,
    headers: dict[str, str],
    timeout: float = 10.0,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
) -> Any:
    url = _with_query_params(_join_url(config.merchant_api_url_start, endpoint), params)
    started = time.perf_counter()

    try:
        status, payload = await asyncio.to_thread(_http_request_json, "POST", url, headers, timeout, json_body)
    except Exception:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        logger.exception("POST %s failed (%.1f ms)", url, elapsed_ms)
        raise

    elapsed_ms = (time.perf_counter() - started) * 1000.0

    if 200 <= int(status) <= 299:
        logger.info("POST %s -> %s (%.1f ms)", url, status, elapsed_ms)
        return payload

    logger.warning("POST %s -> %s (%.1f ms), payload=%r", url, status, elapsed_ms, payload)
    raise ZenithionPayApiError(status=int(status), payload=payload, url=url)
