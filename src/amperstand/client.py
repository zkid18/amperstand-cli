"""Thin HTTP client for an amperstand-core server.

The CLI uses one of these per invocation. Bearer auth is resolved at
construction time — pass the value directly, or pass `api_key_env` and
the value is read from the environment lazily.

No retry, no caching — the CLI is short-lived and operators want errors
to bubble up loudly.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class ClientError(Exception):
    """Raised when the server returns a non-2xx or the network fails."""


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

    # ── Feeds ───────────────────────────────────────────────────────

    def feeds_list(self) -> list[dict[str, Any]]:
        data = self._get("/v1/feeds")
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
        return self._post("/v1/feeds/register", body)

    def feeds_remove(self, feed_id: str) -> None:
        r = self._client.delete(f"/v1/feeds/{feed_id}")
        if r.status_code not in (200, 204):
            raise ClientError(self._fmt(r))

    def feeds_sync(self, *, timeout: float = 600.0) -> dict[str, Any]:
        return self._post("/v1/feeds/sync", {}, timeout=timeout)

    # ── Vault ───────────────────────────────────────────────────────

    def health(self) -> dict[str, Any]:
        return self._get("/health")

    def docs_count(self) -> int:
        data = self._get("/v1/docs?limit=1")
        return int(data.get("total", 0))

    # ── Internals ───────────────────────────────────────────────────

    def _get(self, path: str) -> dict[str, Any]:
        r = self._client.get(path)
        if r.status_code >= 400:
            raise ClientError(self._fmt(r))
        return r.json()

    def _post(
        self, path: str, body: dict[str, Any], *, timeout: float | None = None
    ) -> dict[str, Any]:
        r = self._client.post(path, json=body, timeout=timeout) if timeout else self._client.post(path, json=body)
        if r.status_code >= 400:
            raise ClientError(self._fmt(r))
        return r.json()

    @staticmethod
    def _fmt(r: httpx.Response) -> str:
        try:
            detail = r.json().get("detail") or r.text
        except Exception:
            detail = r.text
        return f"{r.request.method} {r.request.url.path} → {r.status_code}: {detail}"
