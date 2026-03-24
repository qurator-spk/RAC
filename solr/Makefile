EMBEDDING_DB=SP-1907-1931-EMB.sqlite
SOLR_URL=http://localhost:8983/solr/test3
CHUNK_SIZE=10000
# STOP_PARAMS=--stop-at=100
STOP_PARAMS=
PROCESSES=10

all:
	zefys-create-solr-index --hnsw-beam-width=16 --hnsw-beam-width=32 --hnsw-beam-width=64 \
		--hnsw-max-connections=100  --hnsw-max-connections=200 --hnsw-max-connections=400 \
		--embedding-dim=128 --embedding-dim=256 --embedding-dim=512 --embedding-dim=768 \
		--collation-mode="mean" --collation-mode="absminmax" --collation-mode="min" --collation-mode="max" \
		--processes=$(PROCESSES) --chunk-size=$(CHUNK_SIZE) $(STOP_PARAMS) $(EMBEDDING_DB) $(SOLR_URL)


exp1:
	query-solr-index --summaries-db=./SP-1907-1931-ART.sqlite --query-result-db=./EXP1.sqlite \
	       	--model-dir ./embeddinggemma-300m \
	       	--hnsw-beam-width=16 --hnsw-beam-width=32 --hnsw-beam-width=64 \
                --hnsw-max-connections=100  --hnsw-max-connections=200 --hnsw-max-connections=400 \
                --embedding-dim=128 --embedding-dim=256 --embedding-dim=512 --embedding-dim=768 \
                --collation-mode="mean" --collation-mode="absminmax" --collation-mode="min" \
		--collation-mode="max" \
                --processes=$(PROCESSES) --solr-core-url $(SOLR_URL) --k=512 --chunk-size=2000 
