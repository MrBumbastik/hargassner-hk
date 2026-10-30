# Hargassner HK – Home Assistant Integration für Hackgutkessel

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
![Status](https://img.shields.io/badge/Status-ungetestet-red.svg)
![Vibecoded](https://img.shields.io/badge/vibecoded-KI--generiert-blueviolet.svg)

> [!WARNING]
> **Früher, ungetesteter Stand (v0.1.0). Bitte lesen, bevor du es installierst.**
>
> - **Vibecoded:** Der Code wurde weitgehend von einer KI (Claude) geschrieben, im Dialog mit mir. Ich habe ihn nicht Zeile für Zeile geprüft.
> - **Ungetestet:** Die Integration lief noch an **keinem echten Kessel**. Es gibt automatische Tests, aber die laufen nur gegen einen simulierten Kessel und nachgebaute Cloud-Daten.
> - Die Eco-HK-spezifischen Teile, also Kanalnamen sowie Zustands- und Störungscodes, sind **Annahmen**. Sie stammen von der Pellet-Steuerung derselben Gerätefamilie.
> - Die Cloud-Funktionen können **Werte in deinen Kessel schreiben**, zum Beispiel Sollwerte, Betriebsarten und das Kesselprogramm. Das ist **standardmäßig gesperrt** und muss in den Optionen ausdrücklich erlaubt werden („Werte über die Cloud ändern erlauben“). Schalte es erst ein, wenn du die Integration an deinem Kessel geprüft hast. Die Verantwortung liegt bei dir.
>
> Ausprobieren, Fehlerberichte und Diagnosedaten von echten Anlagen sind sehr willkommen. Für den produktiven Einsatz ist der Stand noch **nicht** gedacht.

> **English:** Unofficial Home Assistant integration for Hargassner wood chip boilers (Eco-HK). Early, **untested and vibecoded (AI-generated)**. It has never run against a real boiler. Use at your own risk; bug reports welcome.

Inoffizielle Integration für **Hargassner Hackschnitzelkessel (Eco-HK)** mit Touch-Tronic-Steuerung.

- **Lokal lesen:** Der Datenstrom des Kessels (LAN, Telnet-Port 23) liefert jede Sekunde alle Messwerte. Das funktioniert ohne Cloud und ohne Internet.
- **Über die Cloud steuern (optional):** Raumsollwerte, Heizkurve, Heizgrenzen und Betriebsarten der Heizkreise werden über das Hargassner-App-Konto gesetzt.
- **Hackgut-Bilanz:** Erzeugte Wärme (fürs Energie-Dashboard), Hackgutverbrauch in kg und SRM, Lagerstand und Reichweite in Tagen.

> ⚠️ Nicht von Hargassner unterstützt. Die Cloud-API ist aus der App rekonstruiert und kann sich jederzeit ändern.

## Unterschiede zur Pellet-Integration `hargassner`

| | `hargassner` (Cloud) | `hargassner_hk` |
|---|---|---|
| Datenquelle | nur Cloud, Abfrage alle 60 s | lokaler Datenstrom + optional Cloud |
| Werte | rund 15 Widget-Werte | alle Kanäle des DAQ-Templates (100+) |
| Hackgut-spezifisch | – | Saugzug, O₂, Rauchgas, Motorströme (Raumaustragung, Ascheaustragung, Schieberost), Störungstexte |
| Verbrauch | Lagerstand in kg (aus der Cloud) | Wärme in kWh, Verbrauch in kg/SRM, Lagerstand, Reichweite |
| Sprache | Namen fest auf Französisch | Übersetzungen Deutsch/Englisch |
| Fehlerfälle | – | Reconfigure nach Firmware-Update, Reauth, Diagnostics |

Beide Integrationen laufen parallel, da sie verschiedene Domains haben.

## Voraussetzungen

1. Der Kessel ist per LAN im Heimnetz und hat eine feste IP-Adresse (DHCP-Reservierung im Router).
2. **DAQ-Template: meist nicht nötig.** Die Bedeutung der Werte im Datenstrom hängt von Modell und Firmware ab. Für geprüfte Kessel bringt die Integration das Template mit und erkennt es automatisch, das Feld bleibt dann einfach leer. Mitgeliefert ist derzeit:
   - **Eco-HK, Firmware V30.0HAR.f** (mit und ohne Lagerbestandsberechnung des Kessels)

   Wird dein Kessel nicht erkannt, meldet die Einrichtung das, und du exportierst das Template selbst: **Einstellen → Setup → Dateimanager → DAQ**, neueste Datei, **Export** (ausführlich: [Kurzanleitung DAQ-Datei](docs/DAQ-Datei.md)). Bitte schick es dann auch als Issue, damit es für alle mitgeliefert werden kann.

Bei der Einrichtung liest die Integration eine Live-Zeile vom Kessel und prüft, ob das Template dazu passt.

## Installation

**HACS:** HACS → Integrationen → ⋮ → Benutzerdefinierte Repositories → dieses Repo als *Integration* hinzufügen → „Hargassner HK“ installieren → Home Assistant neu starten.

**Manuell:** `custom_components/hargassner_hk/` nach `config/custom_components/` kopieren und Home Assistant neu starten.

Danach: Einstellungen → Geräte & Dienste → Integration hinzufügen → **Hargassner HK**.

## Einstellungen (Optionen)

| Option | Standard | Bedeutung |
|---|---|---|
| Aktualisierungsintervall lokal | 10 s | Der Kessel sendet jede Sekunde. HA übernimmt nur alle *n* Sekunden einen Wert, damit die Datenbank nicht unnötig wächst. |
| Kanal für Kesselleistung | `Leistung` | Kanal in % der Nennleistung, Grundlage der Wärme- und Verbrauchsberechnung |
| Nennleistung | 30 kW | laut Typenschild |
| Heizwert | 3,4 kWh/kg | Fichte W30. Faustwerte: W20 ≈ 4,0, W40 ≈ 2,8 |
| Schüttdichte | 210 kg/SRM | Fichte W30 ≈ 200–230, Buche ≈ 300–340 |
| Wirkungsgrad | 90 % | |
| Werte über die Cloud ändern erlauben | aus | Schreibschutz für alle Cloud-Steuerungen (nur mit Cloud-Login sichtbar) |

### So wird der Verbrauch berechnet

```
Wärme [kWh]  = ∫ Leistung [%] × Nennleistung [kW] dt
Hackgut [kg] = Wärme ÷ (Heizwert × Wirkungsgrad)
Hackgut [SRM] = kg ÷ Schüttdichte
```

Die Werte sind Schätzungen. **Kalibrieren:** Setze nach einer Lieferung den Lagerstand. Ist das Lager früher leer als berechnet, senke den Heizwert, ist es später leer, erhöhe ihn.

## Lagerstand pflegen

- Entität **Lagerstand** (SRM): direkt setzen, zum Beispiel nach dem Ausmessen.
- Aktion `hargassner_hk.refill`: addiert eine Lieferung.
- Aktion `hargassner_hk.set_storage`: setzt den Lagerstand absolut.

```yaml
action: hargassner_hk.refill
data:
  config_entry_id: <ID des Eintrags>
  amount: 30   # SRM
```

Beispiel-Automation für eine Warnung bei niedrigem Lager:

```yaml
triggers:
  - trigger: numeric_state
    entity_id: sensor.eco_hk_reichweite_lager
    below: 14
actions:
  - action: notify.notify
    data:
      message: "Hackgut reicht noch etwa {{ states('sensor.eco_hk_reichweite_lager') | int }} Tage."
```

## Entitäten

- **Sensoren:** alle Analogkanäle des Templates. Bekannte Kanäle (TK, TRG, O2, SZist, Leistung, Puffer, Vorläufe …) haben deutsche Namen. Motorströme und unbekannte Kanäle ohne °C-Einheit sind standardmäßig deaktiviert, du kannst sie bei Bedarf aktivieren.
- **Kesselzustand** mit dem Rohcode als Attribut. Beim Eco-HK sind bisher „Aus“ (1) und „Leistungsbrand“ (5) am Display bestätigt; andere Codes erscheinen als „Sonstiger Zustand“, bis sie zugeordnet sind (bitte melden: Code + Displaytext).
- **Betriebsstunden** je Komponente (Brenner, Zündung, Saugzug, Einschub, Austragungen, Roste, Putzmotor, Pumpen) mit Statistik pro Tag/Woche/Monat; Zählerstände für den Abgleich mit dem Kesseldisplay (Aktion `hargassner_hk.set_operating_hours`).
- **Störung** als Text mit Code, dazu der Binärsensor *Störung aktiv*.
- **Binärsensoren:** Digitalkanäle wie Pumpen und Störmeldung, *Brenner aktiv*, lokale Verbindung und Cloud-Verbindung.
- **Mit Cloud:**
  - Climate pro Heizkreis
  - Number: Raumtemperatur Tag und Nacht, Raumtemperatur-Korrektur, Heizkurve (Radiator und Fußboden), Heizgrenzen, Warmwasser-Solltemperatur
  - Select: Kesselprogramm (Aus, Nur Warmwasser, Automatik, Abbrand) und Betriebsart pro Heizkreis
  - Buttons: Puffer zwangsladen, Warmwasser zwangsladen, Zirkulation einmalig
  - Unbekannte Cloud-Parameter werden deaktiviert angelegt.
  - Modell und Nennleistung werden aus der Cloud übernommen („Eco-HK 50“ → 50 kW).

## Was die Cloud liefert und was nicht

Geprüft an einem Eco-HK 50 mit Firmware V30.0HAR.f:

- Die Cloud aktualisiert nur alle **5 Minuten** und kennt rund 30 Messkanäle: Kessel, Rauchgas, O₂, Rücklauf, Puffer, Heizkreise und Warmwasser.
- **Keine Hackgut-Werte:** Saugzug, Einschub, Raumaustragung, Schieberost, Ascheaustragung und Motorströme gibt es nur im lokalen Datenstrom.
- Der Lagerstand (`fuel_stock`) ist beim Eco-HK leer, deshalb berechnet die Integration ihn selbst.
- Der Cloud-Wert `efficiency` ist trotz des Namens die **Kesselleistung in %**, nicht der Wirkungsgrad.
- Die vollständige Parameterliste und die Gerätefunktionen sind nur für Servicepartner freigegeben (HTTP 403 für Kundenkonten).

## Bekannte Grenzen / bitte melden

- **Erster Live-Test bestanden (Eco-HK 50, V30.0HAR.f):** Der Datenstrom wird gelesen, die Werte stimmen mit der Cloud überein. Der Strom enthält bei dieser Firmware **3 Werte mehr**, als das DAQ-Template beschreibt. Die Integration erkennt das und korrigiert es automatisch. Bei anderen Modellen oder Firmwares kann eine ähnliche Abweichung auftreten. Dann meldet die Einrichtung „Template passt nicht“. Bitte als Issue melden, mit der Wertanzahl aus der Fehlermeldung.
- Auf Hackgutkesseln sind `Stb`, `NotAus` und die Sicherheitsschalter `SK_*` Ruhestromkontakte: Bit gesetzt heißt „alles in Ordnung“. Die Integration invertiert sie.

- Die Zustands- und Störungscodes stammen aus der Pellet-Firmware (Nano-PK) derselben Steuerungsfamilie. **Für den Eco-HK sind sie nicht verifiziert.** Unbekannte Zustände erscheinen als „Sonstiger Zustand“ und unbekannte Störungen als „Störung &lt;Nr&gt;“, jeweils mit dem Code als Attribut. Bitte melde fehlende Codes.
- Die Kanalnamen im Eco-HK-Template können von den hier hinterlegten abweichen. Solche Kanäle erscheinen trotzdem, nur mit ihrem Template-Namen. Für die Ergänzung in `channels.py` helfen die **Diagnosedaten** (Gerät → ⋮ → Diagnose herunterladen); E-Mail und Passwort sind darin geschwärzt.
- Der Touch-Tronic erlaubt eventuell nur **eine** Telnet-Verbindung gleichzeitig. Andere Tools, die Port 23 nutzen, solange parallel nicht verwenden.

## Mithelfen

Am meisten helfen Rückmeldungen von echten Anlagen. Bitte ein [Issue](https://github.com/MrBumbastik/hargassner-hk/issues) öffnen mit:
- Kesselmodell und Firmware-Version (steht am Touch-Tronic und in den Diagnosedaten),
- den **Diagnosedaten** (Gerät → ⋮ → Diagnose herunterladen). E-Mail und Passwort sind darin geschwärzt. Prüfe sie trotzdem vor dem Hochladen auf persönliche Angaben,
- gern dem `<DAQPRJ>`-Block deiner DAQ-Datei.

Auf der [Roadmap](TODO.md) steht, was als Nächstes geplant ist.

## Entwicklung

```bash
pip install homeassistant pytest-homeassistant-custom-component
pytest
```

Die Tests simulieren den Kessel mit einem lokalen TCP-Server.

## Danksagung

Das Telnet-Protokoll und das DAQ-Template-Format sind dokumentiert in [TheRealKillaruna/nano_pk](https://github.com/TheRealKillaruna/nano_pk) (Apache-2.0). Den Cloud-API-Zugang hat [lithium73fr/hargassner-ha](https://github.com/lithium73fr/hargassner-ha) erarbeitet.

## Lizenz

[Apache-2.0](LICENSE). Der Code ist ohne jede Gewährleistung, siehe Lizenztext.
