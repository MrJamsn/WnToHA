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


def _aggregate_to_hourly(messwerte: list) -> dict[datetime, float]:
    """Aggregate 15-min messwerte into hourly buckets (values in Wh)."""
    hourly_wh: dict[datetime, float] = defaultdict(float)
    for m in messwerte:
        try:
            if m.get("qualitaet") not in ("VAL", "EST", None, ""):
                continue

            if "zeitVon" in m:
                zeit_von = datetime.fromisoformat(m["zeitVon"].replace("Z", "+00:00"))
            else:
                zeit_bis = datetime.fromisoformat(m["zeitBis"].replace("Z", "+00:00"))
                zeit_von = zeit_bis - timedelta(minutes=15)

            hour_start = zeit_von.replace(minute=0, second=0, microsecond=0)
            hourly_wh[hour_start] += float(m["messwert"])

        except Exception as exc:
            _LOGGER.warning("Error processing messwert %s: %s", m, exc)

    return hourly_wh


async def async_insert_statistics(
    hass: HomeAssistant,
    coordinator,
    zp_nummer: str,
) -> None:
    """Insert hourly statistics for one Zaehlpunkt into HA recorder (incremental)."""
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
    """Aggregate 15-min messwerte into hourly buckets and append new entries only.

    Used for incremental updates from the coordinator. Skips entries already
    in the database (based on last_dt) to avoid duplicate writes.
    """
    if not messwerte:
        return

    # Get last stored statistic to continue the cumulative sum
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

    hourly_wh = _aggregate_to_hourly(messwerte)

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


async def _write_full_statistics(
    hass: HomeAssistant,
    messwerte: list,
    statistic_id: str,
    name: str,
) -> None:
    """Write all messwerte as statistics with cumulative sum starting from zero.

    Unlike _insert_zaehlwerk_statistics, this writes ALL entries regardless of
    what is already stored. Used for backfill so that historical data is never
    skipped. HA will upsert existing entries with the same start timestamp.
    """
    if not messwerte:
        return

    hourly_wh = _aggregate_to_hourly(messwerte)

    if not hourly_wh:
        return

    statistics: list[StatisticData] = []
    running_sum = 0.0

    for hour_start in sorted(hourly_wh.keys()):
        kwh_value = hourly_wh[hour_start] / 1000.0
        running_sum += kwh_value
        statistics.append(StatisticData(start=hour_start, state=kwh_value, sum=running_sum))

    async_add_external_statistics(hass, _make_metadata(statistic_id, name), statistics)
    _LOGGER.info(
        "Backfill: wrote %d hourly statistics for %s (total sum: %.3f kWh)",
        len(statistics), statistic_id, running_sum,
    )


async def async_backfill_statistics(
    hass: HomeAssistant,
    client,
    zp_nummer: str,
    days: int = 1095,
    chunk_days: int = 90,
) -> None:
    """Backfill historical statistics, chunked to avoid API timeouts.

    Collects all messwerte across all chunks first, then writes everything
    at once with a fresh cumulative sum starting from zero. This avoids the
    last_dt deduplication bug where incremental inserts (called during setup)
    set last_dt=today, causing all historical chunks to be skipped.
    """
    _LOGGER.info("Starting backfill for %s (%d days, chunks of %d)", zp_nummer, days, chunk_days)
    tz = ZoneInfo(VIENNA_TZ)
    end_date   = datetime.now(tz).date()
    start_date = end_date - timedelta(days=days)

    # Accumulate all messwerte across every chunk, keyed by OBIS code
    all_messwerte: dict[str, list] = {OBIS_CONSUMPTION: [], OBIS_FEEDIN: []}

    chunk_start = start_date
    while chunk_start < end_date:
        chunk_end = min(chunk_start + timedelta(days=chunk_days), end_date)
        von = chunk_start.strftime("%Y-%m-%d")
        bis = chunk_end.strftime("%Y-%m-%d")

        try:
            raw = await hass.async_add_executor_job(
                lambda v=von, b=bis: client.get_quarter_hour_values(date_from=v, date_to=b)
            )
        except Exception as exc:
            _LOGGER.error("Backfill chunk %s–%s failed for %s: %s", von, bis, zp_nummer, exc)
            chunk_start = chunk_end
            continue

        for zp_data in raw:
            if zp_data.get("zaehlpunkt") != zp_nummer:
                continue
            for zaehlwerk in zp_data.get("zaehlwerke", []):
                obis = zaehlwerk.get("obisCode", "")
                if obis in all_messwerte:
                    all_messwerte[obis].extend(zaehlwerk.get("messwerte", []))

        _LOGGER.debug("Backfill chunk %s–%s fetched for %s", von, bis, zp_nummer)
        chunk_start = chunk_end

    # Write each OBIS code's full history in one shot (cumulative sum from 0)
    for obis, messwerte in all_messwerte.items():
        if not messwerte:
            continue

        if obis == OBIS_CONSUMPTION:
            stat_id   = f"{STATISTIC_ID_CONSUMPTION}_{zp_nummer.lower()}"
            stat_name = f"Smart Meter Bezug {zp_nummer[-6:]}"
        else:
            stat_id   = f"{STATISTIC_ID_FEEDIN}_{zp_nummer.lower()}"
            stat_name = f"Smart Meter Einspeisung {zp_nummer[-6:]}"

        await _write_full_statistics(hass, messwerte, statistic_id=stat_id, name=stat_name)

    _LOGGER.info("Backfill complete for %s", zp_nummer)
