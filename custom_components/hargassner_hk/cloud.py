"""Client for the Hargassner cloud API (web.hargassner.at).

Used for writing parameters (setpoints, circuit modes), which the local
telnet stream cannot do.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from .const import (
    API_BASE_URL,
    API_INSTALLATIONS,
    API_LOGIN,
    API_LOGOUT,
    API_REFRESH,
    API_WIDGETS,
    APP_BRANDING,
    CLIENT_ID,
    CLIENT_SECRET,
)

_LOGGER = logging.getLogger(__name__)


class CloudError(Exception):
    """Generic cloud API error."""


class CloudAuthError(CloudError):
    """Login rejected."""


class HargassnerCloud:
    """Minimal async client for the Hargassner cloud."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at = 0.0

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json", "Branding": APP_BRANDING}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def _request(self, method: str, path: str, json: dict | None = None, *, auth_retry: bool = True) -> Any:
        url = path if path.startswith("http") else API_BASE_URL + path
        try:
            async with self._session.request(
                method, url, headers=self._headers(), json=json, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 401 and auth_retry:
                    await self._reauthenticate()
                    return await self._request(method, path, json, auth_retry=False)
                if resp.status in (401, 403):
                    raise CloudAuthError(f"HTTP {resp.status} for {path}")
                if resp.status >= 400:
                    raise CloudError(f"HTTP {resp.status} for {path}: {(await resp.text())[:200]}")
                if resp.status == 204:
                    return {}
                if "json" in (resp.content_type or ""):
                    return await resp.json(content_type=None)
                return {}
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise CloudError(f"Network error: {err}") from err

    def _store_tokens(self, data: Any) -> None:
        inner = data.get("data", data) if isinstance(data, dict) else {}
        token = inner.get("access_token") if isinstance(inner, dict) else None
        if not token:
            raise CloudAuthError("No access token in response")
        self._access_token = token
        self._refresh_token = inner.get("refresh_token", self._refresh_token)
        self._expires_at = time.time() + float(inner.get("expires_in", 3600))

    async def login(self) -> None:
        """Log in with email and password."""
        self._access_token = None
        data = await self._request(
            "POST",
            API_LOGIN,
            {"email": self._email, "password": self._password, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
            auth_retry=False,
        )
        self._store_tokens(data)

    async def _reauthenticate(self) -> None:
        if self._refresh_token:
            try:
                data = await self._request(
                    "POST",
                    API_REFRESH,
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": self._refresh_token,
                        "client_id": CLIENT_ID,
                        "client_secret": CLIENT_SECRET,
                    },
                    auth_retry=False,
                )
                self._store_tokens(data)
                return
            except CloudError as err:
                _LOGGER.debug("Token refresh failed (%s), logging in again", err)
        await self.login()

    async def ensure_token(self) -> None:
        """Log in or refresh the token if it expires within 5 minutes."""
        if self._access_token is None:
            await self.login()
        elif time.time() > self._expires_at - 300:
            await self._reauthenticate()

    async def logout(self) -> None:
        if self._access_token is None:
            return
        try:
            await self._request("POST", API_LOGOUT, {}, auth_retry=False)
        except CloudError:
            pass
        self._access_token = None
        self._refresh_token = None

    async def get_installations(self) -> list[dict[str, Any]]:
        data = await self._request("GET", f"{API_INSTALLATIONS}?with=devices.software%3Bdevices.gateway&sort=name")
        result = data.get("data", []) if isinstance(data, dict) else data
        if isinstance(result, dict):
            return [result]
        return [i for i in result if isinstance(i, dict)] if isinstance(result, list) else []

    async def get_widgets(self, installation_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        data = await self._request("GET", f"{API_INSTALLATIONS}/{installation_id}{API_WIDGETS}")
        if isinstance(data, dict):
            widgets = data.get("data", [])
            meta = data.get("meta", {})
            return (
                [w for w in widgets if isinstance(w, dict)] if isinstance(widgets, list) else [],
                meta if isinstance(meta, dict) else {},
            )
        return ([w for w in data if isinstance(w, dict)] if isinstance(data, list) else []), {}

    async def set_value(self, resource: str, value: Any) -> None:
        await self._request("PATCH", resource, {"value": value})

    async def post_action(self, resource: str) -> None:
        await self._request("POST", resource)
