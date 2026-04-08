"""Sensor platform for Wiener Netze Smart Meter."""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, VIENNA_TZ, OBIS_CONSUMPTION, OBIS_FEEDIN
from .coordinator import WNSmartMeterCoordinator
from .statistics import async_insert_statistics

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from config entry."""
    coordinator: WNSmartMeterCoordinator = hass.data[DOMAIN][entry.entry_id]

    await coordinator.async_config_entry_first_refresh()

    entities = []
    for zp_nummer, zp_data in coordinator.data.items():
        for obis, zaehlwerk in zp_data.get("zaehlwerke", {}).items():
            if obis == OBIS_CONSUMPTION:
                entities.append(
                    WNSmartMeterSensor(
                        coordinator=coordinator,
                        zp_nummer=zp_nummer,
                        obis=obis,
                        sensor_type="viertelstunde",
                        name=f"Smart Meter Bezug Viertelstunde {zp_nummer[-6:]}",
                    )
                )
                entities.append(
                    WNSmartMeterSensor(
                        coordinator=coordinator,
                        zp_nummer=zp_nummer,
                        obis=obis,
                        sensor_type="tagesverbrauch",
                        name=f"Smart Meter Bezug Tagesverbrauch {zp_nummer[-6:]}",
                    )
                )
            elif obis == OBIS_FEEDIN:
                entities.append(
                    WNSmartMeterSensor(
                        coordinator=coordinator,
                        zp_nummer=zp_nummer,
                        obis=obis,
                        sensor_type="viertelstunde",
                        name=f"Smart Meter Einspeisung Viertelstunde {zp_nummer[-6:]}",
                    )
                )

    async_add_entities(entities)

    # Insert statistics after sensors are set up
    for zp_nummer in coordinator.data:
        await async_insert_statistics(hass, coordinator, zp_nummer)


class WNSmartMeterSensor(CoordinatorEntity, SensorEntity):
    """Sensor entity for Wiener Netze Smart Meter."""

    _attr_device_class    = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class     = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        coordinator: WNSmartMeterCoordinator,
        zp_nummer: str,
        obis: str,
        sensor_type: str,
        name: str,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._zp_nummer   = zp_nummer
        self._obis        = obis
        self._sensor_type = sensor_type
        self._attr_name   = name
        self._attr_unique_id = f"{DOMAIN}_{zp_nummer}_{obis}_{sensor_type}"
        self._tz          = ZoneInfo(VIENNA_TZ)

    @property
    def _zaehlwerk_data(self) -> dict | None:
        if not self.coordinator.data:
            return None
        zp = self.coordinator.data.get(self._zp_nummer, {})
        return zp.get("zaehlwerke", {}).get(self._obis)

    @property
    def native_value(self) -> float | None:
        data = self._zaehlwerk_data
        if not data:
            return None

        if self._sensor_type == "viertelstunde":
            wh = data.get("latest_messwert")
            return round(wh / 1000, 3) if wh is not None else None
        elif self._sensor_type == "tagesverbrauch":
            wh = data.get("tagesverbrauch_wh")
            return round(wh / 1000, 3) if wh is not None else None

        return None

    @property
    def extra_state_attributes(self) -> dict:
        data = self._zaehlwerk_data
        if not data:
            return {}

        attrs = {
            "zaehlpunkt": self._zp_nummer,
            "obis_code":  self._obis,
            "einheit":    data.get("einheit"),
        }

        if self._sensor_type == "viertelstunde":
            zeit_bis_utc = data.get("latest_zeitBis")
            if zeit_bis_utc:
                dt = datetime.fromisoformat(zeit_bis_utc.replace("Z", "+00:00"))
                dt_local = dt.astimezone(self._tz)
                attrs["zeitBis"]          = dt_local.isoformat()
                attrs["zeitBis_readable"] = dt_local.strftime("%d.%m.%Y %H:%M")
            attrs["qualitaet"] = data.get("latest_qualitaet")

        return attrs
