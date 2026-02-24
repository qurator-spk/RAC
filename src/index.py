import io

import click
import os

import ipdb
import numpy as np
import pandas as pd
from pyarrow import json_

from tqdm import tqdm

import sqlite3

from .parallel import run as prun

from annoy import AnnoyIndex

import json
import requests

from somajo import SoMaJo
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

import pysolr

class BuildIndexTask:
    ann_indices = None

    def __init__(self, n_trees, index_file):

        self.n_trees = n_trees
        self.index_file = index_file

    def __call__(self, *args, **kwargs):

        # noinspection PyBroadException
        try:
            (index, index_file) = self.ann_indices[self.index_file]

            index.build(self.n_trees)
            index.save(self.index_file)

        except Exception as e:
            print(e)

    @staticmethod
    def initialize(ann_indices):

        BuildIndexTask.ann_indices = ann_indices


@click.command()
@click.argument('emb-db-sqlite', type=click.Path(exists=True))
@click.option('--dist-measure', type=str, default='angular', help="Distance measure of the approximate nearest"
              " neighbour index. default: angular.")
@click.option('--n-trees', type=int, default=10, help="Number of search trees. Default 10.")
@click.option('--shard', type=str, multiple=True, default=None, help="")
@click.option('--embedding-dim', type=int, default=None, help="")
@click.option('--stop-at', type=int, default=None, help="")
def create_annoy_index(emb_db_sqlite, dist_measure, n_trees, shard, embedding_dim, stop_at):

    if shard is not None:
        shard = list(shard)

    index_dir = emb_db_sqlite.split('/')[-1]

    index_dir = index_dir.split('.')[-2] + ".ann"

    if not os.path.exists(index_dir):
        os.mkdir(index_dir)

    # noinspection PyShadowingNames
    def iterate_embeddings():
        with sqlite3.connect(emb_db_sqlite) as db:
            num_embeddings = db.execute("SELECT count(*) FROM embeddings").fetchone()[0]

            cur = db.cursor()
            cur.execute("SELECT article_id, embedding FROM embeddings")

            _cur_it = tqdm(cur, total=num_embeddings)

            for (aid, embedding) in _cur_it:

                buffer = io.BytesIO(embedding)

                buffer.seek(0)

                embedding = np.load(buffer)

                if embedding_dim is not None:
                    embedding = embedding[0:embedding_dim]

                yield aid, embedding

    with sqlite3.connect(emb_db_sqlite) as emb_db:
        article_db_file = emb_db.execute('SELECT value FROM meta_data WHERE key="article_db"').fetchone()[0]

    with sqlite3.connect(article_db_file) as art_db:

        articles = pd.read_sql('SELECT * FROM articles', con=art_db).\
            reset_index(drop=True).\
            set_index('article_id').\
            sort_index()

        index_info = list()
        ann_indices = dict()
        ann_counter = dict()

        ann_id_mapping = list()
        for num, (aid, embedding) in enumerate(iterate_embeddings()):

            if stop_at is not None and num >= stop_at:
                break

            ainfo = articles.loc[[aid]]

            index_file = index_dir + "/" + (ainfo[shard].astype(str).apply('-'.join, axis=1) + '.ann').iloc[0]

            # noinspection PyUnresolvedReferences
            (index, index_id) = ann_indices.get(index_file, (None, None))

            if index is None:
                index = AnnoyIndex(len(embedding), dist_measure)
                index.on_disk_build(index_file)

                ann_indices[index_file] = (index, len(index_info)+1)
                ann_counter[index_file] = 0

                index_id = len(index_info)+1
                index_info.append(ainfo[shard])

            index.add_item(ann_counter[index_file], embedding)
            ann_id_mapping.append((index_id, ann_counter[index_file], aid))
            ann_counter[index_file] += 1

        index_info = pd.concat(index_info).reset_index(drop=True)

        ann_id_mapping = pd.DataFrame(ann_id_mapping, columns=['index_id', 'ann_id', 'article_id'])

        with sqlite3.connect(emb_db_sqlite) as db:
            index_info.to_sql('ann_index', index=False, if_exists='replace', con=db)
            ann_id_mapping.to_sql('ann_id_mapping', index=False, if_exists='replace', con=db)

            db.execute('CREATE INDEX IF NOT EXISTS idx_ann_id_mapping ON ann_id_mapping(index_id, ann_id);')

        # noinspection PyShadowingNames
        def get_index_build_tasks():
            for index_file, index in ann_indices.items():
                yield BuildIndexTask(n_trees, index_file)

        for _ in tqdm(prun(get_index_build_tasks(), initializer=BuildIndexTask.initialize, initargs=(ann_indices,)),
                      total=len(ann_indices), desc="Building indices ..."):
            pass


@click.command()
@click.argument('art-db-sqlite', type=click.Path(exists=True))
@click.argument('solr-core-url', type=str)
@click.option('--model-dir', type=click.Path(exists=True), default="None")
@click.option('--query-text', type=str, default=None,
              help="Use first N dimensions of embeddings. Default 128.")
@click.option('--embedding-dim', type=click.Choice([128, 256, 512, 768]), default=128,
              help="Use first N dimensions of embeddings. Default 128.")
@click.option('--hnsw-beam-width', type=click.Choice([16,32,64]), default=16,
              help="")
@click.option('--hnsw-max-connections', type=click.Choice([100,200,400]), default=100,
              help="")
@click.option('--collation-mode', type=click.Choice(['raw', 'mean', 'max', 'min', 'absminmax']),
              default='mean',
              help="How to collate multiple embeddings of longer texts. Default: raw => do not collate at all.")
def query_solr_index(art_db_sqlite, solr_core_url, model_dir, query_text, embedding_dim,
                     hnsw_beam_width, hnsw_max_connections, collation_mode):

    k=10

    query = \
        {
            # "sort": "desc",
            "limit": k
        }

    embedding_field = \
        "embedding_{}_vec_{}_mc{}_bw{}".format(collation_mode, int(embedding_dim),
                                               int(hnsw_beam_width), int(hnsw_max_connections))

    print(embedding_field)

    if query_text is not None and model_dir is not None:

        model = SentenceTransformer(model_dir)

        #model_tokenizer = AutoTokenizer.from_pretrained(model_dir)
        #somajo_tokenizer = SoMaJo("de_CMC", split_camel_case=True, split_sentences=True)
        #
        #sentences_tokenized = somajo_tokenizer.tokenize_text([query_text])
        #sentences = [" ".join([t.text for t in sen]) for sen in sentences_tokenized]
        #inputs = model_tokenizer(sentences, padding=True, truncation=True)

        embeddings = model.encode([ "title: | text: {}".format(query_text)], batch_size=1)

        embeddings = [str(f) for f in  list(embeddings[0][0:embedding_dim])]

        knn_query = \
            {
                "knn":
                    {
                        "f": embedding_field,
                        "v": "[{}]".format(",".join(embeddings)),
                        "k": k
                    }
            }

        query["query"] = knn_query

        # import ipdb;ipdb.set_trace()

    # json_query = \
    #     {
    #         "query": {
    #             "knn": {
    #                 "field": "dense_vec",
    #                 "vector": embeddings,
    #                 "k": 10
    #             }
    #         },
    #
    #         # "filter": [
    #         #     {"term": {"category_id": 5}},  # exact match on category
    #         #     {"range": {"status": {"gte": 2, "lte": 4}}},  # status 2–4 inclusive
    #         #     {"range": {"created_at": {"gte": "2023-01-01T00:00:00Z",
    #         #                               "lte": "2023-12-31T23:59:59Z"}}}  # year‑wide
    #         # ],
    #
    #         "sort": [
    #             {"score": "desc"}  # best‑matches    first
    #         ],
    #
    #         "limit": 10  # keep the same k‑value as above
    #     }

    #query["sort"] = ["year desc"]

    # query["filter"] = ["year:1907"]

    # r = requests.post(solr_core_url + "/query?q=*:*&q.op=OR&indent=true&json={}".format(),
    #                   headers={"Content-Type": "application/json"},
    #                   json=json.dumps(query), timeout=None)

    solr = pysolr.Solr(solr_core_url, timeout=10)

    # r.raise_for_status()  # raises on 4xx/5xx
    # data = r.json()
    # result = data["response"]

    # import ipdb;ipdb.set_trace()

    response = solr.search(q='*:*', json=json.dumps(query), fl="*,score", sort="score desc")

    # import ipdb;ipdb.set_trace()

    with sqlite3.connect(art_db_sqlite) as art_db:
        for doc in response.docs:
            df_regions = pd.read_sql("SELECT type, text, article_pos FROM regions WHERE article_id=?", con=art_db,
                                     params=(doc["article_id"],))

            header = " ".join(df_regions.loc[df_regions.type == "header"]. \
                              sort_values(by="article_pos", ascending=True).text.tolist())

            text = " ".join(df_regions.loc[df_regions.type == "paragraph"]. \
                            sort_values(by="article_pos", ascending=True).text.tolist())

            print("\n{}\n============\n{}".format(header,text))

            # print(f"id={doc['id']}, score={doc['score']}")


class ArticleIndexTask:

    emb_db=None

    def __init__(self, article_id, embedding_dim, collation_mode):

        self._article_id = article_id
        self._embedding_dim = embedding_dim
        #self._mode = "mean"
        self._mode = collation_mode

    def __call__(self, *args, **kwargs):
        tmp = pd.read_sql("SELECT article_id, embedding FROM embeddings WHERE article_id=?",
                          params=(self._article_id,), con=ArticleIndexTask.emb_db)
        embeddings = []
        for _, (_, embedding) in tmp.iterrows():
            buffer = io.BytesIO(embedding)
            buffer.seek(0)
            embedding = np.load(buffer)
            embeddings.append(embedding)

        embeddings = pd.DataFrame(embeddings)

        # import ipdb;ipdb.set_trace()

        if len(embeddings) < 1:
            return self._article_id, None

        result = {}

        for mode in self._mode:

            if mode == "mean":
                vec = embeddings.mean() #.iloc[0:self._embedding_dim]

                vec = pd.DataFrame(vec).T

            elif mode == "max":
                vec = embeddings.max() #.iloc[0:self._embedding_dim]

                vec = pd.DataFrame(vec).T

            elif mode == "min":
                vec = embeddings.min() #.iloc[0:self._embedding_dim]

                vec = pd.DataFrame(vec).T

            elif mode == "absminmax":
                if len(embeddings) > 1:
                    #embeddings = embeddings.iloc[:, 0:self._embedding_dim]

                    emb_abs = embeddings.abs()

                    sgn = np.sign(embeddings)

                    abs_idx = emb_abs.idxmax()

                    sgn = pd.DataFrame([sgn.iloc[r, c] for c, r in enumerate(abs_idx.tolist())])

                    vec  = pd.DataFrame(emb_abs.max() * sgn.T)
                    #import ipdb;ipdb.set_trace()
                else:
                    vec = pd.DataFrame(embeddings.max()).T  #.iloc[0:self._embedding_dim]).T
                    #import ipdb;ipdb.set_trace()

            elif mode == "raw":
                vec = embeddings # .iloc[:, 0:self._embedding_dim]
            else:
                raise RuntimeError("Unknown collation-mode: {}".format(self._mode))

            result[mode] = vec

        return self._article_id, result

    @staticmethod
    def initialize(emb_db_sqlite):
        ArticleIndexTask.emb_db = sqlite3.connect(emb_db_sqlite)

@click.command()
@click.argument('emb-db-sqlite', type=click.Path(exists=True))
@click.argument('solr-core-url', type=str)
@click.option('--embedding-dim', type=click.Choice([128, 256, 512, 768]), default=128,
              help="Use first N dimensions of embeddings. Default 128.", multiple=True)
@click.option('--hnsw-beam-width', type=click.Choice([16,32,64]), default=16,
              help="", multiple=True)
@click.option('--hnsw-max-connections', type=click.Choice([100,200,400]), default=100,
              help="", multiple=True)
@click.option('--collation-mode', type=click.Choice(['raw', 'mean', 'max', 'min', 'absminmax']), default='raw',
              help="How to collate multiple embeddings of longer texts. Default: raw => do not collate at all.", multiple=True)
@click.option('--stop-at', type=int, default=None,
              help="Process only the first N embeddings. Default: Process all.")
@click.option('--skip-first', type=int, default=None,
              help="Skip the first N embeddings. Default: skip nothing.")
@click.option('--chunk-size', type=int, default=10000,
              help="Commit in chunks of size N to solr. Default 100000.")
@click.option('--processes', type=int, default=10,
              help="Number of concurrent data feeder processes. Default 10.")
def create_solr_index(emb_db_sqlite, solr_core_url, embedding_dim, hnsw_beam_width, hnsw_max_connections,
                      collation_mode, stop_at, skip_first, chunk_size, processes):
    """
    EMB_DB_SQLITE: sqlite database that holds the embeddings to be imported.
    SOLR_CORE_URL: Example: http://localhost:8983/solr/test .
    """

    with sqlite3.connect(emb_db_sqlite) as emb_db:
        article_db_file = emb_db.execute('SELECT value FROM meta_data WHERE key="article_db"').fetchone()[0]

    with sqlite3.connect(article_db_file) as art_db:
        articles = pd.read_sql('SELECT * FROM articles', con=art_db). \
            reset_index(drop=True). \
            set_index('article_id'). \
            sort_index()

    # noinspection PyShadowingNames
    def get_article_tasks():
        for aid, _ in tqdm(articles.iterrows(), total=len(articles), desc="data loading", leave=False):
            yield ArticleIndexTask(aid, embedding_dim, collation_mode)

    update_url = "{}/update?commit=true".format(solr_core_url)

    num_chunk = 0
    num_vec = 0

    seq = tqdm(enumerate(prun(get_article_tasks(), initializer=ArticleIndexTask.initialize,
                              initargs=(emb_db_sqlite,), processes=processes)), total=len(articles),
               leave=False, desc="Commit to solr")

    def commit_chunk(_json_data):
        nonlocal num_chunk
        nonlocal seq
        nonlocal update_url

        try:
            seq.set_description("Commiting chunk #{} of size {} to solr ....".format(num_chunk, chunk_size))

            r = requests.post(update_url,
                              headers={"Content-Type": "application/json"},
                              json=_json_data, timeout=None)
            r.raise_for_status()

            num_chunk += 1

            seq.set_description("Commit to solr")

        except Exception as _e:
            print(_e)
            raise _e

    # noinspection PyShadowingNames
    def iterate_knn_params():
        for mode in collation_mode:
            for emb_dim in embedding_dim:
                for beam_width in hnsw_beam_width:
                    for max_connections in hnsw_max_connections:
                        yield mode, emb_dim, beam_width, max_connections

    json_data = []

    chunk_size = stop_at if stop_at is not None and chunk_size > stop_at else chunk_size

    for num, (aid, result) in seq:

        if result is None: # There are some articles that do not have text (only header) vice versa.
            continue            # Submitting them would cause a solr exception since the embeddings field is required.

        if stop_at is not None and num_vec >= stop_at:
            break

        ainfo = articles.loc[aid]

        #Example: 1995-12-31T23:59:59
        publishing_date = "{}-{}-{}T01:01:01".format(ainfo.year, ainfo.month, ainfo.day)

        new_json_items = {}

        for mode, emb_dim, beam_width, max_connections in iterate_knn_params():
            vec = result[mode]

            embedding_field = \
                "embedding_{}_vec_{}_mc{}_bw{}".format(mode, int(emb_dim),
                                                       int(beam_width), int(max_connections))
            for row_id, row in vec.iterrows():
                # import ipdb;ipdb.set_trace()

                the_id = str(aid)+"-"+str(row_id)

                if the_id in new_json_items:
                    new_json_items[the_id][embedding_field] = row.tolist()[0:emb_dim]
                else:
                    new_json_items[the_id] =\
                        {
                            "id": the_id,
                            "article_id" : int(aid),
                            "article_db" : article_db_file,
                            "zdbid" : ainfo.zdb_id,
                            "year": int(ainfo.year),
                            "month": int(ainfo.month),
                            "day": int(ainfo.day),
                            "issue": int(ainfo.issue),
                            embedding_field: row.tolist()[0:emb_dim],
                            "publishing_date": publishing_date
                        }

            #import ipdb;
            #ipdb.set_trace()
        for _,json_item in new_json_items.items():
            json_data.append(json_item)

        seq.set_description("Chunk #{}: {}".format(num_chunk, len(json_data)))

        if len(json_data) < chunk_size:
            continue

        try:
            if skip_first is not None and num_vec + len(json_data) < skip_first:
                num_vec += len(json_data)
                json_data = []
                continue

            commit_chunk(json_data)
            num_vec += len(json_data)
            json_data = []

        except Exception as e:
            break

    if len(json_data) > 0:
        commit_chunk(json_data)

def create_new_core(core_name):

    # Establish a connection to Solr
    solr = pysolr.Solr('http://localhost:8983/solr', always_commit=True)
    # Create a new Solr core
    solr.create_core('mycore')
    # Define the schema for the core
    schema = [
        {
            "name": "id",
            "type": "string",
            "indexed": True,
            "stored": True,
            "required": True,
            "uniqueKey": True
        },
        {
            "name": "title",
            "type": "text_general",
            "indexed": True,
            "stored": True
        },
        {
            "name": "content",
            "type": "text_general",
            "indexed": True,
            "stored": True
        }
    ]
    # Configure the schema for the core
    solr.schema.create(core_name, schema)