"""Button platform for Wiener Netze Smart Meter."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, DEFAULT_BACKFILL_DAYS
from .coordinator import WNSmartMeterCoordinator
from .statistics import async_backfill_statistics

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button from config entry."""
    coordinator: WNSmartMeterCoordinator = hass.data[DOMAIN][entry.entry_id]
    backfill_days = int(entry.data.get("backfill_days", DEFAULT_BACKFILL_DAYS))
    async_add_entities([WNBackfillButton(coordinator, entry.entry_id, backfill_days)])


class WNBackfillButton(ButtonEntity):
    """Button that triggers a full historical data backfill."""

    _attr_icon = "mdi:database-refresh"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WNSmartMeterCoordinator,
        entry_id: str,
        backfill_days: int,
    ) -> None:
        """Initialize button."""
        self._coordinator   = coordinator
        self._backfill_days = backfill_days
        self._attr_name      = "Historische Daten neu laden"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_backfill"

    async def async_press(self) -> None:
        """Trigger a full backfill for all Zaehlpunkte."""
        client           = self._coordinator.client
        zaehlpunktnummer = self._coordinator.zaehlpunktnummer

        if zaehlpunktnummer:
            zp_list = [zaehlpunktnummer]
        elif self._coordinator.zaehlpunkte:
            zp_list = [
                zp.get("zaehlpunktnummer") or zp.get("zaehlpunkt")
                for zp in self._coordinator.zaehlpunkte
                if zp.get("zaehlpunktnummer") or zp.get("zaehlpunkt")
            ]
        else:
            # Coordinator hasn't fetched Zaehlpunkte yet — fetch now
            zp_list = [
                zp.get("zaehlpunktnummer") or zp.get("zaehlpunkt")
                for zp in await self.hass.async_add_executor_job(client.get_anlagendaten)
                if zp.get("zaehlpunktnummer") or zp.get("zaehlpunkt")
            ]

        _LOGGER.info(
            "Backfill button pressed — running %d-day backfill for %s",
            self._backfill_days, zp_list,
        )
        for zp_nr in zp_list:
            await async_backfill_statistics(
                self.hass, client, zp_nr, days=self._backfill_days
            )
