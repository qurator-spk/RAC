# Article-Separation GT

* [W3C-JSON Export](http://spunk.lx0246.sbb.spk-berlin.de/ArticleSeparation/w3c-anno.json) der Annotationen.
* Aus dem W3C-JSON Vorprozessierte Artikel-GT [TSV - Datei](http://spunk.lx0246.sbb.spk-berlin.de/ArticleSeparation/gt.tsv). 
  Diese Datei beschreibt lediglich die annotierten Artikelpolygone. Dokumentation der Spalten siehe unten.
  Sie wird mit dem [compile-artice-separation-gt](CLI.md#compile-artice-separation-gt) CLI-Befehl aus der W3C-JSON Datei erzeugt.
  Dabei entsteht auch ein [Fehlerreport](http://spunk.lx0246.sbb.spk-berlin.de/ArticleSeparation/errors.md).
* Mit dem [download-w3c-annotation-images](CLI.md#download-w3c-annotation-images) CLI-Befehl können alle in der W3C-JSON Datei referenzierten Bilder
  heruntergeladen werden. Hiergibt es diese Bilder und auch passende PAGE-XML Dateien die Layout und OCR enthalten und mit Eynollah erzeugt wurden 
  als  [ZIP-Archiv](http://spunk.lx0246.sbb.spk-berlin.de/ArticleSeparation/SBB.zip).
* Die Artikel-GT kann mit dem [match-article-sequences](CLI.md#match-article-sequences) CLI-Befehl auf die PAGE-XML Dateien gemappt werden.
  Für Eynollah Layout/OCR gibt es das Resultat [hier](http://spunk.lx0246.sbb.spk-berlin.de/ArticleSeparation/gt-eynollah-layout-ocr.tsv).
  Dokumenation dieser Datei folgt. 

## Newseye 

* Eynollah Layout+OCR für die Newseye-BnF-Zeitungsseiten als [ZIP-Archiv](http://spunk.lx0246.sbb.spk-berlin.de/ArticleSeparation/BnF.zip).
* Eynollah Layout+OCR für die Newseye-NLF-Zeitungsseiten als [ZIP-Archiv](http://spunk.lx0246.sbb.spk-berlin.de/ArticleSeparation/NLF.zip).

## Pero-OCR + Textbite Reading Order
* Pero Layout+OCR+RO für die SBB-Zeitungsseiten als [ZIP-Archiv](http://spunk.lx0246.sbb.spk-berlin.de/ArticleSeparation/SPUNK/pero-SBB.zip).

## CLI

* [download-w3c-annotation-images](CLI.md#download-w3c-annotation-images)
* [compile-artice-separation-gt](CLI.md#compile-artice-separation-gt)
* [match-article-sequences](CLI.md#match-article-sequences)

# TSV Format Article-Separation GT:
* Aktuell enthält diese [Datei](http://spunk.lx0246.sbb.spk-berlin.de/ArticleSeparation/gt.tsv) 4518, die jeweils ein Artikelpolygon beschreiben.
* id : ID eines einzelnen Artikelpolygons
* sequence_id: ID einer Polygonsequenz die insgesamt einem Artikel entspricht. Diese Sequenz-ID gleicht der ID des ersten Polygons der Sequenz für alle Polygone die zur Sequenz gehören.
* sequence_num: Gibt an an welcher Stelle das Polygon innerhalb der Sequenz steht. 
* url : Die Content-Server URL für das Bild auf dem das Polygon liegt.
* image_file: Pfad zur Bilddatei, die von der Content-Server-URL runtergeladen wurde (ZIP-Datei).
* xml_file: Pfad zur page-XML-Datei die zur Bilddatei gehört (ZIP-Datei) .
* coords : Die Koordinaten des Polygons im Format "x1,y1 x2,y2 ... xN,yN" (Gilt auch für Rechtecke).
* tag : Typ des Polygons article, article_head etc.
* next_part: Wenn das Polygon Teil einer Sequenz ist, ist dies die ID des nächsten Polygons in der Sequenz.
  * Wenn dieses Polygon das Letzte der Sequenz ist ,dann gilt next_part="not_specified".
  * Wenn dieses Polygon des Letzte annotierte der Sequenz ist, aber weitere auf nicht annotierten Seiten liegen, dann gilt next_part=="unknown".
* prev_part: Wenn das Polygon Teil einer Sequenz ist und es ein vorheriges Polygon gibt, ist dies die ID des vorherigen Polygons. Ansonsten gilt prev_part="not_specified".
* created: Zeitstempel der Erzeugung des Polygons. Wenn die Sequenzen nach dem Zeitstempel des ersten Polygons der Sequenz sortiert werden, erhält man eine Lesereihenfolge über die Seite.
* creator: Gibt an von wem das Polygon hinzugefügt wurde.
* zdb : ZDB-ID der Zeitungsseite.
* year : Erscheinungsjahr.
* month : Erscheinungsmonat.
* day : Erscheinungstag.
* issue: Ausgabe.
* page: Seite.

# TSV Format Artikel-GT + Layout + OCR
* Aktuell enthält diese [Datei](http://spunk.lx0246.sbb.spk-berlin.de/ArticleSeparation/gt-eynollah-layout-ocr.tsv) 109730 Zeilen, die jeweils eine Textzeile sowie deren Zuordnung zu einem Artikelpolygon beschreiben.
* ...