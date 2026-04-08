"""DataUpdateCoordinator for Wiener Netze Smart Meter."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, VIENNA_TZ

_LOGGER = logging.getLogger(__name__)


class WNSmartMeterCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch data from Wiener Netze Smart Meter API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client,
        scan_interval: int,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=scan_interval),
        )
        self.client = client
        self.zaehlpunkte: list[dict] = []
        self._tz = ZoneInfo(VIENNA_TZ)

    async def _async_update_data(self) -> dict:
        """Fetch latest data from API."""
        try:
            # Fetch Zaehlpunkte on first run
            if not self.zaehlpunkte:
                self.zaehlpunkte = await self.hass.async_add_executor_job(
                    self.client.get_anlagendaten
                )
                _LOGGER.debug("Fetched %d Zaehlpunkte", len(self.zaehlpunkte))

            # Fetch quarter hour values for yesterday and today
            heute   = datetime.now(self._tz).strftime("%Y-%m-%d")
            gestern = (datetime.now(self._tz) - timedelta(days=1)).strftime("%Y-%m-%d")

            raw = await self.hass.async_add_executor_job(
                lambda: self.client.get_quarter_hour_values(
                    date_from=gestern,
                    date_to=heute,
                )
            )

            return self._parse(raw)

        except Exception as exc:
            raise UpdateFailed(f"Error fetching Smart Meter data: {exc}") from exc

    def _parse(self, raw: list) -> dict:
        """Parse API response into structured data."""
        result = {}

        for zp_data in raw:
            zp_nummer = zp_data.get("zaehlpunkt", "unknown")
            result[zp_nummer] = {
                "zaehlpunkt": zp_nummer,
                "zaehlwerke": {},
            }

            for zaehlwerk in zp_data.get("zaehlwerke", []):
                obis      = zaehlwerk.get("obisCode", "unknown")
                einheit   = zaehlwerk.get("einheit", "WH")
                messwerte = zaehlwerk.get("messwerte", [])

                if not messwerte:
                    continue

                # Latest reading
                latest = messwerte[-1]

                # Total for today (MESZ aware)
                heute_str = datetime.now(self._tz).strftime("%Y-%m-%d")
                tages_wh  = sum(
                    m["messwert"]
                    for m in messwerte
                    if self._is_today(m["zeitBis"], heute_str)
                )

                result[zp_nummer]["zaehlwerke"][obis] = {
                    "obisCode":        obis,
                    "einheit":         einheit,
                    "latest_messwert": latest["messwert"],
                    "latest_zeitBis":  latest["zeitBis"],
                    "latest_qualitaet": latest.get("qualitaet", ""),
                    "tagesverbrauch_wh": tages_wh,
                    "messwerte":       messwerte,
                }

        return result

    def _is_today(self, zeit_bis_utc: str, heute_local: str) -> bool:
        """Check if a UTC timestamp falls on today in Vienna time."""
        try:
            dt = datetime.fromisoformat(zeit_bis_utc.replace("Z", "+00:00"))
            dt_local = dt.astimezone(self._tz)
            return dt_local.strftime("%Y-%m-%d") == heute_local
        except Exception:
            return False

    def get_latest_timestamp_local(self, zeit_bis_utc: str) -> datetime:
        """Convert UTC zeitBis to Vienna local datetime."""
        dt = datetime.fromisoformat(zeit_bis_utc.replace("Z", "+00:00"))
        return dt.astimezone(self._tz)
