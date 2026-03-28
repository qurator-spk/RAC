import io

import click
import os

import ipdb
import numpy as np
import pandas as pd
from openpyxl.styles.builtins import total
# from pyarrow import json_

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
@click.option('--shard', type=str, multiple=True, default=[], help="")
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

class QueryIndexTask:
    solr_core_url=None
    solr = None

    def __init__(self, query, query_param=None):
        self._query = query
        self._query_param = query_param

    def __call__(self, *args, **kwargs):
        response = None

        # import ipdb;ipdb.set_trace()

        if QueryIndexTask.solr is not None:
            try:
                response = QueryIndexTask.solr.search(q='*:*', json=json.dumps(self._query), fl="*,score", sort="score desc")
            except pysolr.SolrError:
                pass

        return self._query, response, self._query_param

    @staticmethod
    def initialize(solr_core_url):

        if solr_core_url is None:
            return

        QueryIndexTask.solr_core_url = solr_core_url
        QueryIndexTask.solr = pysolr.Solr(solr_core_url, timeout=120)


@click.command()
@click.option('--solr-core-url', type=str, default=None)
@click.option('--model-dir', type=click.Path(exists=True), default="None")
@click.option('--query-text', type=str, default=None, help="")
@click.option('--k', type=int, default=10, help="k. Default 10.")
@click.option('--limit-factor', type=int, default=1, help="Limit. Default 10.")
@click.option('--embedding-dim', type=click.Choice([128, 256, 512, 768]), default=[128], multiple=True,
              help="Use first N dimensions of embeddings. Default 128.")
@click.option('--hnsw-beam-width', type=click.Choice([16,32,64]), default=[16], multiple=True,
              help="")
@click.option('--hnsw-max-connections', type=click.Choice([100,200,400]), default=[100], multiple=True,
              help="")
@click.option('--collation-mode', type=click.Choice(['raw', 'mean', 'max', 'min', 'absminmax']),
              multiple=True, default=['mean'], help="How to collate multiple embeddings of longer texts. Default: mean.")
@click.option('--art-db-sqlite', type=click.Path(exists=True), default=None, help="")
@click.option('--summaries-db', type=click.Path(), default=None, help="")
@click.option('--query-result-db', type=click.Path(), default=None, help="")
@click.option('--write-query-json', type=click.Path(), default=None, help="")
@click.option('--stop-at', type=int, default=None, help="")
@click.option('--processes', type=int, default=0, help="")
@click.option('--chunk-size', type=int, default=1000, help="")
def query_solr_index(solr_core_url, model_dir, query_text, k, limit_factor, embedding_dim,
                     hnsw_beam_width, hnsw_max_connections, collation_mode, art_db_sqlite,
                     summaries_db, query_result_db, write_query_json, stop_at,processes, chunk_size):

    model=None
    if model_dir is not None:
        model = SentenceTransformer(model_dir)

    query_params = \
        [("embedding_{}_vec_{}_mc{}_bw{}".format(cm, int(ed), int(hbw), int(hmc)),
         cm, int(ed), int(hbw), int(hmc), k, limit_factor)
         for cm in collation_mode for ed in embedding_dim for hbw in hnsw_beam_width
         for hmc in hnsw_max_connections]

    def make_query(embeddings, _k, _limit_factor, _embedding_field, _embedding_dim):

        embeddings = [str(f) for f in  list(embeddings[0][0:_embedding_dim])]

        knn_query = \
             {
                 "knn": {
                     "f": _embedding_field,
                     "v": "[{}]".format(",".join(embeddings)),
                     "topK": int(_limit_factor*k)
                 }
             }

        query = \
            {
                "limit": _k,
                "query": knn_query
            }

        return query

    def get_queries():
        if query_text is not None:

            embeddings = model.encode(["title: | text: {}".format(query_text)], batch_size=1)

            for query_param  in tqdm(query_params):
                embedding_field, cm, ed, hbw, hmc, k, limit_factor = query_param

                yield QueryIndexTask(make_query(embeddings, k, limit_factor, embedding_field, ed), query_param)

        elif summaries_db is not None:

            with sqlite3.connect(summaries_db) as sdb:

                df_queries = pd.read_sql("SELECT article_id, prompt, model, max_tokens, temperature, "
                                         "summary FROM summaries", con=sdb)

            df_queries = df_queries.iloc[np.random.permutation(len(df_queries))].reset_index(drop=True)

            def get_query_chunks():

                n=0
                chunk=[]
                for _, (article_id, prompt, model_name, max_tokens, temperature, summary) in \
                        tqdm(df_queries.iterrows(), total=len(df_queries), leave=False, desc="queries"):

                    if stop_at is not None and n >= stop_at:
                        if len(chunk) > 0:
                            yield chunk
                            chunk=[]
                        break

                    chunk.append(
                        ((article_id, prompt, model_name, max_tokens, temperature, summary),
                         model.encode(["title: | text: {}".format(summary)], batch_size=1)))

                    n += 1

                    if len(chunk) >= chunk_size:
                        yield chunk
                        chunk=[]

                if len(chunk) > 0:
                    yield chunk

            for chunk in get_query_chunks():

                for query_param in tqdm(query_params, leave=False, desc="query_params"):
                    for (article_id, prompt, model_name, max_tokens, temperature, summary), embeddings in \
                            tqdm(chunk, leave=False, desc="chunk"):

                        embedding_field, cm, ed, hbw, hmc, k, limit_factor = query_param

                        full_query_param = query_param + (article_id, prompt, model_name, max_tokens, temperature)

                        yield QueryIndexTask(make_query(embeddings, k, limit_factor, embedding_field, ed),
                                             full_query_param)


    def print_result_articles(response):
        with sqlite3.connect(art_db_sqlite) as art_db:
            for doc in response.docs:
                df_regions = pd.read_sql("SELECT type, text, article_pos FROM regions WHERE article_id=?", con=art_db,
                                         params=(doc["article_id"],))

                header = " ".join(df_regions.loc[df_regions.type == "header"]. \
                                  sort_values(by="article_pos", ascending=True).text.tolist())

                text = " ".join(df_regions.loc[df_regions.type == "paragraph"]. \
                                sort_values(by="article_pos", ascending=True).text.tolist())

                print("\n\n==============\nTitel: {}\nDatum: {}\nZDB-ID: {}\nText:\n{}".format(header,
                                                                                               doc["publishing_date"],
                                                                                               doc["zdbid"], text.strip()))

    def setup_query_result_db(query_result_db):

        with sqlite3.connect(query_result_db) as qrdb:

            qrdb.execute('BEGIN EXCLUSIVE TRANSACTION')

            qrdb.execute('CREATE TABLE IF NOT EXISTS "results" '
                         '( "k" INTEGER, "limit_factor" INTEGER, '
                         '"article_id" INTEGER, "prompt" TEXT, "model" TEXT, "max_tokens" INTEGER, "temperature" REAL, '
                         ' "collation_mode" TEXT, "embedding_dim" INTEGER, "hnsw_beam_width" INTEGER,'
                         ' "hnsw_max_connections" INTEGER, "article_ids" TEXT, "scores" TEXT);')

            qrdb.execute('CREATE INDEX IF NOT EXISTS idx_results ON results(k, limit_factor, article_id, prompt, model, '
                         'max_tokens, temperature, collation_mode, embedding_dim, hnsw_beam_width, hnsw_max_connections);')

            qrdb.execute('COMMIT TRANSACTION')

    if query_result_db is not None:
        setup_query_result_db(query_result_db)

    queries = list()
    for query, response, query_param in \
            prun(get_queries(), initializer=QueryIndexTask.initialize, initargs=(solr_core_url,), processes=processes):

        if art_db_sqlite is not None:
            print_result_articles(response)

        elif query_result_db is not None:

            if response is None:
                continue

            # import ipdb;ipdb.set_trace()

            embedding_field, cm, ed, hbw, hmc, k, limit_factor, article_id, prompt, model_name, max_tokens, temperature =\
                query_param

            article_ids = ",".join([str(doc["article_id"]) for doc in response.docs])

            scores = ",".join([str(doc["score"]) for doc in response.docs])

            #import ipdb;ipdb.set_trace()

            with sqlite3.connect(query_result_db) as qrdb:

                qrdb.execute('BEGIN EXCLUSIVE TRANSACTION')

                qrdb.execute(
                    'INSERT INTO results(k, limit_factor, article_id, prompt, model, max_tokens, '
                    'temperature, collation_mode, embedding_dim, hnsw_beam_width, hnsw_max_connections, '
                    'article_ids, scores )'
                    ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (k, limit_factor, article_id, prompt, model_name, max_tokens, temperature, cm,
                     ed, hbw, hmc, article_ids, scores))

                qrdb.execute('COMMIT TRANSACTION')
        elif write_query_json is not None:

            #import ipdb;ipdb.set_trace()

            embedding_field, cm, ed, hbw, hmc, k, limit_factor, article_id, prompt, model_name, max_tokens, temperature = \
                query_param

            item = {
                "query" : query,
                "query_params": {
                    "embedding_field": embedding_field,
                    "collation_mode": cm,
                    "embedding_dim": ed,
                    "hnsw_beam_width": hbw,
                    "hnsw_max_connections": hmc,
                    "k": k,
                    "limit_factor": limit_factor,
                    "article_id": article_id,
                    "prompt": prompt,
                    "model": model_name,
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
            }

            queries.append(item)

    if write_query_json is not None:
        with open(write_query_json, "w", encoding="utf-8") as a_file:
            # noinspection PyTypeChecker
            json.dump(queries, a_file, ensure_ascii=False, indent=3)


class ArticleIndexTask:

    emb_db=None

    def __init__(self, article_id, embedding_dim, collation_mode):

        self._article_id = article_id
        self._embedding_dim = embedding_dim
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

        if len(embeddings) < 1:
            return self._article_id, None

        result = {}

        for mode in self._mode:

            if mode == "mean":
                vec = embeddings.mean()

                vec = pd.DataFrame(vec).T

            elif mode == "max":
                vec = embeddings.max()

                vec = pd.DataFrame(vec).T

            elif mode == "min":
                vec = embeddings.min()

                vec = pd.DataFrame(vec).T

            elif mode == "absminmax":
                if len(embeddings) > 1:

                    emb_abs = embeddings.abs()

                    sgn = np.sign(embeddings)

                    abs_idx = emb_abs.idxmax()

                    sgn = pd.DataFrame([sgn.iloc[r, c] for c, r in enumerate(abs_idx.tolist())])

                    vec  = pd.DataFrame(emb_abs.max() * sgn.T)
                else:
                    vec = pd.DataFrame(embeddings.max()).T

            elif mode == "raw":
                vec = embeddings
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
@click.option('--embedding-dim', type=click.Choice([128, 256, 512, 768]), default=[128],
              help="Use first N dimensions of embeddings. Default 128.", multiple=True)
@click.option('--hnsw-beam-width', type=click.Choice([16,32,64]), default=[16],
              help="", multiple=True)
@click.option('--hnsw-max-connections', type=click.Choice([100,200,400]), default=[100],
              help="", multiple=True)
@click.option('--collation-mode', type=click.Choice(['raw', 'mean', 'max', 'min', 'absminmax']), default=['raw'],
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
            seq.set_description("Commiting chunk #{} of size {} to SOLR ....".format(num_chunk, chunk_size))

            r = requests.post(update_url,
                              headers={"Content-Type": "application/json"},
                              json=_json_data, timeout=None)
            r.raise_for_status()

            num_chunk += 1

            seq.set_description("Commit to SOLR")

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
