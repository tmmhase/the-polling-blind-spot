"""Small HTTP helpers for public dataset downloads.

The standard library is used first. ``curl`` is a fallback for hosts whose
TLS chain Python cannot verify in this environment.
"""

from __future__ import annotations

import shutil
import ssl
import subprocess
import urllib.error
import urllib.request

from polling_blind_spot.ingest.errors import DownloadError

USER_AGENT = (
    "ThePollingBlindSpot/0.1 "
    "(https://github.com/tmmhase/the-polling-blind-spot; research data ingestion)"
)


def download_bytes(url: str, timeout: int = 180) -> bytes:
    """Fetch URL contents. Reject HTML error pages and empty bodies."""
    errors: list[str] = []

    try:
        return _download_with_urllib(url, timeout=timeout)
    except DownloadError as exc:
        errors.append(f"urllib: {exc}")

    curl_path = shutil.which("curl")
    if curl_path:
        try:
            return _download_with_curl(curl_path, url, timeout=timeout)
        except DownloadError as trans_exc:
            errors.append(f"curl: {trans_exc}")

    raise DownloadError(f"Failed to fetch {url}. " + " | ".join(errors))


def download_html(url: str, timeout: int = 120) -> tuple[bytes, dict[str, str]]:
    """Fetch a URL that is expected to be an HTML document.

    Returns the body and a small set of response headers. Wikipedia's REST
    HTML endpoint is the caller this exists for: ``download_bytes`` rejects
    HTML because the CSV/JSON sources must not silently save an error page.
    """
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=timeout, context=ssl.create_default_context()
        ) as response:
            status = getattr(response, "status", None)
            if status is not None and status >= 400:
                raise DownloadError(f"HTTP {status} for {url}")
            payload = response.read()
            headers = {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        raise DownloadError(f"HTTP {exc.code} {exc.reason} for {url}") from exc
    except urllib.error.URLError as exc:
        raise DownloadError(f"{exc.reason} for {url}") from exc

    if not payload:
        raise DownloadError(f"Empty response from {url}")
    if not _looks_like_html(payload, headers.get("content-type", "")):
        raise DownloadError(
            f"Expected HTML from {url} "
            f"(Content-Type={headers.get('content-type', '')!r}, {len(payload)} bytes)"
        )
    return payload, headers


def _download_with_urllib(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/csv,application/json,*/*"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=timeout, context=ssl.create_default_context()
        ) as response:
            status = getattr(response, "status", None)
            if status is not None and status >= 400:
                raise DownloadError(f"HTTP {status}")
            content_type = response.headers.get("Content-Type", "")
            payload = response.read()
    except urllib.error.HTTPError as exc:
        raise DownloadError(f"HTTP {exc.code} {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise DownloadError(str(exc.reason)) from exc

    return _reject_html(payload, content_type, url)


def _download_with_curl(curl_path: str, url: str, timeout: int) -> bytes:
    completed = subprocess.run(
        [
            curl_path,
            "-sS",
            "-L",
            "--fail",
            "--max-time",
            str(timeout),
            "-A",
            USER_AGENT,
            "-H",
            "Accept: text/csv,application/json,*/*",
            url,
        ],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise DownloadError(stderr or f"curl exited {completed.returncode}")
    return _reject_html(completed.stdout, "", url)


def _reject_html(payload: bytes, content_type: str, url: str) -> bytes:
    if not payload:
        raise DownloadError(f"Empty response from {url}")
    if _looks_like_html(payload, content_type):
        raise DownloadError(
            f"Response from {url} looks like HTML, not a dataset "
            f"(Content-Type={content_type!r}, {len(payload)} bytes)"
        )
    return payload


def _looks_like_html(payload: bytes, content_type: str) -> bool:
    lowered_type = content_type.lower()
    if "text/html" in lowered_type:
        return True
    head = payload.lstrip()[:200].lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")
