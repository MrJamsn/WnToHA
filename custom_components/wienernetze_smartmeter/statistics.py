"""Statistics insertion for Wiener Netze Smart Meter - 15-min values with correct timestamps."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    VIENNA_TZ,
    OBIS_CONSUMPTION,
    OBIS_FEEDIN,
    STATISTIC_ID_CONSUMPTION,
    STATISTIC_ID_FEEDIN,
)

_LOGGER = logging.getLogger(__name__)

UNIT_WH  = "Wh"
UNIT_KWH = "kWh"


async def async_insert_statistics(
    hass: HomeAssistant,
    coordinator,
    zp_nummer: str,
) -> None:
    """Insert 15-min statistics with correct timestamps into HA recorder."""
    data = coordinator.data
    if not data or zp_nummer not in data:
        return

    zaehlwerke = data[zp_nummer].get("zaehlwerke", {})

    # Consumption (Bezug)
    if OBIS_CONSUMPTION in zaehlwerke:
        await _insert_zaehlwerk_statistics(
            hass,
            coordinator,
            zp_nummer,
            zaehlwerke[OBIS_CONSUMPTION],
            statistic_id=f"{STATISTIC_ID_CONSUMPTION}_{zp_nummer}",
            name=f"Smart Meter Bezug {zp_nummer[-6:]}",
        )

    # Feed-in (Einspeisung) - only if present
    if OBIS_FEEDIN in zaehlwerke:
        await _insert_zaehlwerk_statistics(
            hass,
            coordinator,
            zp_nummer,
            zaehlwerke[OBIS_FEEDIN],
            statistic_id=f"{STATISTIC_ID_FEEDIN}_{zp_nummer}",
            name=f"Smart Meter Einspeisung {zp_nummer[-6:]}",
        )


async def _insert_zaehlwerk_statistics(
    hass: HomeAssistant,
    coordinator,
    zp_nummer: str,
    zaehlwerk_data: dict,
    statistic_id: str,
    name: str,
) -> None:
    """Insert statistics for one Zaehlwerk."""
    tz       = ZoneInfo(VIENNA_TZ)
    messwerte = zaehlwerk_data.get("messwerte", [])

    if not messwerte:
        return

    # Get last stored statistic to avoid duplicates
    last_stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, {"sum"}
    )

    last_sum = 0.0
    last_dt  = None

    if last_stats and statistic_id in last_stats:
        last_entry = last_stats[statistic_id][0]
        last_sum   = last_entry.get("sum", 0.0) or 0.0
        last_dt    = dt_util.utc_from_timestamp(last_entry["start"])
        _LOGGER.debug(
            "Last statistic for %s: sum=%.3f kWh at %s",
            statistic_id, last_sum, last_dt
        )

    # Build StatisticData list - only new entries
    statistics: list[StatisticData] = []
    running_sum = last_sum

    for messwert in messwerte:
        try:
            # zeitBis is the end of the 15-min interval - use as the stat timestamp
            zeit_bis_utc = datetime.fromisoformat(
                messwert["zeitBis"].replace("Z", "+00:00")
            )

            # Skip already stored entries
            if last_dt and zeit_bis_utc <= last_dt:
                continue

            # Skip invalid quality
            if messwert.get("qualitaet") not in ("VAL", "EST", None, ""):
                _LOGGER.debug("Skipping messwert with qualitaet=%s", messwert.get("qualitaet"))
                continue

            wh_value  = float(messwert["messwert"])
            kwh_value = wh_value / 1000.0
            running_sum += kwh_value

            statistics.append(
                StatisticData(
                    start=zeit_bis_utc,
                    state=kwh_value,
                    sum=running_sum,
                )
            )
        except Exception as exc:
            _LOGGER.warning("Error parsing messwert %s: %s", messwert, exc)
            continue

    if not statistics:
        _LOGGER.debug("No new statistics to insert for %s", statistic_id)
        return

    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=name,
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=UNIT_KWH,
    )

    async_add_external_statistics(hass, metadata, statistics)
    _LOGGER.info(
        "Inserted %d new statistics for %s (sum now: %.3f kWh)",
        len(statistics), statistic_id, running_sum
    )


async def async_backfill_statistics(
    hass: HomeAssistant,
    client,
    zp_nummer: str,
    days: int = 30,
) -> None:
    """Backfill historical statistics on first setup."""
    _LOGGER.info("Starting backfill for %s (%d days)", zp_nummer, days)
    tz      = ZoneInfo(VIENNA_TZ)
    heute   = datetime.now(tz)
    von     = (heute - timedelta(days=days)).strftime("%Y-%m-%d")
    bis     = heute.strftime("%Y-%m-%d")

    try:
        raw = await hass.async_add_executor_job(
            lambda: client.get_quarter_hour_values(
                date_from=von,
                date_to=bis,
            )
        )
    except Exception as exc:
        _LOGGER.error("Backfill fetch failed for %s: %s", zp_nummer, exc)
        return

    # Build a fake coordinator-like data structure and re-use insert logic
    for zp_data in raw:
        if zp_data.get("zaehlpunkt") != zp_nummer:
            continue

        for zaehlwerk in zp_data.get("zaehlwerke", []):
            obis      = zaehlwerk.get("obisCode", "")
            einheit   = zaehlwerk.get("einheit", "WH")
            messwerte = zaehlwerk.get("messwerte", [])

            if obis == OBIS_CONSUMPTION:
                stat_id = f"{STATISTIC_ID_CONSUMPTION}_{zp_nummer}"
                stat_name = f"Smart Meter Bezug {zp_nummer[-6:]}"
            elif obis == OBIS_FEEDIN:
                stat_id = f"{STATISTIC_ID_FEEDIN}_{zp_nummer}"
                stat_name = f"Smart Meter Einspeisung {zp_nummer[-6:]}"
            else:
                continue

            await _insert_zaehlwerk_statistics(
                hass,
                None,
                zp_nummer,
                {"messwerte": messwerte},
                statistic_id=stat_id,
                name=stat_name,
            )

    _LOGGER.info("Backfill complete for %s", zp_nummer)
