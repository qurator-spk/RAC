## compute-rac
```
Usage: compute-rac [OPTIONS]

Options:
  --article-tsv-file PATH
  --match-tsv-file PATH
  --mode [all|multi-part-one-page]
                                  Perform RAC computation either for all
                                  articles or only for multi part articles
                                  that do not span multiple pages.
  --help                          Show this message and exit.
```
## evaluate-article-matching
```
Usage: evaluate-article-matching [OPTIONS] GT_TSV_FILE MATCH_TSV_FILE

Options:
  --help  Show this message and exit.
```
## extract-article-separation
```
Usage: extract-article-separation [OPTIONS] DIRECTORY OUT_FILE

  A tool that extracts the article separation information from the PAGE-XML
  files of NLF and BnF datasets into a TSV-file (OUT_FILE) that describes one
  article polygon per line and in its entirety corresponds to the article
  polygon sequence of the dataset where the article polygons are the
  <TextRegions> in the XML-files.

  The XML-files to be processed are found by recursively parsing DIRECTORY.

Options:
  --pattern TEXT     Consider only XML-files that match this pattern. Default:
                     *.xml.
  --follow-symlinks  Follow symlinks while traversing the DIRECTORY.
  --mode [bnf|nlf]   File parse mode that defines how meta-data information is
                     extracted from the filename - if possible. Default: bnf
  --help             Show this message and exit.
```
## match-article-sequences
```
Usage: match-article-sequences [OPTIONS] GT_TSV_FILE XML_DIR OUT_FILE

  A tool that takes the article-polygon-sequence TSV files - obtained by
  either compile-article-separation-gt or extract-article-separation - as well
  as a directory (XML_DIR) with PAGE-XML files as inputs. For each text line
  in the PAGE-XML- files, the article polygon of largest intersection in the
  TSV file is determined. A matching-TSV file is produced, that corresponds to
  the <TextLine> sequence of the entire PAGE-XML input directory mapped to the
  TSV polygons, first order sorted by page sequence, second order sorted by
  page, and third order sorted by the reading order defined in the PAGE-XML
  files.

Options:
  --help  Show this message and exit.
```
## compile-article-separation-gt
```
Usage: compile-article-separation-gt [OPTIONS] W3C_ANNO_JSON OUT_TSV

  A tool that compiles the W3C-JSON file into a tab separated value file
  (OUT_TSV) that describes one article polygon per line and in its entirety
  corresponds to the article polygon sequence of the dataset including all
  pages.

  The tool checks the annotations for consistency - as far as this can be done
  automatically - and writes errors to stdout.

  The W3C-JSON file has been created with the region annotation tool:
  https://github.com/qurator-spk/sbb_images/blob/6623081cd1b80864e6eca85ab4d7940f5045d1b8/doc/region-annotator.md

Options:
  --check-only  Do not write TSV but output only consistency checks.
  --help        Show this message and exit.
```
## download-w3c-annotation-images
```
Usage: download-w3c-annotation-images [OPTIONS] W3C_ANNO_JSON TARGET_DIR

  Batch download of images referenced in a W3C-Annotation-JSON file (W3C-ANNO-
  JSON) and write them to TARGET_DIR.

Options:
  --from-zefys     Special treatment for ZEFYS links.
  --user TEXT      Username for basic auth.
  --password TEXT  Password for basic auth
  --help           Show this message and exit.
```
