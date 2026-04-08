"""Constants for the Wiener Netze Smart Meter integration."""

DOMAIN = "wienernetze_smartmeter"
DEFAULT_SCAN_INTERVAL = 30  # minutes

VIENNA_TZ = "Europe/Vienna"

# OBIS codes
OBIS_CONSUMPTION = "1-1:1.9.0"   # Bezug (Wh)
OBIS_FEEDIN      = "1-1:2.9.0"   # Einspeisung (Wh) - falls vorhanden

STATISTIC_ID_CONSUMPTION = f"{DOMAIN}:energy_consumption"
STATISTIC_ID_FEEDIN      = f"{DOMAIN}:energy_feedin"
