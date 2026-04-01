## zefys-scanner
```
Usage: zefys-scanner [OPTIONS] OUT_FILE

  Recursively search some directory for image files. Process the filenames of
  the found files with regular expressions in order to extract information
  such as ZDB_ID, YEAR, MONTH, DAY, ISSUE, PAGE from them. Output a tab
  separated value file (TSV) that contains all this information for further
  use for instance with zefys-downloader.

Options:
  --directory TEXT         Recursively search image files in the directory.
                           See also options: pattern, follow-symlinks, subset-
                           json, subset-dirs-json
  --zefys-filelist TEXT    A pre-computed image file list as text file. One
                           image file with absolute path per line. Can be
                           obtained for instance from running in /nfs/zefys
                           (takes roughly 24 hours!):         find ./
                           -wholename "*/presentation/*.jpg"    -o -wholename
                           "*/presentation/*.jpeg"   -o -wholename
                           "*/presentation/*.png" > zefys_image_files.txt
  --pattern TEXT           File pattern to search for in case of directory
                           search. Default: ["*/presentation/*.jpg",
                           "*/presentation/*.jpeg", "*/presentation/*.png"
                           ]Can be used in order to consider only a particular
                           subset of subdirectories in the recursive search,
                           for instance */presentation/*.jpg considers only
                           .jpg files located in a subdirectory "presentation"
  --follow-symlinks
  --subset-json PATH       Consider only the subset of page-XML files defined
                           in this json file.
  --subset-dirs-json PATH  Recursively search only through a subset of sub-
                           directories as defined in this json file.
  --help                   Show this message and exit.
```
## zefys-downloader
```
Usage: zefys-downloader [OPTIONS] SCAN_IMAGES_FILE TARGET_PATH

  The tool either creates symlinks to ZEFYS image files or downloads ZEFYS
  image files in full resolution from the SBB content server. The option
  --zefys-prefix controls if sysmlinks are used or rather the files are
  downloaded from the content server. If --zefys-prefix is provided, it should
  point to a directory where the ZEFYS NFS is mounted. Then the resulting
  batch directories will only contain sysmlinks to the full resolution images.
  If --zefys-prefix is omitted then the images would be downloaded. The
  symlinks or files are stored in a batch directory structure where the option
  --batch-size controls how many items are stored per batch directory. Which
  newspapers and time periods are included can be controlled by the --zdb-id,
  --year, --month ... options.

  SCAN_IMAGES_FILE: A TSV file containing of list of all ZEFYS page scan image
  files that are to be considered. This file can be created with zefys-
  scanner.

  TARGET_PATH: Either the name of the new directory where the symlinks or
  downloaded images are stored if batch-size is omitted or a prefix for the
  batch directories names to be created if batch-size is specified.

Options:
  --zefys-prefix TEXT    ZEFYY NFS storage path. If specified only symlinks to
                         this location will be created.
  --zdb-id TEXT          Consider only this ZDB-ID (can be supplied multiple
                         times).
  --year INTEGER         Consider only this year (can be supplied multiple
                         times).
  --start-year INTEGER   Consider a time interval [start-year, stop-year[
  --stop-year INTEGER    Consider a time interval [start-year, stop-year[
  --month INTEGER        Consider only this month (can be supplied multiple
                         times).
  --start-month INTEGER  Consider a time interval [start-month, stop-month[
  --stop-month INTEGER   Consider a time interval [start-month, stop-month[
  --day INTEGER          Consider only this day (can be supplied multiple
                         times).
  --start-day INTEGER    Consider a time interval [start-day, stop-day[
  --stop-day INTEGER     Consider a time interval [start-day, stop-day[
  --issue INTEGER        Consider only this issue (can be supplied multiple
                         times).
  --start-issue INTEGER  Consider a time interval [start-issue, stop-issue[
  --stop-issue INTEGER   Consider a time interval [start-issue, stop-issue[
  --page INTEGER         Consider only this page (can be supplied multiple
                         times).
  --start-page INTEGER   Consider a page interval [start-page, stop-page[
  --stop-page INTEGER    Consider a page interval [start-page, stop-page[
  --language INTEGER     Consider only this language (can be supplied multiple
                         times).
  --batch-size INTEGER   Split into batches of this size.
  --start-batch INTEGER  Ignore all batches before start-batch.
  --num-batches INTEGER  Create at most num-batches.
  --exclude-tsv PATH     Exclude the files listed in this TSV file. Can be
                         supplied multiple times
  --dry-run              Do not actually do anything.
  --help                 Show this message and exit.
```
## zefys-ocr-database
```
Usage: zefys-ocr-database [OPTIONS] DIRECTORY SQLITE_FILE

  Creates, appends to, or updates a (new) SQLITE database where the PAGE-XML-
  OCR files are stored as ZIP-compressed binary blobs. This enables space
  efficient storage, performant access with respect to the properties ZDB-ID,
  YEAR, MONTH, DAY, ISSUE, and PAGE. Additionally, these SQLITE database files
  can be efficiently copied between different host computers, for instance by
  "scp".

  The tool expects the PAGE-XML filenames to have the following structure:
  ZDBID-YEAR-MONTH-DAY-ISSUE-PAGE.xml .

  All the XML-files in the database or a particular subset of them can be
  extract by the command "zefys-unpack-ocr-database".

  DIRECTORY: Recursively search XML files in this directory. SQLITE_FILE: The
  database file.

Options:
  --pattern TEXT           File pattern to search for. Default: *.xml . Can be
                           used in order to consider only a particular subset
                           of subdirectories in the recursive search, for
                           instance */ey-ocr*/*.xml considers only XML files
                           located in a subdirectory that starts with ey-
                           ocr...
  --append                 Append to database file instead of creating a new
                           one. Entries that already exist for a particular
                           combination of ZDB-ID,YEAR,MONTH,DAY,ISSUE, and
                           PAGE will be ignored. Only new entries will be
                           added.
  --update                 Update database file instead of creating a new one.
                           If a particular combination of ZDB-
                           ID,YEAR,MONTH,DAY,ISSUE, and PAGE alreadys exists
                           it would be replaced by the new file.
  --follow-symlinks
  --subset-json PATH       Consider only the subset of page-XML files defined
                           in this json file.
  --subset-dirs-json PATH  Recursively search only through a subset of sub-
                           directories as defined in this json file.
  --processes INTEGER      Number of parallel processes to be used. (default
                           all cores)
  --help                   Show this message and exit.
```
## zefys-unpack-ocr-database
```
Usage: zefys-unpack-ocr-database [OPTIONS] SQLITE_FILE

Options:
  --flat                 Do not create a directory structure.
  --processes INTEGER    Number of parallel processes to be used. (default all
                         cores)
  --download-images      Download corresponding images from SBB content
                         server.BEWARE: USE WITH CARE!!!!!
  --dry-run              Do not actually unpack anything.
  --zdb-id TEXT          Consider only this ZDB-ID (can be supplied multiple
                         times).
  --year INTEGER         Consider only this year (can be supplied multiple
                         times).
  --start-year INTEGER   Consider a time interval [start-year, stop-year[
  --stop-year INTEGER    Consider a time interval [start-year, stop-year[
  --month INTEGER        Consider only this month (can be supplied multiple
                         times).
  --start-month INTEGER  Consider a time interval [start-month, stop-month[
  --stop-month INTEGER   Consider a time interval [start-month, stop-month[
  --day INTEGER          Consider only this day (can be supplied multiple
                         times).
  --start-day INTEGER    Consider a time interval [start-day, stop-day[
  --stop-day INTEGER     Consider a time interval [start-day, stop-day[
  --issue INTEGER        Consider only this issue (can be supplied multiple
                         times).
  --start-issue INTEGER  Consider a time interval [start-issue, stop-issue[
  --stop-issue INTEGER   Consider a time interval [start-issue, stop-issue[
  --page INTEGER         Consider only this page (can be supplied multiple
                         times).
  --start-page INTEGER   Consider a page interval [start-page, stop-page[
  --stop-page INTEGER    Consider a page interval [start-page, stop-page[
  --help                 Show this message and exit.
```
## zefys-join-ocr-databases
```
Usage: zefys-join-ocr-databases [OPTIONS] TARGET_SQLITE [SOURCE_SQLITE]...

Options:
  --help  Show this message and exit.
```
## zefys-ocr-filelist
```
Usage: zefys-ocr-filelist [OPTIONS] SQLITE_FILE TSV_FILE_OUT

Options:
  --help  Show this message and exit.
```
## create-article-database
```
Usage: create-article-database [OPTIONS] OCR_DB_SQLITE SQLITE_FILE



Options:
  --processes INTEGER    Number of parallel processes to be used. (default all
                         cores)
  --zdb-id TEXT          Consider only this ZDB-ID (can be supplied multiple
                         times).
  --year INTEGER         Consider only this year (can be supplied multiple
                         times).
  --start-year INTEGER   Consider a time interval [start-year, stop-year[
  --stop-year INTEGER    Consider a time interval [start-year, stop-year[
  --month INTEGER        Consider only this month (can be supplied multiple
                         times).
  --start-month INTEGER  Consider a time interval [start-month, stop-month[
  --stop-month INTEGER   Consider a time interval [start-month, stop-month[
  --day INTEGER          Consider only this day (can be supplied multiple
                         times).
  --start-day INTEGER    Consider a time interval [start-day, stop-day[
  --stop-day INTEGER     Consider a time interval [start-day, stop-day[
  --issue INTEGER        Consider only this issue (can be supplied multiple
                         times).
  --start-issue INTEGER  Consider a time interval [start-issue, stop-issue[
  --stop-issue INTEGER   Consider a time interval [start-issue, stop-issue[
  --page INTEGER         Consider only this page (can be supplied multiple
                         times).
  --start-page INTEGER   Consider a page interval [start-page, stop-page[
  --stop-page INTEGER    Consider a page interval [start-page, stop-page[
  --help                 Show this message and exit.
```
## article-json-export
```
Usage: article-json-export [OPTIONS] ART_DB_SQLITE

Options:
  --json-file PATH
  --json-single-line-file PATH
  --zdb-json-meta-file PATH
  --zdb-id TEXT                 Consider only this ZDB-ID (can be supplied
                                multiple times).
  --year INTEGER                Consider only this year (can be supplied
                                multiple times).
  --start-year INTEGER          Consider a time interval [start-year, stop-
                                year[
  --stop-year INTEGER           Consider a time interval [start-year, stop-
                                year[
  --month INTEGER               Consider only this month (can be supplied
                                multiple times).
  --start-month INTEGER         Consider a time interval [start-month, stop-
                                month[
  --stop-month INTEGER          Consider a time interval [start-month, stop-
                                month[
  --day INTEGER                 Consider only this day (can be supplied
                                multiple times).
  --start-day INTEGER           Consider a time interval [start-day, stop-day[
  --stop-day INTEGER            Consider a time interval [start-day, stop-day[
  --issue INTEGER               Consider only this issue (can be supplied
                                multiple times).
  --start-issue INTEGER         Consider a time interval [start-issue, stop-
                                issue[
  --stop-issue INTEGER          Consider a time interval [start-issue, stop-
                                issue[
  --page INTEGER                Consider only this page (can be supplied
                                multiple times).
  --start-page INTEGER          Consider a page interval [start-page, stop-
                                page[
  --stop-page INTEGER           Consider a page interval [start-page, stop-
                                page[
  --help                        Show this message and exit.
```
## zefys-create-embeddings
```
Usage: zefys-create-embeddings [OPTIONS] ART_DB_SQLITE EMB_DB_SQLITE MODEL_DIR

Options:
  --processes INTEGER
  --max-token-length INTEGER
  --batch-size INTEGER
  --help                      Show this message and exit.
```
## compute-summaries
```
Usage: compute-summaries [OPTIONS] ART_DB_SQLITE MODEL

Options:
  --zdb-id TEXT             Consider only this ZDB-ID (can be supplied
                            multiple times).
  --year INTEGER            Consider only this year (can be supplied multiple
                            times).
  --start-year INTEGER      Consider a time interval [start-year, stop-year[
  --stop-year INTEGER       Consider a time interval [start-year, stop-year[
  --month INTEGER           Consider only this month (can be supplied multiple
                            times).
  --start-month INTEGER     Consider a time interval [start-month, stop-month[
  --stop-month INTEGER      Consider a time interval [start-month, stop-month[
  --day INTEGER             Consider only this day (can be supplied multiple
                            times).
  --start-day INTEGER       Consider a time interval [start-day, stop-day[
  --stop-day INTEGER        Consider a time interval [start-day, stop-day[
  --issue INTEGER           Consider only this issue (can be supplied multiple
                            times).
  --start-issue INTEGER     Consider a time interval [start-issue, stop-issue[
  --stop-issue INTEGER      Consider a time interval [start-issue, stop-issue[
  --page INTEGER            Consider only this page (can be supplied multiple
                            times).
  --start-page INTEGER      Consider a page interval [start-page, stop-page[
  --stop-page INTEGER       Consider a page interval [start-page, stop-page[
  --prompt TEXT             Prompt identifier (see summary_prompts.py).
                            Default: prompt_BASIC_1_S_EN
  --max-new-tokens INTEGER  Maximum number of tokens per summary. Default 512
  --temperature FLOAT       Randomness temperature for generation.Default is
                            deterministic generation.
  --random                  Specify this to randomly select articles for
                            generation.
  --processes INTEGER       Number of HTTP request processes.
  --ollama-url TEXT         Ollama URL. Can be supplied multiple times.
                            Example http://localhost:11434 .
  --help                    Show this message and exit.
```
## zefys-create-solr-index
```
Usage: zefys-create-solr-index [OPTIONS] EMB_DB_SQLITE SOLR_CORE_URL

  EMB_DB_SQLITE: sqlite database that holds the embeddings to be imported.
  SOLR_CORE_URL: Example: http://localhost:8983/solr/test .

Options:
  --embedding-dim [128|256|512|768]
                                  Use first N dimensions of embeddings.
                                  Default 128.
  --hnsw-beam-width [16|32|64]
  --hnsw-max-connections [100|200|400]
  --collation-mode [raw|mean|max|min|absminmax]
                                  How to collate multiple embeddings of longer
                                  texts. Default: raw => do not collate at
                                  all.
  --stop-at INTEGER               Process only the first N embeddings.
                                  Default: Process all.
  --skip-first INTEGER            Skip the first N embeddings. Default: skip
                                  nothing.
  --chunk-size INTEGER            Commit in chunks of size N to solr. Default
                                  100000.
  --processes INTEGER             Number of concurrent data feeder processes.
                                  Default 10.
  --help                          Show this message and exit.
```
## query-solr-index
```
Usage: query-solr-index [OPTIONS]

Options:
  --solr-core-url TEXT
  --model-dir PATH
  --query-text TEXT
  --k INTEGER                     k. Default 10.
  --limit-factor INTEGER          Limit. Default 10.
  --embedding-dim [128|256|512|768]
                                  Use first N dimensions of embeddings.
                                  Default 128.
  --hnsw-beam-width [16|32|64]
  --hnsw-max-connections [100|200|400]
  --collation-mode [raw|mean|max|min|absminmax]
                                  How to collate multiple embeddings of longer
                                  texts. Default: mean.
  --art-db-sqlite PATH
  --summaries-db PATH
  --query-result-db PATH
  --write-query-json PATH
  --stop-at INTEGER
  --processes INTEGER
  --chunk-size INTEGER
  --help                          Show this message and exit.
```
## zefys-create-annoy-index
```
Usage: zefys-create-annoy-index [OPTIONS] EMB_DB_SQLITE

Options:
  --dist-measure TEXT      Distance measure of the approximate nearest
                           neighbour index. default: angular.
  --n-trees INTEGER        Number of search trees. Default 10.
  --shard TEXT
  --embedding-dim INTEGER
  --stop-at INTEGER
  --help                   Show this message and exit.
```
