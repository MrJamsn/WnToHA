"""Wiener Netze Smart Meter Integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL, DEFAULT_BACKFILL_DAYS, STATISTIC_ID_CONSUMPTION
from .coordinator import WNSmartMeterCoordinator
from .statistics import async_backfill_statistics

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

# How many days to catch up when statistics already exist
_CATCHUP_DAYS = 7


async def _backfill_days_needed(hass: HomeAssistant, zp_nummer: str, full_days: int) -> int:
    """Return how many days to backfill.

    If no statistics exist yet, return full_days (initial load).
    If statistics already exist, return _CATCHUP_DAYS to fill recent gaps only.
    """
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import get_last_statistics

    stat_id = f"{STATISTIC_ID_CONSUMPTION}_{zp_nummer.lower()}"
    last_stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, stat_id, True, {"sum"}
    )
    if last_stats and stat_id in last_stats:
        _LOGGER.debug("Statistics exist for %s — running %d-day catch-up only", zp_nummer, _CATCHUP_DAYS)
        return _CATCHUP_DAYS

    _LOGGER.info("No statistics found for %s — running full %d-day backfill", zp_nummer, full_days)
    return full_days


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Wiener Netze Smart Meter from a config entry."""
    from .api import WNAPIClient

    try:
        client = WNAPIClient(
            client_id=entry.data["client_id"],
            client_secret=entry.data["client_secret"],
            api_key=entry.data["api_key"],
        )
    except Exception as exc:
        raise ConfigEntryNotReady(f"Cannot connect to Wiener Netze API: {exc}") from exc

    scan_interval    = int(entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL))
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

    backfill_days = int(entry.data.get("backfill_days", DEFAULT_BACKFILL_DAYS))

    async def _backfill(event=None):
        zp_list = (
            [zaehlpunktnummer]
            if zaehlpunktnummer
            else [
                zp.get("zaehlpunktnummer") or zp.get("zaehlpunkt")
                for zp in await hass.async_add_executor_job(client.get_anlagendaten)
                if zp.get("zaehlpunktnummer") or zp.get("zaehlpunkt")
            ]
        )
        for zp_nr in zp_list:
            days = await _backfill_days_needed(hass, zp_nr, backfill_days)
            await async_backfill_statistics(hass, client, zp_nr, days=days)

    hass.async_create_task(_backfill())

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
