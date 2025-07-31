nfs-scan:
	cd /nfs/zefys
	find ./ -wholename "*/presentation/*.jpg" -o -wholename "*/presentation/*.jpeg" -o -wholename "*/presentation/*.png" > ~/SPUNK/workbench/zefys_image_files.txt
