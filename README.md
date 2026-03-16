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




