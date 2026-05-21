W3C_ANNO=article-separation-annotations-2026-05-19-19-19-07.839805.json
W3C_ANNO_ERRORS=article-separation-annotations-2026-05-19-19-19-07.839805-errors.md
MODELS=models
IMAGES=SBB-images
SEGMENTATION=ey-seg-$(IMAGES)
OCR=ey-ocr-$(IMAGES)

segmentation: 
	mkdir -p "$(SEGMENTATION)"
	ln -rfn -s "$(IMAGES)" "$(SEGMENTATION)/$(IMAGES)"
	eynollah layout -m "$(MODELS)" -di "$(IMAGES)" -o "$(SEGMENTATION)" -light -tll -fl
ocr: segmentation
	mkdir -p "$(OCR)"
	ln -rfn -s "$(IMAGES)" "$(OCR)/$(IMAGES)"
	eynollah ocr -bs 64 -m "$(MODELS)" -di "$(IMAGES)" -dx "$(SEGMENTATION)" -o "$(OCR)"

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

all:	link download-images gt match-articles

zip:
	rm -f SBB.zip
	zip -r SBB.zip $(OCR)

remove-not-done:
	cd ey-ocr-SBB-images;rm -f SNP24353991-18910313-1-4-0-0.xml SNP24353991-18910313-1-5-0-0.xml SNP30744556-19140412-0-17-0-0.xml SNP28028685-18920124-0-6-0-0.xml SNP28409322-19080716-0-3-0-0.xml SNP27825061-18540207-0-4-0-0.xml
