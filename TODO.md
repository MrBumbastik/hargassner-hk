# Roadmap / TODO

Jeder Schritt ist ein eigener Commit. Nach einer Unterbrechung: `git log --oneline` und diese Liste prüfen, beim ersten offenen Punkt der höchsten Priorität weitermachen und danach `pytest` laufen lassen.

## Erledigt (v0.1.0)

- [x] Lokaler DAQ-Datenstrom, Cloud-Steuerung, Verbrauchsmodell, Config-/Options-/Reauth-/Reconfigure-Flow, Diagnose, Übersetzungen de/en
- [x] Bekannte Cloud-Parameter: Kesselprogramm, Warmwasser-Soll, Raumtemperatur-Korrektur, Heizkurve Fußboden
- [x] Buttons für Cloud-Aktionen (Puffer/Warmwasser zwangsladen, Zirkulation einmalig)
- [x] Modell und Nennleistung aus dem Cloud-Gerätetyp
- [x] README mit Hinweis „ungetestet / vibecoded“, öffentliches Repo

## P1: vor dem ersten Test am echten Kessel

- [ ] **DAQ-Datei auswerten** (Eco-HK 50, V30.0HAR.f): Kanalnamen in `channels.py` zuordnen, Hackgut-Kanäle identifizieren (Austragung, Schieberost, Asche, Unterdruck …), anonymisiertes Test-Fixture mit echter Kanalstruktur bauen.
- [ ] **Cloud-Schreibzugriff absichern:** Option „Werte über die Cloud ändern erlauben“, standardmäßig **aus**. Solange die Integration ungetestet ist, soll sie nicht versehentlich Sollwerte oder das Kesselprogramm ändern.
- [ ] **Nur eine Telnet-Verbindung:** Prüfen, ob der Touch-Tronic parallele Verbindungen erlaubt. Falls nicht, im Reconfigure-Flow den laufenden Client wiederverwenden, statt eine zweite Verbindung zu öffnen.
- [ ] **Hintergrund-Task sauber anbinden:** `entry.async_create_background_task` statt `asyncio.create_task` verwenden, damit HA den Task beim Herunterfahren zuverlässig beendet.
- [ ] **Code-Review des vibecodeten Stands** (`/code-review high`), Funde beheben.

## P2: während und nach dem ersten Test

- [ ] **Zustands- und Störungscodes verifizieren:** Rohcodes über einige Tage beobachten (Attribut `code`) und mit der Anzeige am Touch-Tronic abgleichen. `BOILER_STATES` und `ERRORS_*` für den HK korrigieren.
- [ ] **Raumtemperatur aus `measurements`:** Das Widget liefert `room_temperature_current = null`, die Messwerte enthalten sie aber. Climate soll den Messwert verwenden.
- [ ] **Verbrauchsmodell kalibrieren:** Nach der nächsten Hackgut-Lieferung berechnete und tatsächliche Menge vergleichen, die Standardwerte für Heizwert und Schüttdichte prüfen.
- [ ] **Cloud-Leistung als Ersatz:** Fällt der lokale Datenstrom aus, die Verbrauchsberechnung mit `heater.efficiency` (= Leistung %, 5-Minuten-Raster) weiterführen.
- [ ] **Reparatur-Hinweis bei Template-Abweichung:** Passt der Datenstrom dauerhaft nicht zum Template (z. B. nach einem Firmware-Update), ein HA-Repair-Issue mit Verweis auf „Neu konfigurieren“ anlegen.
- [ ] **Recorder-Last prüfen:** Wie viele Entitäten sind aktiv, wie groß wird die Datenbank? Gegebenenfalls weitere Kanäle standardmäßig deaktivieren.

## P3: Qualität und Veröffentlichung

- [ ] **Tests ergänzen:** Cloud-Client (Login, Token-Refresh, 401-Wiederholung), Reauth-, Reconfigure- und Options-Flow, Diagnose, Climate. Ziel: über 90 % Abdeckung, kein Modul unter 80 %.
- [ ] **CI mit GitHub Actions:** `hassfest`, HACS-Validierung (`hacs/action`), `pytest`, `ruff`. Das läuft bei jedem Push.
- [ ] **Lizenz festlegen** (z. B. MIT oder Apache-2.0).
- [ ] **Releases:** Versionsnummer in `manifest.json`, Git-Tag und GitHub-Release mit Changelog. HACS zeigt Releases als Updates an.
- [ ] **Brand-Icon:** Logo für die Integrationsliste in HA und HACS (Pull Request an `home-assistant/brands`, Markenrechte von Hargassner beachten).
- [ ] **Config-Entry-Migration vorbereiten:** Entity-IDs hängen an Kanalnamen. Benennt eine neue Firmware Kanäle um, sollen Verläufe über `async_migrate_entry` erhalten bleiben.

## Später / Ideen

- [ ] Zeitprogramme (Heizzeiten, Warmwasser, Zirkulation) lesen und anzeigen, eventuell als HA-Kalender
- [ ] Störungsverlauf aus `/installations/{id}/events` als HA-Ereignisse (Logbuch, Automationen)
- [ ] Reiner Cloud-Modus für Anlagen ohne LAN-Zugang (mit 5-Minuten-Raster)
- [ ] Beispiel-Dashboard (Lovelace) für Kessel, Puffer und Lager
- [ ] Unterstützung weiterer Hargassner-Hackgutkessel (Magna, WTH) über Nutzer-Templates

## Erkenntnisse aus der Cloud-API (Eco-HK 50, Firmware V30.0HAR.f)

- Für Kundenkonten freigegeben: `/installations/{id}/widgets`, `/devices/{id}/metric-fields`, `/devices/{id}/measurements`, `/installations/{id}/events`. Gesperrt (403): `/devices/{id}/parameters`, `/installations/{id}/devices/{id}/features`.
- Keine Hackgut-Kanäle in der Cloud (kein Saugzug, keine Austragung, Asche oder Motorströme). `heater.fuel_stock` ist beim HK `null`. Hackgut-Werte gibt es nur lokal (DAQ).
- `heater.efficiency` ist laut Web-App die **Leistung in %**, nicht der Wirkungsgrad.
- Widgets: HEATER (`program`: PROGRAM_OFF/BOILER/AUTOMATIC/STOP_FIRING), BUFFER (Aktion `force_charging`), HEATING_CIRCUIT_RADIATOR/FLOOR (`room_temperature_correction`, `steepness` bzw. `steepness_floor`), BOILER (`boiler_temperature_target`, Aktionen `force_charging`, `one_time_circulation`).
- Aktionen: POST auf `actions.<name>.resource`. Die Web-App schreibt Parameter auch über `PATCH /devices/{id}/parameters/{p}` mit `If-Match`-ETag. Ob das für Kundenkonten erlaubt ist, wurde nicht geprüft (nur das Lesen der Liste ergab 403).
- Der Gerätetyp steht in `installations[].devices[].type` (z. B. „Eco-HK 50“).
- Die Cloud aktualisiert alle 300 s (`meta.refresh`).
