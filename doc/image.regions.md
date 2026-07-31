# Extraktion von Bildregionen

Vorraussetzung ist das [installierte](https://code.dev.sbb.berlin/idm4/SPUNK#installation) SPUNK python-Paket.

## Extraktion der Bounding-Boxes aus den ImageRegion XML-Elementen der PAGE-Dateien

Die erforderlichen OCR-Datenbanken liegen hier:
```
kai.labusch@lx0246:/data/kai.labusch/SPUNK$ ls -lh *OCR*.sqlite
-rw-r--r-- 1 kai.labusch kai.labusch  31G  4. Dez 2025  SP-1907-1931-OCR.sqlite
-rw-r--r-- 1 kai.labusch kai.labusch 104G 17. Jul 12:50 SP-24353991-OCR.sqlite
-rw-r--r-- 1 kai.labusch kai.labusch  96G 23. Dez 2025  SP-2436020X-OCR.sqlite
-rw-r--r-- 1 kai.labusch kai.labusch  88G 16. Jul 17:21 SP-27646518-OCR.sqlite
-rw-r--r-- 1 kai.labusch kai.labusch  33G 27. Apr 18:35 SP-2812988X-OCR.sqlite
```
Die OCR-Datenbanken können auch [hier](../artifacts/README.md) heruntergeladen werden.

Mit dem Befehl [scan-graph-regions-ocr-database](CLI.md#scan-graph-regions-ocr-database) 
kann aus diesen Datenbanken eine CSV-Datei extrahiert werden, die die Bounding-Boxes der ImageRegion Elemente
sowie die Originaldatei auf der die OCR gelaufen ist enthält. Zusätzlich wird noch der Link auf den Content-Server
mitgeschrieben unter dem die Seite auch abrufbar sein sollte.

Da es aber noch Diskrepanzen zwischen den Content-Server Links und den Dateien im NFS gibt sollten im allgemeinen 
die Dateien direkt aus dem NFS genutzt werden. Dies reduziert auch Konfliktpotentiale bezgl. Content-Server-Belastung.

Beispielextraktion der CSV-Datei:
```
(SPUNK-3.11) kai.labusch@lx0246:/data/kai.labusch/SPUNK$ scan-graph-regions-ocr-database ./zefys-files.tsv SP-1907-1931-OCR.sqlite test.csv
Read 171287 entries from SP-1907-1931-OCR.sqlite ...
171287 entries remain after filtering.
Joining with scan files ...
171287 entries remain after join.
  1%|▌                                                               | 1487/171287 [00:05<10:02, 281.96it/s]
```

Mit folgender Anweisung wird das für alle OCR-Datenbanken in dem Verzeichnis gemacht:
```
(SPUNK-3.11) kai.labusch@lx0246:/data/kai.labusch/SPUNK$ for i in *OCR*.sqlite; do scan-graph-regions-ocr-database ./zefys-files.tsv $i ImageRegions/`basename -s .sqlite $i`-image-regions.csv; done
```

Die Resultate mit Stand vom 31.7.2026 liegen hier:
```
(SPUNK-3.11) kai.labusch@lx0246:/data/kai.labusch/SPUNK/ImageRegions$ ls -lh
insgesamt 852M
-rw-r--r-- 1 kai.labusch kai.labusch  75M 30. Jul 16:58 SP-1907-1931-OCR-image-regions.csv
-rw-r--r-- 1 kai.labusch kai.labusch 258M 30. Jul 17:35 SP-24353991-OCR-image-regions.csv
-rw-r--r-- 1 kai.labusch kai.labusch 213M 30. Jul 18:07 SP-2436020X-OCR-image-regions.csv
-rw-r--r-- 1 kai.labusch kai.labusch 232M 30. Jul 18:39 SP-27646518-OCR-image-regions.csv
-rw-r--r-- 1 kai.labusch kai.labusch  75M 30. Jul 18:50 SP-2812988X-OCR-image-regions.csv
```

Beispiel CSV:
```
(SPUNK-3.11) kai.labusch@lx0246:/data/kai.labusch/SPUNK/ImageRegions$ head SP-1907-1931-OCR-image-regions.csv
x1,y1,x2,y2,zdb_id,year,month,day,issue,page,image_file,image_url
597,2508,1002,2800,24353991,1907,3,7,1,10,/zefys/archive/./24353991/1907/03/07/01/presentation/27112366_1907-03-07_000_111_1_010.jpg,https://content.staatsbibliothek-berlin.de/zefys/SNP24353991-19070307-0-10-0-0/full/full/0/default.jpg
```

Spalten der CSV-Dateien: x1,y1,x2,y2,zdb_id,year,month,day,issue,page,image_file,image_url

* x1,y1,x2,y2 : left,top,right,bottom Koordinaten der Bounding-Box der Bildregion
* zdb_id : ZDB-ID der Zeitung
* year,month,day,issue,page: Erscheinungsdaten
* image_file : Originaldatei im ZEFYS-NFS auf dem die OCR gelaufen ist
* image_url : Korrespondierender Link zum Content-Server (meistens richtig)



## Ausschneiden der Bildregionen aus den Seitenscans

Mittels des [zefys-crop-images](CLI.md#zefys-crop-images) Befehls und den CSV-Dateien 
können dann die Bildregionen in eigene JPEG-Dateien extrahiert werden.
Die OCR-Datenbanken werden hierfür nicht mehr benötigt.

Defaultmäßig legt das Tool eine Ordnerstruktur ZDBID/YEAR/MONTH/DAY/ISSUE an. 
Die Bilddateinamen setzen sich als ZDBID-YEAR-MONTH-DAY-ISSUE-PAGE-NR.jpeg zusammen. 
Wobei NR eine bei 0 beginnende laufende Abbildungsnr. pro Seite ist.
Die Ergebnisse werden immer in das aktuelle Verzeichnis in dem man sich befindet geschrieben.
Beispiel:
```
(SPUNK-3.11) kai.labusch@lx0246:/data/kai.labusch/SPUNK/ImageRegions$ zefys-crop-images SP-1907-1931-OCR-image-regions.csv --min-width=100 --min-height=100 --max-count=10 
Read 319340 entries from SP-1907-1931-OCR-image-regions.csv ...
319340 entries remain after filtering.
Application of lower threshold to width (100) ...
230788 regions remain after application of width threshold.
Application of lower threshold to height (100) ...
194282 regions remain after application of height threshold.
Processing 73758 unique image files ...
#:13:   0%|                                                             | 40/73758 [00:00<10:24, 117.98it/s]
(SPUNK-3.11) kai.labusch@lx0246:/data/kai.labusch/SPUNK/ImageRegions$ tree 24329435
24329435
└── 1931
    └── 1
        └── 1
            └── 1
                ├── 24329435-1931-1-1-1-1-0.jpeg
                ├── 24329435-1931-1-1-1-2-0.jpeg
                ├── 24329435-1931-1-1-1-2-1.jpeg
                ├── 24329435-1931-1-1-1-2-2.jpeg
                ├── 24329435-1931-1-1-1-5-0.jpeg
                ├── 24329435-1931-1-1-1-5-1.jpeg
                ├── 24329435-1931-1-1-1-5-2.jpeg
                ├── 24329435-1931-1-1-1-5-3.jpeg
                ├── 24329435-1931-1-1-1-5-4.jpeg
                ├── 24329435-1931-1-1-1-6-0.jpeg
                ├── 24329435-1931-1-1-1-6-1.jpeg
                ├── 24329435-1931-1-1-1-6-2.jpeg
                ├── 24329435-1931-1-1-1-6-3.jpeg
                ├── 24329435-1931-1-1-1-7-0.jpeg
                ├── 24329435-1931-1-1-1-8-0.jpeg
                └── 24329435-1931-1-1-1-8-1.jpeg

```
Mit dem --flat Parameter kann man erzwingen, dass keine Ordnerstruktur angelegt wird, sondern die Dateien "flach"
ins aktuelle Verzeichnis geschrieben werden:
```
(SPUNK-3.11) kai.labusch@lx0246:/data/kai.labusch/SPUNK/ImageRegions$ zefys-crop-images SP-1907-1931-OCR-image-regions.csv --flat --min-width=100 --min-height=100 --max-count=10 
Read 319340 entries from SP-1907-1931-OCR-image-regions.csv ...
319340 entries remain after filtering.
Application of lower threshold to width (100) ...
230788 regions remain after application of width threshold.
Application of lower threshold to height (100) ...
194282 regions remain after application of height threshold.
Processing 73758 unique image files ...
#:13:   0%|                                                             | 41/73758 [00:00<10:31, 116.75it/s]
(SPUNK-3.11) kai.labusch@lx0246:/data/kai.labusch/SPUNK/ImageRegions$ tree .
.
├── 24329435-1931-1-1-1-1-0.jpeg
├── 24329435-1931-1-1-1-2-0.jpeg
├── 24329435-1931-1-1-1-2-1.jpeg
├── 24329435-1931-1-1-1-2-2.jpeg
├── 24329435-1931-1-1-1-5-0.jpeg
├── 24329435-1931-1-1-1-5-1.jpeg
├── 24329435-1931-1-1-1-5-2.jpeg
├── 24329435-1931-1-1-1-5-3.jpeg
├── 24329435-1931-1-1-1-5-4.jpeg
├── 24329435-1931-1-1-1-6-0.jpeg
├── 24329435-1931-1-1-1-6-1.jpeg
├── 24329435-1931-1-1-1-6-2.jpeg
├── 24329435-1931-1-1-1-6-3.jpeg
├── 24329435-1931-1-1-1-7-0.jpeg
├── 24329435-1931-1-1-1-8-0.jpeg
├── 24329435-1931-1-1-1-8-1.jpeg
├── SP-1907-1931-OCR-image-regions.csv
├── SP-24353991-OCR-image-regions.csv
├── SP-2436020X-OCR-image-regions.csv
├── SP-27646518-OCR-image-regions.csv
└── SP-2812988X-OCR-image-regions.csv

```

Mit --min-width und --min-height kann man einen Schwellwert für die minimale Breite und Höhe der Regionen 
angeben. Defaultmäßig werden bei weglassen dieser Parameter alle Regionen extrahiert.

Mit --max-count kann man eine maximale Anzahl von zu extrahierenden Regionen angeben - wenn man z.B. nur testweise
10 Regionen extrahieren möchte.

Mit --dry-run kann man sich einfach nur anschauen was er täte - ohne das tatsächlich etwas geschrieben wird.

