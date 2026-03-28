CLI_DOC_FILE=doc/CLI.md


nfs-scan:
	cd /zefys/archive;find ./ -wholename "*/presentation/*.jpg" -o -wholename "*/presentation/*.jpeg" -o -wholename "*/presentation/*.png" > ~/SPUNK/workbench/zefys_image_files.txt
run-zefyAs-statistics:
	cd notebooks;jupyter nbconvert --to notebook --execute zefys-statistics.ipynb;rm zefys-statistics.nbconvert.ipynb
%-command-doc:
	echo "## $*" >> $(CLI_DOC_FILE)
	echo \`\`\` >> $(CLI_DOC_FILE)
	echo `$* --help | base64 -w0` | base64 -d >> $(CLI_DOC_FILE)
	echo \`\`\` >> $(CLI_DOC_FILE)
CLI-MD-HEADER:
	rm $(CLI_DOC_FILE)
CLI-MD: CLI-MD-HEADER zefys-create-annoy-index-command-doc zefys-scanner-command-doc zefys-create-embeddings-command-doc zefys-join-ocr-databases-command-doc zefys-unpack-ocr-database-command-doc zefys-create-solr-index-command-doc zefys-ocr-database-command-doc zefys-downloader-command-doc zefys-ocr-filelist-command-doc compute-summaries-command-doc create-article-database-command-doc
