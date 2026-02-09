import io

import click
import os

import ipdb
import numpy as np
import pandas as pd

from tqdm import tqdm

import sqlite3

from parallel import run as prun

from annoy import AnnoyIndex

import json
import requests

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
@click.argument('emb-db-sqlite', type=click.Path(exists=True))
def query_index(emb_db_sqlite):
    pass


class ArticleIndexTask:

    emb_db=None

    def __init__(self, article_id):

        self._article_id = article_id

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

        vec = embeddings.mean().iloc[0:128]

        return self._article_id, vec

    @staticmethod
    def initialize(emb_db_sqlite):
        ArticleIndexTask.emb_db = sqlite3.connect(emb_db_sqlite)

@click.command()
@click.argument('emb-db-sqlite', type=click.Path(exists=True))
@click.argument('solr-core-url', type=str)
@click.option('--embedding-dim', type=int, default=128,
              help="Use first N dimensions of embeddings. Default 128.")
@click.option('--stop-at', type=int, default=None, help="")
def create_solr_index(emb_db_sqlite, solr_core_url, embedding_dim, stop_at):
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

    seq = tqdm(articles.iterrows(), total=len(articles))

    # noinspection PyShadowingNames
    def get_article_tasks():
        for aid, _ in seq:
            yield ArticleIndexTask(aid)

    json_data = []
    chunk_size = 1000
    processes = 10
    update_url = "{}/update?commit=true".format(solr_core_url)

    num_chunk = 0
    for num, (aid, vec) in enumerate(prun(get_article_tasks(), initializer=ArticleIndexTask.initialize,
                         initargs=(emb_db_sqlite,), processes=processes)):

        if stop_at is not None and num >= stop_at:
            break

        ainfo = articles.loc[aid]

        if len(vec) < 1: # There are some articles that do not have text (only header) vice versa.
            continue            # Submitting them would cause a solr exception since the embeddings field is required.

        #Example: 1995-12-31T23:59:59
        publishing_date = "{}-{}-{}T01:01:01".format(ainfo.year, ainfo.month, ainfo.day)

        json_item = \
            {
                "id": str(aid),
                "article_id" : int(aid),
                "article_db" : article_db_file,
                "zdbid" : ainfo.zdb_id,
                "year": int(ainfo.year),
                "month": int(ainfo.month),
                "day": int(ainfo.day),
                "issue": int(ainfo.issue),
                "embedding": vec.tolist(),
                "publishing_date": publishing_date
            }
        json_data.append(json_item)

        seq.set_description("Chunk #{}: {}".format(num_chunk, len(json_data)))

        if len(json_data) < chunk_size:
            continue

        try:
            seq.set_description("Commiting chunk #{} of size {} to solr ....".format(num_chunk, chunk_size))

            r = requests.post(update_url,
                              headers={"Content-Type": "application/json"},
                              json=json_data, timeout=None)
            r.raise_for_status()
            json_data = []
            num_chunk += 1

            seq.set_description("Success.")

        except Exception as e:
            print(e)
            with open('embeddings.json', 'w', encoding='utf-8') as f:
               json.dump(json_data, f, indent=2)
            break


