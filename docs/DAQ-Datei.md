# Kurzanleitung: DAQ-Datei vom Hargassner Touch-Tronic holen

Die Integration braucht das **DAQ-Template** deines Kessels. Es beschreibt, welcher Wert im lokalen Datenstrom was bedeutet. Das Template steht am Anfang jeder Aufzeichnungsdatei (`DAQxxxxx.DAQ`), die der Kessel auf eine SD-Karte schreibt.

Zeitbedarf: etwa 15 Minuten, davon 5–10 Minuten Warten.

## Du brauchst

- eine **SD-Karte**, am besten eine ältere kleine Karte bis 32 GB, formatiert mit **FAT32** (ältere Steuerungen lesen SDXC/exFAT oft nicht),
- einen PC mit Kartenleser und einem Texteditor (Notepad++, VS Code oder Ähnliches).

## Schnellweg: Export über den Dateimanager

Die Steuerung zeichnet ohnehin laufend DAQ-Dateien auf. Getestet am Eco-HK 50 mit Firmware V30.0HAR.f:

1. SD-Karte (FAT32) am Touch-Tronic einstecken.
2. **Einstellen → Setup → Dateimanager → DAQ**
3. Die **neueste Datei** auswählen (höchste Nummer, z. B. `DAQ02788.DAQ`) und **Export** drücken.
4. Karte entnehmen und weiter mit [Schritt 4: Datei prüfen](#4-datei-prüfen).

Nimm die **neueste** Datei. Die Kanalliste kann sich nach einem Firmware-Update **und auch nach Änderungen an Einstellungen** ändern. Ältere Dateien passen dann nicht mehr.

Funktioniert das bei deiner Version nicht, hilft der ausführliche Weg unten.

## 1. Karte vorbereiten

1. Die Karte am PC als **FAT32** formatieren. Achtung, dabei werden alle Daten auf der Karte gelöscht.
2. Keine Ordner anlegen, die Karte bleibt leer.

## 2. Aufzeichnung am Kessel starten

1. Den **SD-Kartensteckplatz am Touch-Tronic-Bedienteil** suchen, meist seitlich oder unten am Display. Gibt es dort keinen, am Steuergerät im Kessel nachsehen.
2. Die Karte **bei laufendem Kessel** einstecken, mit den Kontakten in der Richtung, die die Markierung am Steckplatz zeigt.
3. Die **Datenaufzeichnung aktivieren**. ⚠️ Der genaue Menüpunkt am Eco-HK ist nicht dokumentiert und hängt von der Softwareversion ab. Typische Stellen:
   - Hauptmenü → **Service** bzw. **Einstellungen** → **SD-Karte** / **Datenaufzeichnung** / **Datalogger**
   - Bei manchen Versionen startet die Aufzeichnung automatisch, sobald eine Karte steckt. Dann erscheint ein **SD-Symbol** in der Statuszeile.
   - Fragt das Menü nach einem **Intervall**, ist jeder Wert in Ordnung (z. B. 1 Minute). Für das Template spielt er keine Rolle.
4. **5–10 Minuten warten.** Der Kessel muss dafür nicht brennen.

> Findest du den Menüpunkt nicht: Fotografiere die Menüebenen *Service* und *Einstellungen* und frag deinen Heizungsbauer oder den Hargassner-Service nach „SD-Karten-Datenaufzeichnung (DAQ)“. Manche Menüs sind erst mit Servicecode zugänglich.

## 3. Karte entnehmen

1. Wenn möglich, die Aufzeichnung im selben Menü **beenden** oder die Karte über „SD-Karte entfernen“ abmelden.
2. Die Karte herausziehen.

## 4. Datei prüfen

1. Die Karte am PC öffnen. Dort sollte eine Datei wie **`DAQ00000.DAQ`** liegen, eventuell in einem Unterordner.
2. Die Datei mit dem Texteditor öffnen. **Nicht doppelklicken**, Windows kennt die Endung nicht.
3. Ganz am Anfang muss ein Block stehen, der so beginnt:
   ```
   <DAQPRJ><ANALOG><CHANNEL id='0' name='...
   ```
   und mit `</DAQPRJ>` endet. Danach folgen unleserliche Messdaten, das ist normal.

✅ Ist der Block da, hat alles geklappt.
❌ Fehlt die Datei oder der Block, war die Aufzeichnung nicht aktiv oder zu kurz. Dann Schritt 2 wiederholen.

## 5. Verwenden

- **Bei der Einrichtung der Integration:** den Block von `<DAQPRJ>` bis `</DAQPRJ>` kopieren und in das Feld *DAQ-Template* einfügen. Du kannst auch den ganzen Dateiinhalt einfügen, der Block wird automatisch herausgeschnitten.
- **Als Hilfe für die Entwicklung:** gern den `<DAQPRJ>`-Block in einem [Issue](https://github.com/MrBumbastik/hargassner-hk/issues) posten, zusammen mit Kesselmodell und Firmware-Version. Der Block enthält nur Kanalnamen und Einheiten, keine persönlichen Daten. Die Messdaten danach brauchst du nicht mitzuschicken.

## Nach einem Firmware-Update oder geänderten Einstellungen

Updates und manche Einstellungen am Kessel ändern die Kanalliste. Merkst du das (die Integration meldet „Template passt nicht“), die Schritte oben wiederholen und das neue Template unter *Einstellungen → Geräte & Dienste → Hargassner HK → ⋮ → Neu konfigurieren* einfügen.
