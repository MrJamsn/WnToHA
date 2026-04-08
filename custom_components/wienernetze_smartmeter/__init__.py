"""Wiener Netze Smart Meter Integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL
from .coordinator import WNSmartMeterCoordinator
from .statistics import async_backfill_statistics

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Wiener Netze Smart Meter from a config entry."""
    from wiener_netze_smart_meter_api import WNAPIClient

    try:
        client = await hass.async_add_executor_job(
            lambda: WNAPIClient(
                username=entry.data["username"],
                password=entry.data["password"],
                client_id=entry.data["client_id"],
                client_secret=entry.data["client_secret"],
                api_key=entry.data["api_key"],
            )
        )
    except Exception as exc:
        raise ConfigEntryNotReady(f"Cannot connect to Wiener Netze API: {exc}") from exc

    scan_interval = entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL)
    zaehlpunktnummer = entry.data.get("zaehlpunktnummer", "").strip() or None

    coordinator = WNSmartMeterCoordinator(
        hass=hass,
        client=client,
        scan_interval=scan_interval,
        zaehlpunktnummer=zaehlpunktnummer,
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Backfill last 30 days on first setup
    async def _backfill(event=None):
        if zaehlpunktnummer:
            # Use the configured Zaehlpunktnummer directly
            await async_backfill_statistics(hass, client, zaehlpunktnummer, days=30)
        else:
            zaehlpunkte = await hass.async_add_executor_job(client.get_anlagendaten)
            for zp in zaehlpunkte:
                zp_nr = zp.get("zaehlpunktnummer") or zp.get("zaehlpunkt")
                if zp_nr:
                    await async_backfill_statistics(hass, client, zp_nr, days=30)

    hass.async_create_task(_backfill())

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
