"""Config flow for Wiener Netze Smart Meter integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("client_id"): str,
        vol.Required("client_secret"): str,
        vol.Required("api_key"): str,
        vol.Optional("zaehlpunktnummer"): str,
        vol.Optional("scan_interval", default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=15, max=60)
        ),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate credentials by fetching Zaehlpunkte."""
    from .api import WNAPIClient

    try:
        client = WNAPIClient(
            client_id=data["client_id"],
            client_secret=data["client_secret"],
            api_key=data["api_key"],
        )
        zaehlpunkte = await hass.async_add_executor_job(client.get_anlagendaten)
    except Exception as exc:
        _LOGGER.error("Error connecting to Wiener Netze API: %s", exc)
        if "401" in str(exc) or "403" in str(exc) or "auth" in str(exc).lower():
            raise InvalidAuth from exc
        raise CannotConnect from exc

    if not zaehlpunkte:
        raise CannotConnect("No Zaehlpunkte returned")

    # Validate specified Zaehlpunktnummer exists
    zp_nr = data.get("zaehlpunktnummer", "").strip()
    if zp_nr:
        known = [
            zp.get("zaehlpunktnummer") or zp.get("zaehlpunkt")
            for zp in zaehlpunkte
        ]
        if zp_nr not in known:
            raise InvalidZaehlpunkt(f"{zp_nr} not found in account")

    return {"zaehlpunkte": zaehlpunkte}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Wiener Netze Smart Meter."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except InvalidZaehlpunkt:
                errors["zaehlpunktnummer"] = "invalid_zaehlpunkt"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id("wienernetze_smartmeter")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Wiener Netze Smart Meter",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class InvalidZaehlpunkt(HomeAssistantError):
    """Error to indicate the specified Zaehlpunktnummer was not found."""
