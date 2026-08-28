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

* [compile-article-separation-gt](doc/CLI.md#compile-article-separation-gt)
* [extract-article-separation](doc/CLI.md#extract-article-separation) 
| [match-article-sequences](doc/CLI.md#zefys-unpack-ocr-database)
| [compute-rac](doc/CLI.md#compute-rac)
| [evaluate-article-matching](doc/CLI.md#evaluate-article-matching)
* [download-w3c-annotation-images](doc/CLI.md#download-w3c-annotation-images)
| 

See also [Makefile](Makefile).

```mermaid
graph TD
    W3C-ANNO-JSON[W3C-ANNO-JSON file created with Annotationtool] --> COMPILE-ARTICLE-SEPARATION([compile-article-separation-gt])
    COMPILE-ARTICLE-SEPARATION --> ARTICLE-POLYGON-TSV(ARTICLE-POLYGON-TSV)
    PAGE-XML-ARTICLE-ID["Directory with PAGE-XML files that have TextRegion-XML elements and Article-ID attributes in NewsEye style"] --> EXTRACT-ARTICLE-SEPARATION([extract-article-separation])
    EXTRACT-ARTICLE-SEPARATION --> ARTICLE-POLYGON-TSV
    ARTICLE-POLYGON-TSV --> MATCH-ARTICLE-SEQUENCE([match-article-sequence])
    MATCH-ARTICLE-SEQUENCE --> MATCHING-FILE(Matching file)
    PAGE-XML-LAYOUT-READING_ORDER(Directory with PAGE-XML files that have a reading order) --> MATCH-ARTICLE-SEQUENCE
    MATCHING-FILE --> COMPUTE-RAC([compute-rac]) 
    ARTICLE-POLYGON-TSV --> COMPUTE-RAC
    COMPUTE-RAC --> RAC-CSW(RAC-CSW Table)
    W3C-ANNO-JSON --> DOWNLOAD-W3C-ANNOTATION-IMAGES(download-w3c-annotation-images)
    DOWNLOAD-W3C-ANNOTATION-IMAGES --> IMAGE-DIR(Directory containing the images referenced in the W3C-ANNO-JSON)

    MATCHING-FILE --> EVALUATE-ARTICLE-MATCHING([evaluate-article-matching]) 
    ARTICLE-POLYGON-TSV --> EVALUATE-ARTICLE-MATCHING
    EVALUATE-ARTICLE-MATCHING --> EVALUATION-REPORT[Evaluation report]
     
```
