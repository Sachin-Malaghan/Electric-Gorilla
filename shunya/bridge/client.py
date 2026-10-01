"""Unreal Bridge client (spec 17, 18).

Talks to the ShunyaAgentBridge editor plugin over localhost HTTP. Editor and runtime
commands are separate scopes with separate permissions; the plugin re-checks the scope
header, so a runtime-only caller cannot issue editor mutations even if this client is bypassed.
"""

from __future__ import annotations

from typing import Any

import httpx

from shunya.core.interfaces import IUnrealBridge

READ_ROUTES = {"status", "level", "actors", "actor", "assets", "telemetry"}
EDITOR_COMMANDS = {"spawn_actor", "set_property", "load_level", "save_level", "start_pie", "stop_pie", "capture_screenshot"}
RUNTIME_COMMANDS = {"console_stat", "capture_screenshot"}


class BridgeUnavailable(Exception):
    pass


class HttpUnrealBridge(IUnrealBridge):
    def __init__(self, base_url: str, token: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self, scope: str) -> dict[str, str]:
        return {"X-Shunya-Token": self.token, "X-Shunya-Scope": scope}

    async def _request(self, method: str, path: str, *, scope: str, params: dict | None = None, json: dict | None = None) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.request(method, f"{self.base_url}/shunya/{path}", params=params, json=json, headers=self._headers(scope))
        except httpx.HTTPError as e:
            raise BridgeUnavailable(f"Unreal Editor bridge not reachable at {self.base_url} ({type(e).__name__}). Is the editor running with the ShunyaAgentBridge plugin?") from e
        try:
            data = r.json()
        except ValueError:
            data = {"raw": r.text}
        if r.status_code >= 400:
            raise BridgeUnavailable(f"bridge returned {r.status_code}: {data}")
        return data

    async def status(self) -> dict[str, Any]:
        try:
            data = await self._request("GET", "status", scope="read")
            return {"connected": True, **data}
        except BridgeUnavailable as e:
            return {"connected": False, "reason": str(e)}

    async def query(self, route: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if route not in READ_ROUTES:
            raise ValueError(f"unknown bridge route '{route}'")
        return await self._request("GET", route, scope="read", params={k: str(v) for k, v in (params or {}).items()})

    async def command(self, command: str, args: dict[str, Any], scope: str) -> dict[str, Any]:
        allowed = EDITOR_COMMANDS if scope == "editor" else RUNTIME_COMMANDS if scope == "runtime" else set()
        if command not in allowed:
            raise PermissionError(f"command '{command}' is not allowed in scope '{scope}'")
        return await self._request("POST", "command", scope=scope, json={"command": command, "args": args})


class NullUnrealBridge(IUnrealBridge):
    async def status(self) -> dict[str, Any]:
        return {"connected": False, "reason": "bridge disabled"}

    async def query(self, route: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        raise BridgeUnavailable("bridge disabled")

    async def command(self, command: str, args: dict[str, Any], scope: str) -> dict[str, Any]:
        raise BridgeUnavailable("bridge disabled")
