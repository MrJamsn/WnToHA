# Wiener Netze Smart Meter - Home Assistant Integration

Custom Integration fur Home Assistant zur Einbindung des Wiener Netze Smart Meters uber die offizielle Public API.

## Features

- Viertelstunden-Messwerte mit korrektem Timestamp (Vienna/MESZ)
- Tagesverbrauch als Sensor
- Historische 15-Min Werte direkt in den HA Recorder (letzte 30 Tage beim Setup)
- Vollstandige Integration ins Energy Dashboard
- Einspeisung (falls vorhanden)
- Keine Web-Scraping-Abhangigkeiten - nutzt die offizielle API

## Voraussetzungen

Zugang zur offiziellen Wiener Netze Smart Meter Public API:

1. Account im [WSTW Developer Portal](https://api-portal.wienerstadtwerke.at/)
2. Applikation fur `WN_SMART_METER_API` anlegen
3. E-Mail an [support.sm-portal@wienit.at](mailto:support.sm-portal@wienit.at) zur Verknupfung mit dem Smart Meter Portal
4. Nach Bestatigung:
   - **API Key** aus dem WSTW Developer Portal
   - **Client ID + Client Secret** aus [smartmeter-business.wienernetze.at/einstellungen](https://smartmeter-business.wienernetze.at/einstellungen)

## Installation

### Via HACS (empfohlen)

1. HACS offnen -> Integrationen -> 3-Punkte-Menu -> Custom Repositories
2. URL: `https://github.com/YOUR_USERNAME/wienernetze-smartmeter-ha`
3. Kategorie: Integration
4. Installieren
5. HA neu starten

### Manuell

`custom_components/wienernetze_smartmeter/` in dein HA `config/custom_components/` Verzeichnis kopieren und HA neu starten.

## Konfiguration

Einstellungen -> Gerate & Dienste -> Integration hinzufugen -> "Wiener Netze Smart Meter"

| Feld | Quelle |
|------|--------|
| Client ID | smartmeter-business.wienernetze.at/einstellungen |
| Client Secret | smartmeter-business.wienernetze.at/einstellungen |
| API Key | api-portal.wienerstadtwerke.at -> Applikation -> Details |
| Intervall | 15-60 Minuten (Standard: 30) |

## Sensoren

| Sensor | Einheit | Beschreibung |
|--------|---------|--------------|
| Smart Meter Bezug Viertelstunde | kWh | Letzter 15-Min Wert |
| Smart Meter Bezug Tagesverbrauch | kWh | Summe des aktuellen Tages |
| Smart Meter Einspeisung Viertelstunde | kWh | Einspeisung (falls vorhanden) |

## Energy Dashboard

Die Integration schreibt 15-Min Werte mit dem korrekten Originaltimestamp (`zeitBis`) in den HA Recorder. Beim ersten Setup werden automatisch die letzten 30 Tage nachgeladen.

Im Energy Dashboard: Einstellungen -> Energy -> Netzverbrauch -> Sensor hinzufugen -> `sensor.smart_meter_bezug_tagesverbrauch_*`

## Hinweise

- Wiener Netze liefert Messwerte typischerweise mit 1-24h Verzogerung
- Timestamps sind immer in Europe/Vienna (MESZ-aware)
- Token-Erneuerung erfolgt automatisch (Token gultig 3600s)

## Lizenz

MIT
