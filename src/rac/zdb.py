import pandas as pd
from tqdm import tqdm
import requests
import xml.etree.ElementTree as ElementTree
import os
import json

def get_zdb_meta_dummy(df):

    vals = pd.DataFrame(df.zdb_id.value_counts().reset_index())

    df_meta = []
    for _, (zdb, count) in tqdm(vals.iterrows(), total=len(vals), desc="Retrieving dummy ZDB meta data ..."):

        df_meta.append({"zdb_id": zdb, "title": "UNK", "creator": "UNK", "publisher": "UNK", "date": "UNK",
                        "language": "UNK"})

    df_meta = pd.DataFrame(df_meta).reset_index(drop=True).set_index("zdb_id")

    return df_meta

def get_zdb_meta_data(df, json_file=None):

    if json_file is not None and os.path.exists(json_file):
        with open(json_file, "r", encoding="utf-8") as afile:
            df_meta = json.loads(afile.read())
    else:
        vals = pd.DataFrame(df.zdb_id.value_counts().reset_index())

        df_meta = []
        for _, (zdb, count) in tqdm(vals.iterrows(), total=len(vals), desc="Retrieving ZDB meta data ..."):
            zdb_id = zdb[0:-1] + "-" + zdb[-1:]

            url = ("https://services.dnb.de/sru/zdb?"
                   "version=1.1&operation=searchRetrieve&query=zdbid={}&recordSchema=oai_dc").format(zdb_id)

            response = requests.get(url, stream=True)

            response.raw.decode_content = True

            events = ElementTree.iterparse(response.raw)

            meta = {"zdb_id": zdb, "title": "", "creator": "", "publisher": "", "date": "", "language": ""}

            for event, elem in events:
                # print(elem.tag, elem.text)

                if elem.tag == "{http://purl.org/dc/elements/1.1/}title":
                    meta["title"] = elem.text
                    continue

                if elem.tag == "{http://purl.org/dc/elements/1.1/}creator":
                    meta["creator"] = elem.text
                    continue

                if elem.tag == "{http://purl.org/dc/elements/1.1/}publisher":
                    meta["publisher"] = elem.text
                    continue

                if elem.tag == "{http://purl.org/dc/elements/1.1/}date":
                    meta["date"] = elem.text
                    continue

                if elem.tag == "{http://purl.org/dc/elements/1.1/}language":
                    meta["language"] = elem.text
                    continue

            df_meta.append(meta)

    if json_file is not None and not os.path.exists(json_file):
        with open(json_file, "w", encoding="utf-8") as afile:
            json.dump(df_meta, afile, ensure_ascii=False, indent=3)

    df_meta = pd.DataFrame(df_meta).reset_index(drop=True).set_index("zdb_id")

    return df_meta