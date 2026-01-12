import io

import click
import os

import numpy as np
import pandas as pd

from tqdm import tqdm

import sqlite3

from parallel import run as prun

from annoy import AnnoyIndex


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
def create_index(emb_db_sqlite, dist_measure, n_trees, shard, embedding_dim, stop_at):

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

