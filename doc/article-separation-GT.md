# Article-Separation GT

* [W3C-JSON Export](http://spunk.lx0246.sbb.spk-berlin.de/ArticleSeparation/w3c-anno.json) der Annotationen.
* Aus dem W3C-JSON Vorprozessierte GT [TSV - Datei](http://spunk.lx0246.sbb.spk-berlin.de/ArticleSeparation/gt.tsv). Dokumentation der Spalten siehe unten.
* [Bild- und page-XML Dateien](http://spunk.lx0246.sbb.spk-berlin.de/ArticleSeparation/data.zip) als ZIP-Archiv. 


# TSV Format Article-Separation GT:

* id : ID eines einzelnen Artikelpolygons
* sequence_id: ID einer Polyhonsequenz die einem Artikel entspricht. Diese ID gleicht der ID des ersten Polygons der Sequenz.
* sequence_num: Gibt wo das Polygon innerhalb der Sequenz steht. 
* url : Die Content-Server URL für das Bild auf dem das Polyhon liegt.
* image_file: Pfad zur Bilddatei, die vom Content-Server runtergeladen wurde.
* xml_file: Pfad zur page-XML-Datei die zur Bilddatei gehört 
* coords : Die Koordinaten des Polyhons im Format "x1,y1 x2,y2 ... xN,yN" (Gilt auch für Rechtecke)
* tag : Das Tag article, article_head  etc.
* next_part: Wenn das Polygon Teil einer Sequenz ist, ist dies die id des nächsten Polygons in der Sequenz
  * Wenn dieses Polygon das letzte der Sequenz ist dann gilt next_part="not_specified"
  * Wenn dieses Polygon des letzte annotierte der Sequenz ist aber weitere auf nicht annotierten Seiten liegen, dann gilt next_part=="unknown"
* prev_part: Wenn das Polyhon Teil einer Sequenz ist und es ein vorheriges Polyhon gibt, ist dies die id des vorherigen Polyhons ansonsten gilt next_part=not_specified
* created: Zeitstempel der Erzeugung des Polyhons. Wenn die Sequenzen (siehe sequence_id) nach dem Zeitstempel des ersten Polygons der Sequenz sortiert werden erhält man eine Lesereihenfolge über die Seite.
* creator: Gibt an von wem das Polygon hinzugefügt wurde.
* zdb : ZDB-ID der Zeitungsseite
* year : Erscheinungsjahr
* month : Erscheinungsmonat
* day : Erscheinungstag
* issue: Ausgabe
* page: Seite