import os
# import signal
import flask
# from PIL.Image import Image
from spunk.zdb import get_zdb_meta_data
from werkzeug.exceptions import *
import io
import logging
# import cv2

from flask import send_from_directory, redirect, jsonify, request, send_file  # , flash
import sqlite3
import pandas as pd
# import threading
# import torch
import json
import base64
import numpy as np

# noinspection PyUnresolvedReferences
# from annoy import AnnoyIndex

import requests

from somajo import SoMaJo
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

import pysolr


from flask_cachecontrol import (cache_for)

import re

app = flask.Flask(__name__)

try:
    config_file = 'config/config.json' if not os.environ.get('CONFIG') else os.environ.get('CONFIG')

    print(config_file)

    app.config.from_file(os.path.join(os.getcwd(), config_file), load=json.load)

except FileNotFoundError as e:
    import pathlib

    print(e)
    print("Current path: {}".format(pathlib.Path(os.getcwd())))

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

htpasswd = None
if len(app.config['PASSWD_FILE']) > 0 and os.path.exists(os.path.join(os.getcwd(), app.config['PASSWD_FILE'])):
    app.config['FLASK_HTPASSWD_PATH'] = os.path.join(os.getcwd(), app.config['PASSWD_FILE'])
    app.config['FLASK_AUTH_REALM'] = app.config['AUTH_REALM']

    from .no_auth import AuthReloader

    htpasswd = AuthReloader(app, app.config['PASSWD_FILE'])
else:
    print("AUTHENTICATION DISABLED!!!")
    from .no_auth import NoAuth

    htpasswd = NoAuth()

    print("DONE.")

# -----------------------

embedding_models = dict()

def get_embedding_model(model):

    if model in embedding_models:
        return embedding_models[model]

    embedding_models[model] = SentenceTransformer(model)

    return embedding_models[model]

# -----------------------

zdb_info = dict()

def get_publication_name(zdb_id, articles):

    if articles in zdb_info:
        return zdb_info[articles].loc[zdb_id].title

    articles_conf = app.config["ARTICLES"][articles]

    art_db_sqlite = articles_conf["DB_FILE"]

    with sqlite3.connect(art_db_sqlite) as art_db:
        df = pd.read_sql('SELECT DISTINCT zdb_id FROM articles', con=art_db)

    zdb_info[articles] = get_zdb_meta_data(df)

    return zdb_info[articles].loc[zdb_id].title


# -----------------------


@app.route('/query/<articles>', methods=['POST'])
@htpasswd.required
@cache_for(minutes=10)
def get_query(user, articles, k=100):

    articles_conf = app.config["ARTICLES"][articles]

    art_db_sqlite = articles_conf["DB_FILE"]
    solr_core_url  = articles_conf["SOLR_ENDPOINT"]

    query_text = request.json['query_text']

    hnsw_beam_width = 64
    hnsw_max_connections = 400
    embedding_dim = 768
    collation_mode = "mean"

    k=200

    query = \
        {
            "limit": 2*k
        }

    embedding_field = \
        "embedding_{}_vec_{}_mc{}_bw{}".format(collation_mode, int(embedding_dim),
                                               int(hnsw_beam_width), int(hnsw_max_connections))

    model = get_embedding_model(articles_conf["EMBEDDING_MODEL"])

    embeddings = model.encode(["title: | text: {}".format(query_text)], batch_size=1)

    embeddings = [str(f) for f in list(embeddings[0][0:embedding_dim])]

    knn_query = \
        {
            "knn":
                {
                    "f": embedding_field,
                    "v": "[{}]".format(",".join(embeddings)),
                    "topK": 2*k
                }
        }

    query["query"] = knn_query

    solr = pysolr.Solr(solr_core_url, timeout=10)

    response = solr.search(q='*:*', json=json.dumps(query), fl="*,score", sort="score desc")

    result=[]

    text_min_len=64

    with sqlite3.connect(art_db_sqlite) as art_db:
        for doc in response.docs:
            df_regions = pd.read_sql("SELECT type, text, article_pos, page,"
                                     "min_x, min_y, max_x, max_y FROM regions WHERE article_id=?",
                                     con=art_db, params=(doc["article_id"],))

            header = " ".join(df_regions.loc[df_regions.type == "header"]. \
                              sort_values(by="article_pos", ascending=True).text.tolist())

            regions = df_regions.loc[df_regions.type == "paragraph"]. \
                sort_values(by="article_pos", ascending=True).text.tolist()

            text = " ".join(regions)

            if len(text) < text_min_len:
                continue

            page = int(df_regions.page.iloc[0])

            left = int(df_regions.min_x.min())
            top = int(df_regions.min_y.min())
            width = int(df_regions.max_x.max() - left)
            height = int(df_regions.max_y.max() - top)

            #https://dfg-viewer.de/show/?set%5Bmets%5D=https://content.staatsbibliothek-berlin.de/zefys/SNP11614109-18820501-0-0-0-0.xml
            #https://dfg-viewer.de/show?id=9&tx_dlf%5Bid%5D=https%3A%2F%2Fcontent.staatsbibliothek-berlin.de%2Fzefys%2FSNP11614109-18820501-0-0-0-0.xml&tx_dlf%5Bpage%5D=4

            dfg_viewer_url = \
                "https://dfg-viewer.de/show?id=9&tx_dlf%5Bid%5D="\
                "https%3A%2F%2Fcontent.staatsbibliothek-berlin.de%2Fzefys%2FSNP"\
                "{}-{}{:02d}{:02d}-{}-0-0-0.xml&tx_dlf%5Bpage%5D={}".\
                    format(doc["zdbid"], doc["year"], doc["month"], doc["day"], doc["issue"] - 1, page)

            image_url = \
                ("https://content.staatsbibliothek-berlin.de/zefys/"
                 "SNP{}-{}{:02d}{:02d}-{}-{}-0-0/{},{},{},{}/full/0/default.jpg"). \
                    format(doc["zdbid"], doc["year"], doc["month"], doc["day"], doc["issue"]-1, page,
                           left,top,width, height)

            full_image_url = \
                ("https://content.staatsbibliothek-berlin.de/zefys/"
                 "SNP{}-{}{:02d}{:02d}-{}-{}-0-0/full/full/0/default.jpg"). \
                    format(doc["zdbid"], doc["year"], doc["month"], doc["day"], doc["issue"] - 1, page)

            full_image_url += "?highlight={},{},{},{}&highlightColor=ff0000".format(left,top,width,height)

            publication = get_publication_name(doc["zdbid"], articles)

            publication = publication.split(":")[0]

            result.append({"article_id": doc["article_id"],
                           "score": doc["score"],
                           "zdbid": doc["zdbid"],
                           "year": doc["year"],
                           "month": doc["month"],
                           "day": doc["day"],
                           "issue": doc["issue"],
                           "page": page,
                           "url" : image_url,
                           "full_image_url" : full_image_url,
                           "dfg_viewer_url" : dfg_viewer_url,
                           "publishing_date": doc["publishing_date"][:10],
                           "publication" : publication,
                           "header": header,
                           "text": text,
                           "regions": regions})

    df_result = pd.DataFrame.from_dict(result)
    # print(df_result.head())

    ret = {
        "docs" : result[0:k],
        "score_mean" : df_result.score.mean() if len(df_result) > 0 else 0.0,
        "score_std" : df_result.score.std()  if len(df_result) > 0 else 0.0,
    }

    return jsonify(ret)


@app.route('/configuration')
@htpasswd.required
def configuration(user):
    result = dict()

    result['CONFIGURATION'] = app.config['CONFIGURATION']

    return jsonify(result)

@app.route('/<path:path>')
@htpasswd.required
def send_js(user, path):
    del user

    return send_from_directory('static', path)
