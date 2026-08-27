"""HTTP client for the local WiNET stove module.

The protocol is documented in ``docs/PROTOCOL.md``. Two things are worth repeating
here because they shape this module's API:

* ``/ajax/get-registers`` is a command dispatcher, not a read endpoint. Only ``key=019``
  and ``key=020`` are reads; ``key=022`` toggles the stove. Each key therefore gets its
  own method, and the write-ish ones are named accordingly.
* the on/off command is a *toggle without an argument*, so the caller is responsible for
  deciding whether it should be sent at all.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = ClientTimeout(total=15)

KEY_GET_CONFIG = "019"
KEY_GET_RUNTIME = "020"
KEY_TOGGLE_POWER = "022"
KEY_SET_NAME = "026"
KEY_SET_REGISTER = "002"


class WinetError(Exception):
    """Base error for the WiNET client."""


class WinetConnectionError(WinetError):
    """The module could not be reached or answered with a transport error."""


class WinetResponseError(WinetError):
    """The module answered, but the payload was not what we expect."""


class WinetClient:
    """Thin async wrapper around the module's ``/ajax/*`` endpoints."""

    def __init__(self, session: ClientSession, host: str) -> None:
        """Store the session and target host (an IP or hostname, no scheme)."""
        self._session = session
        self._host = host
        self._base = f"http://{host}"
        #: The module serves a single request at a time; serialise our own calls too.
        self._lock = asyncio.Lock()

    @property
    def host(self) -> str:
        """Return the configured host."""
        return self._host

    async def _request(
        self, path: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """POST a form body to ``path`` and return the decoded JSON object."""
        url = f"{self._base}{path}"
        async with self._lock:
            try:
                response = await self._session.post(
                    url, data=data, timeout=REQUEST_TIMEOUT
                )
                response.raise_for_status()
                # The firmware answers with Content-Type: text/html for JSON bodies.
                payload = await response.json(content_type=None)
            except TimeoutError as err:
                raise WinetConnectionError(f"Timeout talking to {url}") from err
            except ClientError as err:
                raise WinetConnectionError(f"Error talking to {url}: {err}") from err
            except ValueError as err:
                raise WinetResponseError(f"Invalid JSON from {url}: {err}") from err

        if not isinstance(payload, dict):
            raise WinetResponseError(f"Unexpected payload from {url}: {payload!r}")
        _LOGGER.debug("%s %s -> %s", path, data, payload)
        return payload

    async def _dispatch(self, key: str, **fields: Any) -> dict[str, Any]:
        """Call the ``/ajax/get-registers`` dispatcher with ``key`` and extra fields."""
        return await self._request("/ajax/get-registers", {"key": key, **fields})

    @staticmethod
    def _expect_ok(payload: dict[str, Any], what: str) -> None:
        """Raise unless the module acknowledged a command."""
        if payload.get("result") is not True:
            raise WinetResponseError(f"{what} was rejected by the module: {payload}")

    # --- reads ------------------------------------------------------------

    async def async_get_module_status(self) -> dict[str, Any]:
        """Return Wi-Fi, network and firmware information (read-only)."""
        return await self._request("/ajax/get-status")

    async def async_get_config(self) -> dict[str, Any]:
        """Return the module configuration, ``key=019`` (read-only)."""
        payload = await self._dispatch(KEY_GET_CONFIG)
        if "custom" not in payload:
            raise WinetResponseError(f"Unexpected key=019 payload: {payload}")
        return payload

    async def async_get_runtime(self, category: int = 0) -> dict[str, Any]:
        """Return the runtime register snapshot, ``key=020`` (read-only)."""
        payload = await self._dispatch(KEY_GET_RUNTIME, category=category)
        if not isinstance(payload.get("params"), list):
            raise WinetResponseError(f"Unexpected key=020 payload: {payload}")
        return payload

    # --- writes -----------------------------------------------------------

    async def async_toggle_power(self) -> None:
        """Send the on/off **toggle**, ``key=022``.

        There is no way to command an absolute state: the module flips whatever the
        stove is currently doing. Callers must read the status first.
        """
        _LOGGER.info("Sending power toggle to WiNET at %s", self._host)
        self._expect_ok(await self._dispatch(KEY_TOGGLE_POWER), "Power toggle")

    async def async_set_register(
        self, memory: int, reg_id: int, raw_value: int
    ) -> None:
        """Write ``raw_value`` into register ``reg_id``.

        ``memory`` is 0 for RAM (volatile) or 1 for EEPROM (persistent).
        """
        _LOGGER.info(
            "Writing register %s (memory %s) = %s on WiNET at %s",
            reg_id,
            memory,
            raw_value,
            self._host,
        )
        payload = await self._request(
            "/ajax/set-register",
            {
                "key": KEY_SET_REGISTER,
                "memory": memory,
                "regId": reg_id,
                "value": raw_value,
            },
        )
        self._expect_ok(payload, f"Write of register {reg_id}")

    async def async_set_device_name(self, name: str, custom_code: int) -> None:
        """Rename the device as shown by the module, ``key=026``."""
        payload = await self._dispatch(KEY_SET_NAME, name=name, customCode=custom_code)
        self._expect_ok(payload, "Device rename")
