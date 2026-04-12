# Wiener Netze Smart Meter - Home Assistant Integration

> **Hinweis:** Diese Integration wurde vibe-coded – mit Unterstützung von KI-Tools entwickelt. Der Code funktioniert, aber lies ihn mit gesundem Menschenverstand. ;)

Custom Integration für Home Assistant zur Einbindung des Wiener Netze Smart Meters über die offizielle Public API.

## Features

- Viertelstunden-Messwerte mit **korrektem Original-Timestamp** (Europe/Vienna, MESZ-aware)
- Tagesverbrauch als Sensor
- Historische Daten direkt in den HA Recorder (konfigurierbar: 30 Tage bis 3 Jahre)
- Vollständige Integration ins Energy Dashboard
- Einspeisung (falls vorhanden)
- Keine externen Python-Abhängigkeiten – nutzt die offizielle API direkt

## Wichtig: Keine Live-Daten

> Wiener Netze liefert Messwerte **nicht in Echtzeit**. Die Daten kommen typischerweise mit **12–48 Stunden Verzögerung** an.

Das bedeutet konkret:

- Die Sensoren in Home Assistant zeigen immer den **zuletzt verfügbaren** Messwert – das kann der Verbrauch von gestern oder vorgestern sein
- Die **Uhrzeit und das Datum der Messung stimmen jedoch exakt** – ein Wert der um 14:15 Uhr gemessen wurde, erscheint im Energy Dashboard auch mit Timestamp 14:15 Uhr, egal wann er tatsächlich bei HA ankam
- Das Energy Dashboard zeigt die Daten daher immer mit ein bis zwei Tagen Rückstand, aber mit korrekter zeitlicher Zuordnung

Das ist keine Einschränkung dieser Integration, sondern eine Eigenschaft der Wiener Netze API.

## Voraussetzungen

Zugang zur offiziellen Wiener Netze Smart Meter Public API:

1. Account im [WSTW Developer Portal](https://api-portal.wienerstadtwerke.at/)
2. Applikation für `WN_SMART_METER_API` anlegen
3. E-Mail an [support.sm-portal@wienit.at](mailto:support.sm-portal@wienit.at) zur Verknüpfung mit dem Smart Meter Portal
4. Nach Bestätigung:
   - **API Key** aus dem WSTW Developer Portal
   - **Client ID + Client Secret** aus [smartmeter-business.wienernetze.at/einstellungen](https://smartmeter-business.wienernetze.at/einstellungen)

## Installation

### Via HACS (empfohlen)

1. HACS öffnen → Integrationen → 3-Punkte-Menü → Custom Repositories
2. URL: `https://github.com/MrJamsn/WnToHA`
3. Kategorie: Integration
4. Installieren
5. HA neu starten

### Manuell

`custom_components/wienernetze_smartmeter/` in dein HA `config/custom_components/` Verzeichnis kopieren und HA neu starten.

## Konfiguration

Einstellungen → Geräte & Dienste → Integration hinzufügen → "Wiener Netze Smart Meter"

| Feld | Pflicht | Beschreibung |
|------|---------|--------------|
| Client ID | Ja | smartmeter-business.wienernetze.at/einstellungen |
| Client Secret | Ja | smartmeter-business.wienernetze.at/einstellungen |
| API Key | Ja | api-portal.wienerstadtwerke.at → Applikation → Details |
| Zählerpunktnummer | Nein | Spezifischen Zählerpunkt auswählen (leer = alle) |
| Aktualisierungsintervall | Nein | 15–60 Minuten (Standard: 30) |
| Historische Daten | Nein | 30 / 90 / 365 / 1095 Tage (Standard: 1095 = ~3 Jahre) |

## Energy Dashboard einrichten

Das ist der wichtigste Schritt nach der Installation:

1. **Einstellungen → Energie → Netzverbrauch → Hinzufügen**
2. Im Suchfeld **"Smart"** eingeben
3. Die Statistik **`Smart Meter Bezug xxxxxx`** auswählen

> **Wichtig:** Nicht die Entität `sensor.smart_meter_...` wählen, sondern die Statistik mit dem Namen `Smart Meter Bezug ...`. Nur diese hat korrekte Timestamps.

Nach dem ersten Setup lädt die Integration automatisch historische Daten nach (je nach gewähltem Zeitraum kann das einige Minuten dauern). Die Daten erscheinen dann rückwirkend mit den korrekten Original-Timestamps im Energy Dashboard.

## Sensoren

| Sensor | Einheit | Beschreibung |
|--------|---------|--------------|
| Smart Meter Bezug Viertelstunde | kWh | Letzter verfügbarer 15-Min-Wert |
| Smart Meter Bezug Tagesverbrauch | kWh | Summe aller heutigen Messwerte |
| Smart Meter Einspeisung Viertelstunde | kWh | Einspeisung (falls vorhanden) |

Die Sensoren aktualisieren sich nur dann, wenn tatsächlich ein neuer Messwert von der API kommt (erkennbar am geänderten Timestamp). Bleibt der Wert gleich, schreibt die Integration nichts in die HA-History.

## Hinweise

- Messwerte kommen stündlich aggregiert in den HA Recorder (HA-Anforderung)
- Token-Erneuerung erfolgt automatisch (gültig 300 Sekunden)
- Bei mehreren Zählerpunkten werden alle automatisch erkannt

## Danksagung

Ein großes Dankeschön an [tschoerk/Wiener-Netze-Smart-Meter-API](https://github.com/tschoerk/Wiener-Netze-Smart-Meter-API) – dieses Repo war der Ausgangspunkt und die Inspiration für diese Integration.

## Lizenz

MIT
