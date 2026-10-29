# Fortschritt / TODO

Jeder Schritt ist ein eigener Commit. Nach Abbruch: `git log --oneline` und diese Liste prüfen, beim ersten offenen Punkt weitermachen, danach `pytest` laufen lassen.

## Erkenntnisse aus der Cloud-API (Eco-HK 50, Firmware V30.0HAR.f)

- Kundenkonto darf: `/installations/{id}/widgets`, `/devices/{id}/metric-fields`, `/devices/{id}/measurements`, `/installations/{id}/events`. Gesperrt (403): `/devices/{id}/parameters`, `/installations/{id}/devices/{id}/features`.
- Keine Hackgut-Kanäle in der Cloud (kein Saugzug, Austragung, Asche, Motorströme). `heater.fuel_stock` ist beim HK `null`. Hackgut-Werte gibt es nur lokal (DAQ).
- `heater.efficiency` ist laut Web-App die **Leistung in %**, nicht der Wirkungsgrad.
- Widgets: HEATER (Parameter `program`: PROGRAM_OFF/BOILER/AUTOMATIC/STOP_FIRING), BUFFER (Aktion `force_charging`), HEATING_CIRCUIT_RADIATOR/FLOOR (`room_temperature_correction`, `steepness` bzw. `steepness_floor`), BOILER (`boiler_temperature_target`, Aktionen `force_charging`, `one_time_circulation`).
- Aktionen: POST auf `actions.<name>.resource`.
- Geräte-Typ steht in `installations[].devices[].type` (z. B. "Eco-HK 50").

## Schritte

- [x] 0. Ausgangsstand committen
- [ ] 1. Bekannte Cloud-Parameter: `program` (Select), `boiler_temperature_target`, `room_temperature_correction`, `steepness_floor` (Number) mit Übersetzungen; Tests
- [ ] 2. Button-Plattform für Cloud-Aktionen (`force_charging`, `one_time_circulation`); Tests
- [ ] 3. Nennleistung aus Gerätetyp ableiten ("Eco-HK 50" → 50 kW) im Config-Flow als Vorgabe; Tests
- [ ] 4. README aktualisieren (Cloud-Erkenntnisse, `efficiency` = Leistung)
- [ ] 5. (später, nach lokalem Test) Cloud-Leistung als Ersatz für Verbrauchsberechnung
- [ ] 6. (morgen) DAQ-Datei des Nutzers auswerten, `channels.py` anpassen, Test-Fixture daraus (anonymisiert)
