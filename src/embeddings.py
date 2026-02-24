import io

import click
import os

# import ipdb
import numpy as np
import pandas as pd
# from fontTools.ttLib.tables.S_V_G_ import doc_index_entry_format_0Size
from tqdm import tqdm
import re
import json
from fnmatch import fnmatch
import sqlite3
import zipfile

from parallel import run as prun

from pathlib import Path

from somajo import SoMaJo, Tokenizer, SentenceSplitter

from sentence_transformers import SentenceTransformer

from transformers import AutoTokenizer

from multiprocessing import Semaphore

tokenization_semaphore = Semaphore(1000)


class ModelTokenizeTask:
    model_tokenizer = None
    somajo_tokenizer = None

    def __init__(self, article_id, title, text, max_token_length):

        self.title = title
        self.article_id = article_id
        self.max_token_length = max_token_length
        self.text = text

    def __call__(self, *args, **kwargs):

        # noinspection PyBroadException
        try:
            tokenization_semaphore.acquire()

            sentences_tokenized = self.somajo_tokenizer.tokenize_text([self.text])

            sentences = [" ".join([t.text for t in sen]) for sen in sentences_tokenized]

            inputs = self.model_tokenizer(sentences, padding=True, truncation=True)

            df_buckets = pd.DataFrame({'num_tokens': [len(inp) for inp in inputs['input_ids']]})

            df_buckets['bucket'] = (df_buckets.num_tokens.cumsum() / self.max_token_length).astype(int)

            return self.article_id, self.title, sentences, df_buckets, inputs

        except Exception as e:
            print(e)
            return None, None, None, None, None

    @staticmethod
    def initialize(model_dir):

        ModelTokenizeTask.model_tokenizer = AutoTokenizer.from_pretrained(model_dir)

        ModelTokenizeTask.somajo_tokenizer = SoMaJo("de_CMC", split_camel_case=True, split_sentences=True)


@click.command()
@click.argument('art-db-sqlite', type=click.Path(exists=True))
@click.argument('emb-db-sqlite', type=click.Path())
@click.argument('model_dir', type=click.Path(exists=True))
@click.option('--processes', type=int, default=0, help="")
@click.option('--max-token-length', type=int, default=200, help="")
@click.option('--batch-size', type=int, default=64, help="")
def create_embeddings(art_db_sqlite, emb_db_sqlite, model_dir, processes, max_token_length, batch_size):

    def setup_emb_db(model):
        if os.path.exists(emb_db_sqlite):
            with (sqlite3.connect(emb_db_sqlite) as con):
                meta_model = con.execute('SELECT value FROM meta_data WHERE key="model"').fetchone()[0]

                if meta_model != str(model):
                    raise RuntimeError("Model mismatch!!")

                meta_max_token_len =\
                    con.execute('SELECT value FROM meta_data WHERE key="max_token_length"').fetchone()[0]

                if int(meta_max_token_len) != max_token_length:
                    raise RuntimeError("max_token_length mismatch!!")

        else:
            with sqlite3.connect(emb_db_sqlite) as con:
                con.execute('BEGIN EXCLUSIVE TRANSACTION')

                con.execute('CREATE TABLE IF NOT EXISTS "meta_data" '
                            '("key" TEXT PRIMARY_KEY,  "value" TEXT);')

                con.execute('CREATE TABLE IF NOT EXISTS "embeddings" '
                            '("article_id" INTEGER, "embedding" BLOB);')

                con.execute('CREATE INDEX IF NOT EXISTS idx_article_id ON embeddings(article_id);')

                con.execute('INSERT INTO meta_data(key, value) VALUES(?,?)', ("model", str(model)))
                con.execute('INSERT INTO meta_data(key, value) VALUES(?,?)', ("max_token_length",
                                                                              str(max_token_length)))
                con.execute('INSERT INTO meta_data(key, value) VALUES(?,?)', ("article_db",
                                                                              art_db_sqlite))

                con.execute('COMMIT TRANSACTION')

    def iterate_articles():

        with sqlite3.connect(art_db_sqlite) as art_db:
            num_articles = art_db.execute("SELECT count(*) FROM articles").fetchone()[0]

            cur = art_db.cursor()
            cur.execute("SELECT article_id, zdb_id, year, month, day, issue, start_page, num_pages FROM articles")

            _cur_it = tqdm(cur, total=num_articles)

            for (aid, zdb_id, year, month, day, issue, start_page, num_page) in _cur_it:

                df_regions = pd.read_sql("SELECT type, text, article_pos FROM regions WHERE article_id=?", con=art_db,
                                         params=(aid,))

                header = " ".join(df_regions.loc[df_regions.type == "header"].
                                  sort_values(by="article_pos", ascending=True).text.tolist())

                text = " ".join(df_regions.loc[df_regions.type == "paragraph"].
                                sort_values(by="article_pos", ascending=True).text.tolist())

                yield aid, header, text

    def iterate_article_buckets():

        # noinspection PyShadowingNames
        def get_tokenize_tasks():
            for article_id, title, text in iterate_articles():
                yield ModelTokenizeTask(article_id, title, text, max_token_length)

        for article_id, title, sentences, df_buckets, inputs in prun(get_tokenize_tasks(),
                                                                     initializer=ModelTokenizeTask.initialize,
                                                                     initargs=(model_dir,),
                                                                     processes=processes):
            for bucket_num, bucket in df_buckets.groupby("bucket"):

                bucket_text = "".join([sentences[i] for i in bucket.index])
                bucket_inputs = np.array([inputs['input_ids'][i] for i in bucket.index])

                if bucket_num == 0:
                    yield article_id, title, bucket_text, bucket_inputs
                else:
                    yield article_id, "none", bucket_text, bucket_inputs

            tokenization_semaphore.release()

    # noinspection PyShadowingNames
    def iterate_batches():
        batch_text = []
        # batch_inputs = []
        batch_article_ids = []
        for article_id, title, bucket_text, bucket_inputs in iterate_article_buckets():
            if len(batch_text) < batch_size:
                batch_text.append("title: " + title + " | text: " + bucket_text)
                # batch_inputs += bucket_inputs
                batch_article_ids.append(article_id)
            else:
                yield batch_article_ids, batch_text
                batch_text = []
                # batch_inputs = []
                batch_article_ids = []

    model = SentenceTransformer(model_dir)

    setup_emb_db(model)

    with sqlite3.connect(emb_db_sqlite) as con:

        con.execute('pragma journal_mode=wal')

        num_emb = 0
        for batch_aids, batch in iterate_batches():

            batch_embeddings = model.encode(batch, batch_size=batch_size)

            con.execute('BEGIN EXCLUSIVE TRANSACTION')

            for i in range(0, len(batch_embeddings)):
                tmp = io.BytesIO()
                np.save(tmp, batch_embeddings[i])
                tmp.seek(0)

                con.execute('INSERT INTO embeddings(article_id, embedding) VALUES(?,?)',
                            (batch_aids[i], sqlite3.Binary(tmp.read())))
            con.execute('COMMIT TRANSACTION')

            num_emb += 1

    print("Number of embeddings computed: {}".format(num_emb))


@click.command()
@click.argument('model_dir', type=click.Path(exists=True))
def emb_test(model_dir):
    # pool = model.start_multi_process_pool()

    model = SentenceTransformer(model_dir)

    # model.stop_multi_process_pool(pool)

    query = "Er ist ein glücklicher Mann."
    documents = [
        "It is a happy dog.",
        "It is a happy cat.",
        "Es ist ein glücklicher Hund.",
        "Es ist eine glückliche Katze",
        "He is a happy dog.",
        "He is a happy cat.",
        "It is a happy man.",
        "He is a happy man.",
        "Er ist ein glücklicher Mann.",
        "Er ist ein unglücklicher Mann.",
        "Manchmal ist er ein glücklicher Mann.",
        "Er ist ein sehr glücklicher Mann.",
        "Er ist ein bischen ein glücklicher Mann.",
        "เขาเป็นผู้ชายที่มีความสุข",
        "彼は幸せな男だ",
        "他是個快樂的人。",
        "他是个快乐的人。"
    ]

    # query_embeddings = model.encode_query(query)
    # document_embeddings = model.encode_document(documents)

    query_embeddings = model.encode("title: none | text: " + query)
    document_embeddings = model.encode(["title: none | text: " + d for d in documents])

    query_embeddings = query_embeddings[0:128]
    document_embeddings = document_embeddings[:, 0:128]

    # print(query_embeddings.shape, document_embeddings.shape)

    # Compute similarities to determine a ranking
    similarities = model.similarity(query_embeddings, document_embeddings).detach().numpy()

    for i, s in enumerate(similarities[0]):
        print(s, "\t:\t", documents[i], "\t<=>\t", query)


