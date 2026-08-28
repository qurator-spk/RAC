# Reading Order Article Coherence Toolbox

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
Install RAC:
```
pip install git+https://github.com/qurator-spk/RAC.git
```


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
    NFS[NFS-filesystem e.g. /nfs/zefys] --> |zefys-scanner| ZEFYS-FILELIST(ZEFYS-filelist)
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