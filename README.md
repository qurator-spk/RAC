# (S)prach(U)nabhängiger (N)achrichten(K)osmos

![greenland](doc/greenland.png) 

![persil](doc/persil.png)

![finnland](doc/finnland.png)

---

## Installation

Required python version is 3.11. 
Consider use of [pyenv](https://github.com/pyenv/pyenv) if that python version is not available on your system. 

Activate virtual environment (virtualenv):
```
source venv/bin/activate
```
or (pyenv):
```
pyenv activate my-python-3.11-virtualenv
```

Update pip:
```
pip install -U pip
```
Install SPUNK:
```
pip install git+https://code.dev.sbb.berlin/idm4/SPUNK.git
```

## ZEFYS digitization statistics

Preliminaries: /zefys/archive must be mounted to or point to b-isiprod-udl.pk.de:/ifs/data/SBB/archive/zefys .

There are [Markdown](artifacts/statistics.md) and [HTML](artifacts/statistics.html) files that provide a  statistical overview of the newspaper page scans that are currently contained in the ZEFYS archive.

This statistics can be updated by running
```
make nfs-scan
make run-zefys-statistics
```
The [make target "run-zefys-statistics"](Makefile) re-runs a [jupyter notebook](notebooks/zefys-statistics.ipynb) that contains all the details.


## Workflow

* [zefys-scanner](doc/CLI.md#zefys-scanner) | [zefys-downloader](doc/CLI.md#zefys-downloader)
* [zefys-ocr-database](doc/CLI.md#zefys-ocr-database) 
| [zefys-unpack-ocr-database](doc/CLI.md#zefys-unpack-ocr-database)
| [zefys-join-ocr-databases](doc/CLI.md#zefys-join-ocr-databases)
| [zefys-ocr-filelist](doc/CLI.md#zefys-ocr-filelist)
* [create-article-database](doc/CLI.md#create-article-database)
| [article-json-export](doc/CLI.md#article-json-export)
* [zefys-create-embeddings](doc/CLI.md#zefys-create-embeddings)
* [compute-summaries](doc/CLI.md#compute-summaries)
* [zefys-create-solr-index](doc/CLI.md#zefys-create-solr-index)
| [query-solr-index](doc/CLI.md#query-solr-index)
* [zefys-create-annoy-index](doc/CLI.md#zefys-create-annoy-index)

```mermaid
graph TD
    NFS[NFS-filesystem e.g. /nfs/zefys] -->|zefys-scanner| ZEFYS-FILELIST(ZEFYS-filelist)
    ZEFYS-FILELIST -->|zefys-downloader| BATCH-DIRECTORIES(batch directories)
    BATCH-DIRECTORIES -->|eynollah| PAGE-XMLS(page XML files)
    PAGE-XMLS -->|zefys-ocr-database| OCR-DATABASE(compressed sqlite OCR-database)
    OCR-DATABASE -->|create-article-database| ARTICLE-DATABASE(article database)
    ARTICLE-DATABASE -->|article-json-export| ARTICLE-JSON(articles as JSON)
    OCR-DATABASE -->|zefys-unpack-ocr-database| PAGE-XMLS
    OCR-DATABASE -->|zefys-ocr-filelist| OCR-FILELIST(filelist of archive as TSV file)
    OCR-DATABASE-2(Another OCR database) -->|zefys-join-ocr-databases| JOINED-OCR-DATABASE(joined OCR-database)
    OCR-DATABASE -->|zefys-join-ocr-databases| JOINED-OCR-DATABASE(joined OCR-database)
    ARTICLE-DATABASE -->|zefys-create-embeddings| EMBEDDING-DATABASE(embedding database)
    ARTICLE-DATABASE -->|compute summaries| SUMMARIES(summaries) --> ARTICLE-DATABASE
    EMBEDDING-DATABASE -->|zefys-create-solr-index| SOLR-INDEX(Apache solr index)
    EMBEDDING-DATABASE -->|zefys-create-annoy-index| ANNOY-INDEX(annoy index)
    SOLR-INDEX --> WEB-INTERFACE(web interface)
    SOLR-INDEX -->|query-solr-index| QUERY-RESULT(query results / quantitative evaluation)
```