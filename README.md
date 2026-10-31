![HK Hackgut](https://raw.githubusercontent.com/MrBumbastik/hargassner-hk/main/custom_components/hargassner_hk/brand/icon.png)

# Hargassner HK – Home Assistant Integration für Hackgutkessel

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
![Status](https://img.shields.io/badge/Status-Beta-yellow.svg)
![Version](https://img.shields.io/badge/Version-0.10.2-blue.svg)
![Vibecoded](https://img.shields.io/badge/vibecoded-KI--generiert-blueviolet.svg)

> [!WARNING]
> **Beta (v0.10.2): läuft im Alltag an genau einer Anlage. Bitte lesen, bevor du es installierst.**
>
> - **Vibecoded:** Der Code wurde weitgehend von einer KI (Claude) geschrieben, im Dialog mit mir. Ich habe ihn nicht Zeile für Zeile geprüft. Es gibt rund 100 automatische Tests und eine CI (Tests, hassfest, HACS-Prüfung).
> - **Getestet an einem Eco-HK 50, Firmware V30.0HAR.f:** Lokaler Datenstrom und Cloud laufen dort produktiv und haben die bisherigen Hargassner-Integrationen samt Dashboard und Energie-Dashboard ersetzt. Die Messwerte wurden mit der Hargassner-Cloud abgeglichen. Ein Schreibtest über die Cloud (Warmwasser-Solltemperatur ändern und zurücksetzen) war erfolgreich.
> - **Andere Modelle und Firmwares sind ungetestet.** Kanalzuordnung, Zustands- und Störungscodes können dort abweichen.
> - **Zustands- und Störungscodes des Eco-HK** stammen aus dem Service-Handbuch Eco-HK 20-60 von Hargassner; Start und Leistungsbrand sind zusätzlich am Display bestätigt. Eine echte Störung ist an der Testanlage noch nicht aufgetreten.
> - Die Cloud-Funktionen können **Werte in deinen Kessel schreiben**, zum Beispiel Sollwerte, Betriebsarten und das Kesselprogramm. Das ist **standardmäßig gesperrt** und muss in den Optionen ausdrücklich erlaubt werden („Werte über die Cloud ändern erlauben“). Die Verantwortung liegt bei dir.
>
> Was bis zur Version 1.0 noch fehlt, steht unter [Weg zu Version 1.0](#weg-zu-version-10). Rückmeldungen von weiteren Anlagen sind sehr willkommen, vor allem Diagnosedaten und Zustandscodes mit dem zugehörigen Displaytext.

> **English:** Unofficial Home Assistant integration for Hargassner wood chip boilers (Eco-HK). **Beta, vibecoded (AI-generated).** In daily use on one Eco-HK 50 (firmware V30.0HAR.f), values cross-checked against the Hargassner cloud; other models/firmwares are untested. Use at your own risk; bug reports welcome.

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
| Betriebsstunden | – | je Komponente, mit Statistik, abgleichbar mit dem Display |
| Fehlerfälle | – | Neu konfigurieren (lokal / Cloud getrennt), Reauth bei falschem Passwort, Diagnosedaten |

Beide Integrationen laufen parallel, da sie verschiedene Domains haben.

### Umstieg von einer anderen Hargassner-Integration

1. `hargassner_hk` zusätzlich einrichten und ein paar Tage parallel laufen lassen.
2. Dashboards, Automationen, Skripte und das Energie-Dashboard auf die neuen Entitäten umstellen. Die Wärme fürs Energie-Dashboard liefert **Erzeugte Wärme** (kWh, `total_increasing`).
3. Betriebsstunden-Zählerstände einmalig vom Kesseldisplay übernehmen (Aktion `hargassner_hk.set_operating_hours`).
4. Die alte Integration zunächst nur **deaktivieren**. Beim Löschen geht deren Verlauf verloren, auch die bisherige Wärmemenge im Energie-Dashboard.

## Voraussetzungen

1. Der Kessel ist per LAN im Heimnetz und hat eine feste IP-Adresse (DHCP-Reservierung im Router).
2. **DAQ-Template: meist nicht nötig.** Die Bedeutung der Werte im Datenstrom hängt von Modell und Firmware ab. Für geprüfte Kessel bringt die Integration das Template mit und erkennt es automatisch, das Feld bleibt dann einfach leer. Mitgeliefert ist derzeit:
   - **Eco-HK, Firmware V30.0HAR.f** (mit und ohne Lagerbestandsberechnung des Kessels)

   Wird dein Kessel nicht erkannt, meldet die Einrichtung das, und du exportierst das Template selbst: **Einstellen → Setup → Dateimanager → DAQ**, neueste Datei, **Export** (ausführlich: [Kurzanleitung DAQ-Datei](https://github.com/MrBumbastik/hargassner-hk/blob/main/docs/DAQ-Datei.md)). Bitte schick es dann auch als Issue, damit es für alle mitgeliefert werden kann.

Bei der Einrichtung liest die Integration eine Live-Zeile vom Kessel und prüft, ob das Template dazu passt.

## Installation

**HACS:** HACS → Integrationen → ⋮ → Benutzerdefinierte Repositories → dieses Repo als *Integration* hinzufügen → „Hargassner HK“ installieren → Home Assistant neu starten.

Die Installation über HACS ist optional.

**Manuell:** `custom_components/hargassner_hk/` nach `config/custom_components/` kopieren und Home Assistant neu starten.

Danach: Einstellungen → Geräte & Dienste → Integration hinzufügen → **Hargassner HK**. Die IP-Adresse ist Pflicht. E-Mail und Passwort des Hargassner-Kontos sind optional: Sind sie angegeben, wird die Cloud mit eingerichtet. Nachträglich geht das über ⋮ → **Neu konfigurieren** → **Hargassner-Cloud-Login**.

## Einstellungen (Optionen)

| Option | Standard | Bedeutung |
|---|---|---|
| Aktualisierungsintervall lokal | 10 s | Der Kessel sendet jede Sekunde. HA übernimmt nur alle *n* Sekunden einen Wert, damit die Datenbank nicht unnötig wächst. |
| Kanal für Kesselleistung | `Leistung` | Kanal in % der Nennleistung, Grundlage der Wärme- und Verbrauchsberechnung |
| Nennleistung | 30 kW | laut Typenschild; mit Cloud wird sie aus dem Modellnamen übernommen |
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

Beim Hackgutkessel zählt die Leistung nur im Leistungsbrand oder solange Brennstoff gefördert wird: Im **Abbrand** meldet der Eco-HK „Leistung 100 %“, obwohl nichts mehr nachgefördert wird und das Rauchgas schon Luft ist.

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

Beispiel-Automation für eine Warnung bei niedrigem Lager (die Entitäts-ID hängt vom Gerätenamen ab):

```yaml
triggers:
  - trigger: numeric_state
    entity_id: sensor.hargassner_eco_hk_reichweite_lager
    below: 14
actions:
  - action: notify.notify
    data:
      message: "Hackgut reicht noch etwa {{ states('sensor.hargassner_eco_hk_reichweite_lager') | int }} Tage."
```

## Entitäten

- **Sensoren:** alle Analogkanäle des Templates. Bekannte Kanäle (TK, TRG, O2, SZist, Leistung, Puffer, Vorläufe …) haben deutsche Namen. Motorströme und unbekannte Kanäle ohne °C-Einheit sind standardmäßig deaktiviert, du kannst sie bei Bedarf aktivieren.
- **Kesselzustand** mit dem Rohcode als Attribut. Beim Eco-HK laut Service-Handbuch: Aus (1), Zündung Start (3), Zündung (4), Leistungsbrand (5), Gluterhaltung (6), Abbrand (7), Entaschung (9), STB ausgelöst (10), Handbetrieb (11), Stückholz-Notbetrieb (12). 1, 3, 4 und 5 sind zusätzlich am Display bestätigt, 7 und 9 durch Mitschnitte. Andere Codes erscheinen als „Sonstiger Zustand“.
- **Brenner aktiv** (und Brenner-Betriebsstunden) folgt beim Hackgutkessel dem kesseleigenen Bit „Feuerung aktiv (F2)“, dazu Leistungsbrand oder Zündheizung.
- **Betriebsstunden** je Komponente (Brenner, Zündung, Saugzug, Einschub, Austragungen, Roste, Putzmotor, Pumpen). Die Integration zählt sie selbst aus dem Datenstrom, denn der Kessel sendet dort nur den Zähler der Einschubschnecke mit. *Betriebsstunden …* zählen ab Installation und liefern Statistik pro Tag/Woche/Monat. *Zählerstand …* = Startwert + gezählte Stunden, zum Abgleich mit dem Kesseldisplay (Startwert einmalig per Aktion `hargassner_hk.set_operating_hours`).
- **Störung** als Text mit Code, dazu der Binärsensor *Störung aktiv*. Beim Eco-HK kommen die Texte aus der Meldungsliste des Service-Handbuchs (über 400 Codes, nur auf Deutsch). Ursache und Lösung stehen im Handbuch.
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

- **Eco-HK 50, V30.0HAR.f:** Der Datenstrom enthält bei dieser Firmware **3 Werte mehr**, als das DAQ-Template beschreibt. Die Integration erkennt das und korrigiert es automatisch. Bei anderen Modellen oder Firmwares kann eine ähnliche Abweichung auftreten. Dann meldet die Einrichtung „Template passt nicht“. Bitte als Issue melden, mit der Wertanzahl aus der Fehlermeldung.
- Auf Hackgutkesseln sind `Stb`, `NotAus` und die Sicherheitsschalter `SK_*` Ruhestromkontakte: Bit gesetzt heißt „alles in Ordnung“. Die Integration invertiert sie.

- Andere Hackgutkessel als der Eco-HK verwenden die Störungstexte der Pellet-Steuerung (Nano-PK), die nicht verifiziert sind. Unbekannte Zustände erscheinen als „Sonstiger Zustand“, unbekannte Störungen als „Störung &lt;Nr&gt;“, jeweils mit dem Code als Attribut. Bitte melde fehlende Codes.
- Die Kanalnamen im Eco-HK-Template können von den hier hinterlegten abweichen. Solche Kanäle erscheinen trotzdem, nur mit ihrem Template-Namen. Für die Ergänzung in `channels.py` helfen die **Diagnosedaten** (Gerät → ⋮ → Diagnose herunterladen); E-Mail und Passwort sind darin geschwärzt.
- Der Touch-Tronic erlaubt eventuell nur **eine** Telnet-Verbindung gleichzeitig. Andere Tools, die Port 23 nutzen, solange parallel nicht verwenden.

## Weg zu Version 1.0

Die Beta läuft seit Oktober 2026 an einem Eco-HK 50. Version 1.0 gibt es, wenn diese Punkte erledigt sind:

- [x] **Kaltstart mitgeschnitten (31.10.2026):** Code 3 = „Zündung Start“, Code 4 = „Zündung“ (anfangs mit „Brennk. füllen“ am Display), Code 5 = „Leistungsbrand“, mit Displayfotos abgeglichen.
- [x] **Zustands- und Störungscodes aus dem Service-Handbuch übernommen** (v0.10.0), darunter Abbrand (7) und Entaschung (9).
- [ ] **Bei der ersten echten Störung prüfen,** ob Code und Text mit dem Display übereinstimmen.
- [ ] **Betriebsstunden mit dem Display abgleichen:** gezählte Laufzeiten gegen die Zähler am Touch-Tronic prüfen, nach einigen Tagen Brennbetrieb.
- [ ] **Ein bis zwei Wochen Dauerbetrieb:** Verbindungsabbrüche, Neustarts von HA und Kessel, Cloud-Token-Erneuerung, Hackgut-Bilanz über mehrere Tage.

Weitere geplante Verbesserungen stehen in der [Roadmap](https://github.com/MrBumbastik/hargassner-hk/blob/main/TODO.md).

## Mithelfen

Am meisten helfen Rückmeldungen von echten Anlagen. Bitte ein [Issue](https://github.com/MrBumbastik/hargassner-hk/issues) öffnen mit:
- Kesselmodell und Firmware-Version (steht am Touch-Tronic und in den Diagnosedaten),
- den **Diagnosedaten** (Gerät → ⋮ → Diagnose herunterladen). E-Mail und Passwort sind darin geschwärzt. Prüfe sie trotzdem vor dem Hochladen auf persönliche Angaben,
- gern dem `<DAQPRJ>`-Block deiner DAQ-Datei.

Auf der [Roadmap](https://github.com/MrBumbastik/hargassner-hk/blob/main/TODO.md) steht, was als Nächstes geplant ist.

Das Logo (Flamme über Hackschnitzeln) ist eigens für dieses Projekt entworfen und kein Hargassner-Markenzeichen. Die Quellen liegen in [`docs/logo/`](https://github.com/MrBumbastik/hargassner-hk/tree/main/docs/logo).

## Entwicklung

```bash
pip install homeassistant pytest-homeassistant-custom-component
pytest
```

Die Tests simulieren den Kessel mit einem lokalen TCP-Server.

## Danksagung

Das Telnet-Protokoll und das DAQ-Template-Format sind dokumentiert in [TheRealKillaruna/nano_pk](https://github.com/TheRealKillaruna/nano_pk) (Apache-2.0). Den Cloud-API-Zugang hat [lithium73fr/hargassner-ha](https://github.com/lithium73fr/hargassner-ha) erarbeitet.

## Lizenz

[Apache-2.0](https://github.com/MrBumbastik/hargassner-hk/blob/main/LICENSE). Der Code ist ohne jede Gewährleistung, siehe Lizenztext.
