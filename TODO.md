# Roadmap / TODO

Jeder Schritt ist ein eigener Commit. Nach einer Unterbrechung: `git log --oneline` und diese Liste prüfen, beim ersten offenen Punkt der höchsten Priorität weitermachen und danach `pytest` laufen lassen.

## Erledigt (v0.1.0)

- [x] Lokaler DAQ-Datenstrom, Cloud-Steuerung, Verbrauchsmodell, Config-/Options-/Reauth-/Reconfigure-Flow, Diagnose, Übersetzungen de/en
- [x] Bekannte Cloud-Parameter: Kesselprogramm, Warmwasser-Soll, Raumtemperatur-Korrektur, Heizkurve Fußboden
- [x] Buttons für Cloud-Aktionen (Puffer/Warmwasser zwangsladen, Zirkulation einmalig)
- [x] Modell und Nennleistung aus dem Cloud-Gerätetyp
- [x] README mit Hinweis „ungetestet / vibecoded“, öffentliches Repo

## P1: vor dem ersten Test am echten Kessel

- [x] **DAQ-Datei auswerten** (Eco-HK 50, V30.0HAR.f): 133 Analogkanäle und 8 Digitalworte (32 Bit) → 141 Werte pro Zeile. Kanalnamen in `channels.py` zugeordnet, Test-Fixture `tests/fixtures/eco_hk_50_v30.0HAR.f.xml` (nur `<DAQPRJ>`-Block).
- [ ] **`Lagerstand HK` [m³] der Steuerung nutzen:** Kanal 132. Erscheint **nicht durch das Firmware-Update**: DAQ02787 (V30.0HAR.f, 30.10. 0:00) hat ihn noch nicht, DAQ02788 (30.10. ab 7:46, gleiche Firmware) schon. Ursache bestätigt: Der Kanal existiert nur, solange am Kessel die **Lagerbestandsberechnung** aktiv ist. Der Nutzer hat sie testweise aktiviert (Meldung „Lager leer“) und wieder deaktiviert. Beide Varianten liegen als Fixture vor (140 bzw. 141 Werte). Solange die Funktion aus ist, bleibt das eigene Verbrauchsmodell die Quelle für den Lagerstand. Prüfen, ob die Steuerung den Lagerstand selbst führt (Wert am Display vergleichen). Wenn ja, als Quelle für Lagerstand und Reichweite verwenden und das eigene Modell nur noch für Wärme und Verbrauch nutzen.
- [ ] **Bedeutung unsicherer Kanäle klären:** GBF (Glutbett, Einheit °), PLK/TLK (Luftklappen?), ER/AR Run (Einschub-/Ascherost?), Effizienz. Abgleich mit dem Display bzw. der PARAMLOG des Kessels.
- [ ] **Cloud-Schreibzugriff absichern:** Option „Werte über die Cloud ändern erlauben“, standardmäßig **aus**. Solange die Integration ungetestet ist, soll sie nicht versehentlich Sollwerte oder das Kesselprogramm ändern.
- [ ] **Nur eine Telnet-Verbindung:** Prüfen, ob der Touch-Tronic parallele Verbindungen erlaubt. Falls nicht, im Reconfigure-Flow den laufenden Client wiederverwenden, statt eine zweite Verbindung zu öffnen.
- [ ] **Hintergrund-Task sauber anbinden:** `entry.async_create_background_task` statt `asyncio.create_task` verwenden, damit HA den Task beim Herunterfahren zuverlässig beendet.
- [x] **Code-Review** (`/code-review high`, 30.10.): 10 Befunde
- [ ] **Review-Befunde beheben:** (1) Fuel-Store wird bei laufendem Brenner nie gespeichert, (2) Reconfigure aktualisiert die unique_id nicht, (3) Diagnose zeigt den Anlagennamen, (4) Telnet-Task läuft bei Setup-Fehler weiter, (5) Climate „Aus“ wird still zu Automatik, (6) Widget-ID-Kollisionen, (7) kaputte Cloud-Antworten als unbekannter Fehler, (8) ValueError im Config-Flow, (9) Host nicht getrimmt, (10) doppeltes Neuladen

## P2: während und nach dem ersten Test

- [ ] **Zustands- und Störungscodes verifizieren:** Rohcodes über einige Tage beobachten (Attribut `code`) und mit der Anzeige am Touch-Tronic abgleichen. `BOILER_STATES` und `ERRORS_*` für den HK korrigieren.
- [ ] **Raumtemperatur aus `measurements`:** Das Widget liefert `room_temperature_current = null`, die Messwerte enthalten sie aber. Climate soll den Messwert verwenden.
- [ ] **Verbrauchsmodell kalibrieren:** Nach der nächsten Hackgut-Lieferung berechnete und tatsächliche Menge vergleichen, die Standardwerte für Heizwert und Schüttdichte prüfen.
- [ ] **Cloud-Leistung als Ersatz:** Fällt der lokale Datenstrom aus, die Verbrauchsberechnung mit `heater.efficiency` (= Leistung %, 5-Minuten-Raster) weiterführen.
- [ ] **Reparatur-Hinweis bei Template-Abweichung (wichtig):** Die Kanalliste ändert sich nicht nur bei Firmware-Updates, sondern auch durch Einstellungen am Kessel (belegt: +1 Kanal bei gleicher Firmware). Passt der Datenstrom dauerhaft nicht, ein HA-Repair-Issue mit Verweis auf „Neu konfigurieren“ anlegen und die Anzahl erwarteter und empfangener Werte nennen.
- [ ] **Betriebsstunden:** Der Kopfteil der DAQ-Datei enthält Zähler (STEUERUNG, HEIZUNG, ZUENDUNG, SAUGZUG, EINSCHUB, AUSTRAG …). Prüfen, ob dieselben Werte im Telnet-Strom stehen (`BSZ_*`-Kanäle). Sonst beim Neu-Einlesen des Templates als Momentaufnahme übernehmen.
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
