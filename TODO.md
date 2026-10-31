# Roadmap / TODO

Jeder Schritt ist ein eigener Commit. Nach einer Unterbrechung: `git log --oneline` und diese Liste prüfen, beim ersten offenen Punkt der höchsten Priorität weitermachen und danach `pytest` laufen lassen.

## Beta → 1.0 (Stand v0.9.0, 30.10.2026)

Die Integration hat am Eco-HK 50 des Autors die beiden bisherigen Integrationen abgelöst (Dashboards, Energie-Dashboard). Für 1.0 fehlt:

- [x] **Kaltstart mitgeschnitten (31.10., v0.9.1):** Mitschnitt `~/hargassner-daq/kaltstart_2026-10-31.csv` mit Displayfotos abgeglichen (Displayuhr ca. 3 min vor). 9 → 3 „Zündung Start“ (~15 s, Saugzug spült, Förderung startet) → 4 „Zündung“ (zuerst „Brennk. füllen“: Einschub ~2,5 min; dann Zündheizung + Gebläse ~6 min) → 5 „Leistungsbrand“ (Leistung springt auf 100 %, F2-Bit ~15 s später). Vom Startsignal bis Leistungsbrand ~7,5 min.
- [x] **Zustandstabelle aus dem Service-Handbuch (v0.10.0):** Kap. 4.2 „Betriebszustände“ (Analogausgang Klemme 78/79): 1 AUS, 3 ZUENDPROBE, 4 ZUENDUNG, 5 LEISTUNGSBRAND, 6 GLUTERHALTUNG, 7 AUSBRAND, 9 ENTASCHUNG, 10 STB, 11 HAND, 12 STUECKHOLZ_NOTBETRIEB. Damit sind Code 7 (Abbrand) und Code 9 (Entaschung) geklärt.
- [ ] **Code 7 = Abbrand am Display bestätigen.**
- [x] **Störungstexte Eco-HK (v0.10.0):** 418 Codes aus der Meldungsliste des Service-Handbuchs (`errors_eco_hk.py`, nur Nr. + Text). Handbuch und Auszug mit Ursache/Lösung liegen lokal in `~/hargassner-docs/` (nicht ins Repo, Urheberrecht).
- [ ] Bei der ersten echten Störung Code und Displaytext abgleichen.
- [ ] **Betriebsstunden gegen das Display prüfen:** Startwerte stammen aus der DAQ-Kopfzeile (30.10. früh) und sind vermutlich 1–2 h zu niedrig; nach einigen Tagen Zuwachs vergleichen.
- [ ] **1–2 Wochen Dauerbetrieb ohne Auffälligkeiten:** Telnet-Reconnect, HA-/Kesselneustart, Token-Refresh, Hackgut-Bilanz.
- [ ] Danach Release 1.0.0 und Hinweis „Beta“ im README entfernen.

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
- [x] **Cloud-Schreibzugriff absichern (30.10.):** Option „Werte über die Cloud ändern erlauben“, standardmäßig **aus**. Solange die Integration ungetestet ist, soll sie nicht versehentlich Sollwerte oder das Kesselprogramm ändern.
- [ ] **Nur eine Telnet-Verbindung:** Prüfen, ob der Touch-Tronic parallele Verbindungen erlaubt. Falls nicht, im Reconfigure-Flow den laufenden Client wiederverwenden, statt eine zweite Verbindung zu öffnen.
- [ ] **Hintergrund-Task sauber anbinden:** `entry.async_create_background_task` statt `asyncio.create_task` verwenden, damit HA den Task beim Herunterfahren zuverlässig beendet.
- [x] **Code-Review** (`/code-review high`, 30.10.): 10 Befunde
- [x] **Review-Befunde behoben (30.10.):** (1) Fuel-Store wird bei laufendem Brenner nie gespeichert, (2) Reconfigure aktualisiert die unique_id nicht, (3) Diagnose zeigt den Anlagennamen, (4) Telnet-Task läuft bei Setup-Fehler weiter, (5) Climate „Aus“ wird still zu Automatik, (6) Widget-ID-Kollisionen, (7) kaputte Cloud-Antworten als unbekannter Fehler, (8) ValueError im Config-Flow, (9) Host nicht getrimmt, (10) doppeltes Neuladen

## P2: während und nach dem ersten Test

- [~] **Zustandscodes ZK beim Eco-HK (v0.8.0):** 1 = Aus, 5 = Leistungsbrand (Display bestätigt), 7 = Abbrand (Mitschnitt 30.10. 18:02–20:01, `~/hargassner-daq/zk_log.csv`: Förderung 0, O₂ → 20 %, F2 fällt, dann Code 1; Displaytext noch bestätigen). Brenner aktiv = F2-Bit oder Code 5 oder Zündheizung. Wärme/Hackgut zählen Leistung nur bei Code 5 oder Förderung > 0 (Leistung meldet im Abbrand 100 %). Offen: Codes für Zündung/Start (Brennstart mitschneiden), Displaytexte.

- [x] **Betriebsstunden (v0.6.0):** pro Komponente sekundengenau aus dem Live-Strom gezählt (`runtime.py`), `total_increasing` → HA-Statistik pro Tag/Woche/Monat. „Zählerstand …“ (Startwert + gezählt, ohne Statistik) für Brenner, Zündung, Saugzug, Raumaustragung; Aktion `set_operating_hours`. Einschub-Zählerstand direkt vom Kessel (`BSZ_ES_PEL`). Offen: echte Laufzeiten im Brennbetrieb gegen Kesseldisplay prüfen.

- [ ] **Raumtemperatur TRA_x ist ohne Raumfühler ein Platzhalter (20,0 °C)**, auch bei nicht vorhandenen Heizkreisen. Sensor standardmäßig deaktivieren oder 20,0 bei fehlendem Fühler als „unbekannt“ melden. Klären, ob ein Fühler-Status existiert (FR_x Zustand?).
- [x] **Cloud nachträglich aktivieren (v0.5.0):** Neu konfigurieren → Hargassner-Cloud. Bugfix: Im Einrichtungsdialog hat ein standardmäßig ausgeschalteter Schalter eingegebene Zugangsdaten verworfen; der Schalter ist entfernt. Falsches Passwort (OAuth 400 `invalid_grant`) wird jetzt als Anmeldefehler erkannt. Live gegen das echte Konto geprüft.
  - Ursprünglich: Derzeit nur bei der Ersteinrichtung möglich. Für die Ablösung der alten Cloud-Integration (Thermostate, Sollwerte, Betriebsart) einen Weg über Reconfigure oder Optionen anbieten.

- [x] **Installation in echtem HA (30.10., v0.4.0):** über HACS, Template-Feld leer → automatisch erkannt, 0 abgelehnte Datensätze. Parallel läuft eine zweite Telnet-Integration am selben Kessel → **mehrere Telnet-Verbindungen sind möglich**.
- [ ] **Vergleich mit anderer Telnet-Integration:** Kesselzustand/-temperatur gleich; Rauchgas, Puffer oben und Außentemperatur weichen dort ab (unsere Werte sind gegen die Cloud geprüft). Nutzer entscheidet über Umstellung von Dashboards (Verlauf beachten).
- [ ] **Nennleistung ohne Cloud:** Ohne Cloud-Login bleibt der Standard 30 kW. Modell aus dem Template ableiten (z. B. Kopfzeile `KT=Eco-HK 50` der DAQ-Datei) oder Hinweis im Optionsdialog.

- [x] **DAQ-Template optional (30.10., v0.4.0):** Geprüfte Templates liegen in `custom_components/hargassner_hk/templates/`. Die Erkennung akzeptiert nur Template plus verifizierte Stromkorrektur und prüft Zustand und Kesseltemperatur auf Plausibilität. Automatisch gewählte Templates folgen Layoutänderungen selbst (3 gleich lange Zeilen nötig). Offen: verwaiste Entität „Lagerstand HK“, wenn die Lagerbestandsberechnung wieder ausgeschaltet wird.

- [x] **Erster Live-Lesetest (30.10.):** Strom erreichbar, 143 Werte statt 140 → Korrektur für 3 zusätzliche Werte (`STREAM_QUIRKS` in `daq.py`), gegen die Cloud verifiziert. Stb, NotAus und SK_* sind Ruhestromkontakte (invertiert). BRT, Wasserdruck und ATÜ liefern Platzhalter (bei Hackgut standardmäßig aus). Echte Zeile als Fixture `tests/fixtures/eco_hk_50_live_line.txt`.
- [ ] **Unsichere Position des ersten Zusatzwerts** (ExtHK-Block, Index 78–80): betrifft nur externe Heizkreise. Klären, sobald jemand mit ExtHK meldet.

- [x] **Zustands- und Störungscodes verifizieren:** für den Eco-HK aus dem Service-Handbuch übernommen (siehe oben).
- [ ] **Raumtemperatur aus `measurements`:** Das Widget liefert `room_temperature_current = null`, die Messwerte enthalten sie aber. Climate soll den Messwert verwenden.
- [ ] **Verbrauchsmodell kalibrieren:** Nach der nächsten Hackgut-Lieferung berechnete und tatsächliche Menge vergleichen, die Standardwerte für Heizwert und Schüttdichte prüfen.
- [ ] **Cloud-Leistung als Ersatz:** Fällt der lokale Datenstrom aus, die Verbrauchsberechnung mit `heater.efficiency` (= Leistung %, 5-Minuten-Raster) weiterführen.
- [ ] **Reparatur-Hinweis bei Template-Abweichung (wichtig):** Die Kanalliste ändert sich nicht nur bei Firmware-Updates, sondern auch durch Einstellungen am Kessel (belegt: +1 Kanal bei gleicher Firmware). Passt der Datenstrom dauerhaft nicht, ein HA-Repair-Issue mit Verweis auf „Neu konfigurieren“ anlegen und die Anzahl erwarteter und empfangener Werte nennen.
- [ ] **Betriebsstunden:** Der Kopfteil der DAQ-Datei enthält Zähler (STEUERUNG, HEIZUNG, ZUENDUNG, SAUGZUG, EINSCHUB, AUSTRAG …). Prüfen, ob dieselben Werte im Telnet-Strom stehen (`BSZ_*`-Kanäle). Sonst beim Neu-Einlesen des Templates als Momentaufnahme übernehmen.
- [ ] **Recorder-Last prüfen:** Wie viele Entitäten sind aktiv, wie groß wird die Datenbank? Gegebenenfalls weitere Kanäle standardmäßig deaktivieren.

## P3: Qualität und Veröffentlichung

- [ ] **Tests ergänzen:** Cloud-Client (Login, Token-Refresh, 401-Wiederholung), Reauth-, Reconfigure- und Options-Flow, Diagnose, Climate. Ziel: über 90 % Abdeckung, kein Modul unter 80 %.
- [x] **CI mit GitHub Actions (30.10.):** `hassfest`, HACS-Validierung (`hacs/action`) und `pytest` bei jedem Push auf `main` und bei Pull Requests. Lokal zusätzlich ein Pre-Commit-Hook (Tests und Prüfung auf persönliche Daten).
- [ ] **Linting:** `ruff` mit Konfiguration einführen und in die CI aufnehmen.
- [x] **Lizenz:** Apache-2.0.
- [x] **Releases (ab v0.9.0):** Versionsnummer in `manifest.json`, Git-Tag und GitHub-Release mit Changelog. HACS zeigt Releases als Updates an; Commits ohne Release erscheinen dort nicht mehr.
- [x] **Brand-Icon (v0.9.0):** eigenes Motiv (Flamme über Hackschnitzeln), kein Hargassner-Logo. Liegt in `custom_components/hargassner_hk/brand/` (neuere HA-Versionen laden es dort direkt, geprüft mit 2026.10), Quellen in `docs/logo/`.
- [ ] Optional: Icon zusätzlich an `home-assistant/brands` schicken, damit es auch HACS und ältere HA-Versionen zeigen.
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
