# (S)prach(U)nabhängiger (N)achrichten(K)osmos

## ZEFYS digitization statistics

Preliminaries: /zefys/archive must be mounted to or point to b-isiprod-udl.pk.de:/ifs/data/SBB/archive/zefys .

There are [Markdown](artifacts/statistics.md) and [HTML](artifacts/statistics.html) files that provide a  statistical overview of the newspaper page scans that are currently contained in the ZEFYS archive.

This statistics can be updated by running
```
make nfs-scan
make run-zefys-statistics
```
The [make target "run-zefys-statistics"](Makefile) re-runs a [jupyter notebook](notebooks/zefys-statistics.ipynb) that contains all the details.




