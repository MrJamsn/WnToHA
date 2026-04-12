"""Statistics insertion for Wiener Netze Smart Meter."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
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

UNIT_KWH = "kWh"

# HA 2025+ requires mean_type instead of has_mean
try:
    from homeassistant.components.recorder.statistics import StatisticMeanType
    _MEAN_TYPE_NONE = StatisticMeanType.NONE
except ImportError:
    _MEAN_TYPE_NONE = None


def _make_metadata(statistic_id: str, name: str) -> StatisticMetaData:
    """Build StatisticMetaData compatible with both old and new HA versions."""
    kwargs: dict = dict(
        has_sum=True,
        name=name,
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=UNIT_KWH,
    )
    if _MEAN_TYPE_NONE is not None:
        kwargs["mean_type"] = _MEAN_TYPE_NONE
    else:
        kwargs["has_mean"] = False
    return StatisticMetaData(**kwargs)


async def async_insert_statistics(
    hass: HomeAssistant,
    coordinator,
    zp_nummer: str,
) -> None:
    """Insert hourly statistics for one Zaehlpunkt into HA recorder."""
    data = coordinator.data
    if not data or zp_nummer not in data:
        return

    zaehlwerke = data[zp_nummer].get("zaehlwerke", {})

    if OBIS_CONSUMPTION in zaehlwerke:
        await _insert_zaehlwerk_statistics(
            hass,
            zaehlwerke[OBIS_CONSUMPTION]["messwerte"],
            statistic_id=f"{STATISTIC_ID_CONSUMPTION}_{zp_nummer.lower()}",
            name=f"Smart Meter Bezug {zp_nummer[-6:]}",
        )

    if OBIS_FEEDIN in zaehlwerke:
        await _insert_zaehlwerk_statistics(
            hass,
            zaehlwerke[OBIS_FEEDIN]["messwerte"],
            statistic_id=f"{STATISTIC_ID_FEEDIN}_{zp_nummer.lower()}",
            name=f"Smart Meter Einspeisung {zp_nummer[-6:]}",
        )


async def _insert_zaehlwerk_statistics(
    hass: HomeAssistant,
    messwerte: list,
    statistic_id: str,
    name: str,
) -> None:
    """Aggregate 15-min messwerte into hourly buckets and write to recorder.

    HA statistics require top-of-hour timestamps (minutes=0, seconds=0).
    Each messwert's zeitVon determines which hour bucket it belongs to.
    """
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
        _LOGGER.debug("Last statistic for %s: sum=%.3f kWh at %s", statistic_id, last_sum, last_dt)

    # Aggregate 15-min values into hourly buckets (HA requires top-of-hour timestamps)
    hourly_wh: dict[datetime, float] = defaultdict(float)

    for m in messwerte:
        try:
            if m.get("qualitaet") not in ("VAL", "EST", None, ""):
                continue

            # Use zeitVon to determine the hour; fall back to zeitBis - 15 min
            if "zeitVon" in m:
                zeit_von = datetime.fromisoformat(m["zeitVon"].replace("Z", "+00:00"))
            else:
                zeit_bis = datetime.fromisoformat(m["zeitBis"].replace("Z", "+00:00"))
                zeit_von = zeit_bis - timedelta(minutes=15)

            hour_start = zeit_von.replace(minute=0, second=0, microsecond=0)
            hourly_wh[hour_start] += float(m["messwert"])

        except Exception as exc:
            _LOGGER.warning("Error processing messwert %s: %s", m, exc)

    # Build StatisticData list — only new hourly entries
    statistics: list[StatisticData] = []
    running_sum = last_sum

    for hour_start in sorted(hourly_wh.keys()):
        if last_dt and hour_start <= last_dt:
            continue

        kwh_value = hourly_wh[hour_start] / 1000.0
        running_sum += kwh_value
        statistics.append(StatisticData(start=hour_start, state=kwh_value, sum=running_sum))

    if not statistics:
        _LOGGER.debug("No new statistics to insert for %s", statistic_id)
        return

    async_add_external_statistics(hass, _make_metadata(statistic_id, name), statistics)
    _LOGGER.info(
        "Inserted %d hourly statistics for %s (sum now: %.3f kWh)",
        len(statistics), statistic_id, running_sum,
    )


async def async_backfill_statistics(
    hass: HomeAssistant,
    client,
    zp_nummer: str,
    days: int = 30,
) -> None:
    """Backfill historical statistics on first setup."""
    _LOGGER.info("Starting backfill for %s (%d days)", zp_nummer, days)
    tz  = ZoneInfo(VIENNA_TZ)
    von = (datetime.now(tz) - timedelta(days=days)).strftime("%Y-%m-%d")
    bis = datetime.now(tz).strftime("%Y-%m-%d")

    try:
        raw = await hass.async_add_executor_job(
            lambda: client.get_quarter_hour_values(date_from=von, date_to=bis)
        )
    except Exception as exc:
        _LOGGER.error("Backfill fetch failed for %s: %s", zp_nummer, exc)
        return

    for zp_data in raw:
        if zp_data.get("zaehlpunkt") != zp_nummer:
            continue

        for zaehlwerk in zp_data.get("zaehlwerke", []):
            obis      = zaehlwerk.get("obisCode", "")
            messwerte = zaehlwerk.get("messwerte", [])

            if obis == OBIS_CONSUMPTION:
                stat_id   = f"{STATISTIC_ID_CONSUMPTION}_{zp_nummer.lower()}"
                stat_name = f"Smart Meter Bezug {zp_nummer[-6:]}"
            elif obis == OBIS_FEEDIN:
                stat_id   = f"{STATISTIC_ID_FEEDIN}_{zp_nummer.lower()}"
                stat_name = f"Smart Meter Einspeisung {zp_nummer[-6:]}"
            else:
                continue

            await _insert_zaehlwerk_statistics(
                hass, messwerte, statistic_id=stat_id, name=stat_name
            )

    _LOGGER.info("Backfill complete for %s", zp_nummer)
