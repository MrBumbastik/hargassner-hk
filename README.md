# Hargassner HK – Home Assistant Integration für Hackgutkessel

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

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
2. **DAQ-Template deiner Firmware:** Die Bedeutung der Werte im Datenstrom hängt von der Firmware-Version ab. So bekommst du das Template:
   1. Am Touch-Tronic die SD-Aufzeichnung aktivieren.
   2. Eine SD-Karte für ein paar Minuten einstecken.
   3. Die Datei `DAQ00000.DAQ` am PC in einem Texteditor öffnen.
   4. Den Block `<DAQPRJ> … </DAQPRJ>` am Dateianfang kopieren. Du kannst auch einfach den ganzen Dateiinhalt einfügen, der Block wird automatisch herausgeschnitten.

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
- **Kesselzustand** (Aus, Zündung, Leistungsbrand, Gluterhaltung, Entaschung …) mit dem Rohcode als Attribut.
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

- Die Zustands- und Störungscodes stammen aus der Pellet-Firmware (Nano-PK) derselben Steuerungsfamilie. **Für den Eco-HK sind sie nicht verifiziert.** Unbekannte Zustände erscheinen als „Sonstiger Zustand“ und unbekannte Störungen als „Störung &lt;Nr&gt;“, jeweils mit dem Code als Attribut. Bitte melde fehlende Codes.
- Die Kanalnamen im Eco-HK-Template können von den hier hinterlegten abweichen. Solche Kanäle erscheinen trotzdem, nur mit ihrem Template-Namen. Für die Ergänzung in `channels.py` helfen die **Diagnosedaten** (Gerät → ⋮ → Diagnose herunterladen); E-Mail und Passwort sind darin geschwärzt.
- Der Touch-Tronic erlaubt eventuell nur **eine** Telnet-Verbindung gleichzeitig. Andere Tools, die Port 23 nutzen, solange parallel nicht verwenden.

## Entwicklung

```bash
pip install homeassistant pytest-homeassistant-custom-component
pytest
```

Die Tests simulieren den Kessel mit einem lokalen TCP-Server.

## Danksagung

Das Telnet-Protokoll und das DAQ-Template-Format sind dokumentiert in [TheRealKillaruna/nano_pk](https://github.com/TheRealKillaruna/nano_pk) (Apache-2.0). Den Cloud-API-Zugang hat [lithium73fr/hargassner-ha](https://github.com/lithium73fr/hargassner-ha) erarbeitet.
