"""Thin HTTP client for an amperstand-core server.

The CLI uses one of these per invocation. Bearer auth is resolved at
construction time — pass the value directly, or pass `api_key_env` and
the value is read from the environment lazily.

No retry, no caching — the CLI is short-lived and operators want errors
to bubble up loudly.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx


class ClientError(Exception):
    """Raised when the server returns a non-2xx or the network fails.

    `status_code` is the HTTP status, or None when no response arrived.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class Client:
    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        api_key_env: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            if not api_key_env:
                raise ClientError(
                    "no API key configured: pass api_key= or api_key_env="
                )
            api_key = os.environ.get(api_key_env, "").strip()
            if not api_key:
                raise ClientError(
                    f"env var {api_key_env} is unset or empty — "
                    f"`export {api_key_env}=<your-key>`"
                )
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ── Capture ─────────────────────────────────────────────────────

    def capture(
        self,
        url: str,
        *,
        persist: bool = True,
        frontmatter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._post(
            "/capture",
            {"url": url, "persist": persist, "frontmatter": frontmatter or {}},
            timeout=180.0,
        )

    def transcribe_submit(self, audio: Path, params: dict[str, Any]) -> dict[str, Any]:
        """POST /transcribe/jobs: upload a recording; the server transcribes and saves it.

        `params` are the endpoint's query parameters (filename, title, tags, …).
        Returns the queued job.
        """
        try:
            with audio.open("rb") as f:
                r = self._client.post(
                    "/transcribe/jobs",
                    params={k: v for k, v in params.items() if v not in (None, [], "")},
                    content=f,
                    headers={"Content-Type": "application/octet-stream", "Content-Length": str(audio.stat().st_size)},
                    timeout=httpx.Timeout(60.0, write=600.0),
                )
        except httpx.HTTPError as e:
            raise ClientError(f"POST /transcribe/jobs failed: {type(e).__name__}: {e}") from e
        if r.status_code >= 400:
            raise ClientError(self._fmt(r), status_code=r.status_code)
        return r.json()

    def transcribe_job(self, job_id: str) -> dict[str, Any]:
        """GET /transcribe/jobs/{id}: status, progress, and doc_id once saved."""
        try:
            return self._get(f"/transcribe/jobs/{job_id}")
        except httpx.HTTPError as e:
            raise ClientError(f"GET /transcribe/jobs/{job_id} failed: {type(e).__name__}: {e}") from e

    # ── Feeds ───────────────────────────────────────────────────────

    def feeds_list(self) -> list[dict[str, Any]]:
        data = self._get("/feeds")
        return data.get("items") or data if isinstance(data, list) else data.get("items", [])

    def feeds_register(
        self,
        url: str,
        *,
        name: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"url": url}
        if name:
            body["label"] = name
        if tags:
            body["tags"] = tags
        return self._post("/feeds/register", body)

    def feeds_remove(self, feed_id: str) -> None:
        r = self._client.delete(f"/feeds/{feed_id}")
        if r.status_code not in (200, 204):
            raise ClientError(self._fmt(r))

    def feeds_sync(self, *, timeout: float = 600.0) -> dict[str, Any]:
        return self._post("/feeds/sync", {}, timeout=timeout)

    # ── Vault ───────────────────────────────────────────────────────

    def health(self) -> dict[str, Any]:
        return self._get("/health")

    def docs_count(self) -> int:
        data = self._get("/vault?limit=1")
        return int(data.get("total", 0))

    # ── Admin ───────────────────────────────────────────────────────

    def rotate_api_key(self) -> dict[str, Any]:
        """POST /admin/rotate-key. Server mints a new key, writes it to the
        env file, returns it. Server's in-memory key is updated synchronously
        so the next request accepts the new value.
        """
        return self._post("/admin/rotate-key", {}, timeout=30.0)

    # ── Internals ───────────────────────────────────────────────────

    def _get(self, path: str) -> dict[str, Any]:
        r = self._client.get(path)
        if r.status_code >= 400:
            raise ClientError(self._fmt(r), status_code=r.status_code)
        return r.json()

    def _post(
        self, path: str, body: dict[str, Any], *, timeout: float | None = None
    ) -> dict[str, Any]:
        r = self._client.post(path, json=body, timeout=timeout) if timeout else self._client.post(path, json=body)
        if r.status_code >= 400:
            raise ClientError(self._fmt(r), status_code=r.status_code)
        return r.json()

    @staticmethod
    def _fmt(r: httpx.Response) -> str:
        try:
            detail = r.json().get("detail") or r.text
        except Exception:
            detail = r.text
        return f"{r.request.method} {r.request.url.path} → {r.status_code}: {detail}"
