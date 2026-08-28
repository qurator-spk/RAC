W3C_ANNO=article-separation-annotations-2026-05-19-19-19-07.839805.json
W3C_ANNO_ERRORS=article-separation-annotations-2026-05-19-19-19-07.839805-errors.md
IMAGES=SBB-images

download-images:
	download-w3c-annotation-images --from-zefys $(W3C_ANNO) $(IMAGES)

gt-SBB.tsv:
	compile-article-separation-gt $(W3C_ANNO) gt-SBB.tsv
gt-NLF.tsv:
	extract-article-separation GT-ArticleSeparation-NewsEye/NLF-finnish-valid gt-NLF.tsv --mode=nlf
gt-BnF.tsv:
	extract-article-separation GT-ArticleSeparation-NewsEye/BnF-valid gt-BnF.tsv --mode=bnf

gt: gt-SBB.tsv gt-NLF.tsv gt-BnF.tsv

match-gt-NLF-gt-layout-ocr.tsv:
	match-article-sequences gt-NLF.tsv GT-ArticleSeparation-NewsEye/NLF-finnish-valid match-gt-NLF-gt-layout-ocr.tsv
match-gt-BnF-gt-layout-ocr.tsv:
	match-article-sequences gt-BnF.tsv GT-ArticleSeparation-NewsEye/BnF-valid match-gt-BnF-gt-layout-ocr.tsv

match-gt-BnF-eynollah-layout-ocr.tsv:
	match-article-sequences gt-BnF.tsv ey-ocr-BnF-images match-gt-BnF-eynollah-layout-ocr.tsv
match-gt-NLF-eynollah-layout-ocr.tsv:
	match-article-sequences gt-NLF.tsv ey-ocr-NLF-images match-gt-NLF-eynollah-layout-ocr.tsv
match-gt-SBB-eynollah-layout-ocr.tsv:
	match-article-sequences gt-SBB.tsv ey-ocr-SBB-images match-gt-SBB-eynollah-layout-ocr.tsv

match-gt-BnF-pero-layout-ocr.tsv:
	match-article-sequences gt-BnF.tsv pero-ocr-BnF-images match-gt-BnF-pero-layout-ocr.tsv
match-gt-NLF-pero-layout-ocr.tsv:
	match-article-sequences gt-NLF.tsv pero-ocr-NLF-images match-gt-NLF-pero-layout-ocr.tsv
match-gt-SBB-pero-layout-ocr.tsv:
	match-article-sequences gt-SBB.tsv pero-ocr-SBB-images match-gt-SBB-pero-layout-ocr.tsv


match-articles: match-gt-NLF-gt-layout-ocr.tsv match-gt-BnF-gt-layout-ocr.tsv match-gt-BnF-eynollah-layout-ocr.tsv match-gt-NLF-eynollah-layout-ocr.tsv match-gt-SBB-eynollah-layout-ocr.tsv match-gt-SBB-pero-layout-ocr.tsv match-gt-BnF-pero-layout-ocr.tsv match-gt-NLF-pero-layout-ocr.tsv

compute-rac:
	compute-rac --article-tsv-file gt-SBB.tsv --match-tsv-file match-gt-SBB-eynollah-layout-ocr.tsv --article-tsv-file gt-NLF.tsv --match-tsv-file match-gt-NLF-eynollah-layout-ocr.tsv --article-tsv-file gt-BnF.tsv --match-tsv-file match-gt-BnF-eynollah-layout-ocr.tsv

eval:
	evaluate-article-matching gt-BnF.tsv match-gt-BnF-gt-layout-ocr.tsv
	evaluate-article-matching gt-BnF.tsv match-gt-BnF-eynollah-layout-ocr.tsv
	evaluate-article-matching gt-BnF.tsv match-gt-BnF-pero-layout-ocr.tsv
	evaluate-article-matching gt-NLF.tsv match-gt-NLF-gt-layout-ocr.tsv
	evaluate-article-matching gt-NLF.tsv match-gt-NLF-eynollah-layout-ocr.tsv
	evaluate-article-matching gt-NLF.tsv match-gt-NLF-pero-layout-ocr.tsv
	evaluate-article-matching gt-SBB.tsv match-gt-SBB-eynollah-layout-ocr.tsv
	evaluate-article-matching gt-SBB.tsv match-gt-SBB-pero-layout-ocr.tsv

link:
	rm -f w3c-anno.json
	ln -sfn $(W3C_ANNO) w3c-anno.json 
	rm -f errors.md
	ln -sfn $(W3C_ANNO_ERRORS) errors.md

all:	link download-images gt match-articles eval compute-rac

CLI_DOC_FILE=doc/CLI.md

%-command-doc:
	echo "## $*" >> $(CLI_DOC_FILE)
	echo \`\`\` >> $(CLI_DOC_FILE)
	echo `$* --help | base64 -w0` | base64 -d >> $(CLI_DOC_FILE)
	echo \`\`\` >> $(CLI_DOC_FILE)

CLI-MD-HEADER:
	rm $(CLI_DOC_FILE)

CLI-MD: CLI-MD-HEADER compute-rac-command-doc evaluate-article-matching-command-doc extract-article-separation-command-doc match-article-sequences-command-doc compile-article-separation-gt-command-doc download-w3c-annotation-images-command-doc

