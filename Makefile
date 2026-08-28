W3C_ANNO=article-separation-annotations-2026-05-19-19-19-07.839805.json
W3C_ANNO_ERRORS=article-separation-annotations-2026-05-19-19-19-07.839805-errors.md
IMAGES=SBB-images

download-images:
	download-w3c-annotation-images --from-zefys $(W3C_ANNO) $(IMAGES)

art-SBB.tsv:
	compile-article-separation-gt $(W3C_ANNO) art-SBB.tsv
art-NLF.tsv:
	extract-article-separation NewsEye/NLF-finnish-valid art-NLF.tsv --mode=nlf
art-BnF.tsv:
	extract-article-separation NewsEye/BnF-valid art-BnF.tsv --mode=bnf

extract-article-separation: art-SBB.tsv art-NLF.tsv art-BnF.tsv

match-art-NLF-layout-ocr.tsv:
	match-article-sequences art-NLF.tsv NewsEye/NLF-finnish-valid match-art-NLF-layout-ocr.tsv
match-art-BnF-layout-ocr.tsv:
	match-article-sequences art-BnF.tsv NewsEye/BnF-valid match-art-BnF-layout-ocr.tsv

match-art-BnF-eynollah-layout-ocr.tsv:
	match-article-sequences art-BnF.tsv ey-ocr-BnF-images match-art-BnF-eynollah-layout-ocr.tsv
match-art-NLF-eynollah-layout-ocr.tsv:
	match-article-sequences art-NLF.tsv ey-ocr-NLF-images match-art-NLF-eynollah-layout-ocr.tsv
match-art-SBB-eynollah-layout-ocr.tsv:
	match-article-sequences art-SBB.tsv ey-ocr-SBB-images match-art-SBB-eynollah-layout-ocr.tsv

match-art-BnF-pero-layout-ocr.tsv:
	match-article-sequences art-BnF.tsv pero-ocr-BnF-images match-art-BnF-pero-layout-ocr.tsv
match-art-NLF-pero-layout-ocr.tsv:
	match-article-sequences art-NLF.tsv pero-ocr-NLF-images match-art-NLF-pero-layout-ocr.tsv
match-art-SBB-pero-layout-ocr.tsv:
	match-article-sequences art-SBB.tsv pero-ocr-SBB-images match-art-SBB-pero-layout-ocr.tsv


match-articles: match-art-NLF-layout-ocr.tsv match-art-BnF-layout-ocr.tsv match-art-BnF-eynollah-layout-ocr.tsv match-art-NLF-eynollah-layout-ocr.tsv match-art-SBB-eynollah-layout-ocr.tsv match-art-SBB-pero-layout-ocr.tsv match-art-BnF-pero-layout-ocr.tsv match-art-NLF-pero-layout-ocr.tsv

compute-rac:
	compute-rac --article-tsv-file art-SBB.tsv --match-tsv-file match-art-SBB-eynollah-layout-ocr.tsv --article-tsv-file art-NLF.tsv --match-tsv-file match-art-NLF-eynollah-layout-ocr.tsv --article-tsv-file art-BnF.tsv --match-tsv-file match-art-BnF-eynollah-layout-ocr.tsv
	compute-rac --article-tsv-file art-SBB.tsv --match-tsv-file match-art-SBB-pero-layout-ocr.tsv --article-tsv-file art-NLF.tsv --match-tsv-file match-art-NLF-pero-layout-ocr.tsv --article-tsv-file art-BnF.tsv --match-tsv-file match-art-BnF-pero-layout-ocr.tsv

eval:
	evaluate-article-matching art-BnF.tsv match-art-BnF-layout-ocr.tsv
	evaluate-article-matching art-BnF.tsv match-art-BnF-eynollah-layout-ocr.tsv
	evaluate-article-matching art-BnF.tsv match-art-BnF-pero-layout-ocr.tsv
	evaluate-article-matching art-NLF.tsv match-art-NLF-layout-ocr.tsv
	evaluate-article-matching art-NLF.tsv match-art-NLF-eynollah-layout-ocr.tsv
	evaluate-article-matching art-NLF.tsv match-art-NLF-pero-layout-ocr.tsv
	evaluate-article-matching art-SBB.tsv match-art-SBB-eynollah-layout-ocr.tsv
	evaluate-article-matching art-SBB.tsv match-art-SBB-pero-layout-ocr.tsv

link:
	rm -f w3c-anno.json
	ln -sfn $(W3C_ANNO) w3c-anno.json 
	rm -f errors.md
	ln -sfn $(W3C_ANNO_ERRORS) errors.md

all:	link download-images extract-article-separation match-articles eval compute-rac

CLI_DOC_FILE=doc/CLI.md

%-command-doc:
	echo "## $*" >> $(CLI_DOC_FILE)
	echo \`\`\` >> $(CLI_DOC_FILE)
	echo `$* --help | base64 -w0` | base64 -d >> $(CLI_DOC_FILE)
	echo \`\`\` >> $(CLI_DOC_FILE)

CLI-MD-HEADER:
	rm $(CLI_DOC_FILE)

CLI-MD: CLI-MD-HEADER compute-rac-command-doc evaluate-article-matching-command-doc extract-article-separation-command-doc match-article-sequences-command-doc compile-article-separation-gt-command-doc download-w3c-annotation-images-command-doc

