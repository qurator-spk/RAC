nfs-scan:
	cd /zefys/archive
	find ./ -wholename "*/presentation/*.jpg" -o -wholename "*/presentation/*.jpeg" -o -wholename "*/presentation/*.png" > ~/SPUNK/workbench/zefys_image_files.txt
run-zefys-statistics:
	cd notebooks;jupyter nbconvert --to notebook --execute zefys-statistics.ipynb;rm zefys-statistics.nbconvert.ipynb
