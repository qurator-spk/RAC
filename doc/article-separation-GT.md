# Article-Separation GT

* [W3C-JSON Export](http://spunk.lx0246.sbb.spk-berlin.de/ArticleSeparation/w3c-anno.json) der Annotationen.
* Aus dem W3C-JSON Vorprozessierte GT [TSV - Datei](http://spunk.lx0246.sbb.spk-berlin.de/ArticleSeparation/gt.tsv). Dokumentation der Spalten siehe unten.
* [Bild- und page-XML Dateien](http://spunk.lx0246.sbb.spk-berlin.de/ArticleSeparation/data.zip) als ZIP-Archiv. 


# TSV Format Article-Separation GT:

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
* prev_part: Wenn das Polygon Teil einer Sequenz ist und es ein vorheriges Polygon gibt, ist dies die ID des vorherigen Polyhons. Ansonsten gilt prev_part="not_specified".
* created: Zeitstempel der Erzeugung des Polygons. Wenn die Sequenzen nach dem Zeitstempel des ersten Polygons der Sequenz sortiert werden, erhält man eine Lesereihenfolge über die Seite.
* creator: Gibt an von wem das Polygon hinzugefügt wurde.
* zdb : ZDB-ID der Zeitungsseite.
* year : Erscheinungsjahr.
* month : Erscheinungsmonat.
* day : Erscheinungstag.
* issue: Ausgabe.
* page: Seite.