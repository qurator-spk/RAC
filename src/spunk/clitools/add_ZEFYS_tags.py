import sqlite3
import click
import re
import numpy as np
import pandas as pd
from tqdm import tqdm
from datetime import datetime

from qurator.sbb_images.database import setup_tags_table, setup_links_table, setup_iiif_links_table


@click.command()
@click.argument('zefys-csv-file', type=click.Path(exists=True))
@click.argument('sqlite-file', type=click.Path(exists=True))
@click.option('--append', type=bool, is_flag=True, default=False)
def cli(zefys_csv_file, sqlite_file, append):
    """
        PAGE_INFO_FILE:
        SQLITE_FILE: sqlite3 database file that contains the images table.
    """

    timestamp = str(datetime.now())

    with (sqlite3.connect(sqlite_file) as conn):

        setup_tags_table(conn)

        if not append:
            conn.execute('DELETE FROM tags WHERE user="ZEFYS-Meta-Data"')

        # ------

        print("Reading ETH info ...")

        df_zefys = pd.read_csv(zefys_csv_file)

        print("done")

        # ------

        print("Reading image table from database ...")

        df_images = pd.read_sql('select rowid, file from images', conn)

        df_images["filename"] = df_images.file.str.split("/").str[-1]

        df_images[['zdb', 'year', 'month', 'day', 'issue', 'page']] = \
            df_images.file.str.extract(".*/(.*?)-(.*?)-(.*?)-(.*)-(.* ?)-(.* ?).jpg")

        df_images[['year', 'month', 'day', 'issue', 'page']] =\
            df_images[['year', 'month', 'day', 'issue', 'page']].astype(int)

        print("done.")

        # ------

        print("Merging Meta-Data ...")

        df_merged = df_zefys.merge(df_images, on=['zdb', 'year', 'month', 'day', 'issue', 'page'])

        print("done.")

        # ------

        df_all_tags = []

        author = "ZEFYS-Meta-Data"

        zefys_meta_columns = ['title', 'zdb', 'year', 'month', 'day', 'issue', 'page']

        no_prefix = ['title', 'year']

        for _, gr in tqdm(df_merged.groupby(['zdb', 'year', 'month', 'day', 'issue', 'page'])):

            tmp = gr.drop_duplicates(subset=['zdb', 'year', 'month', 'day', 'issue', 'page'])

            row = tmp.iloc[0]

            for mc in zefys_meta_columns:

                if str(row[mc]) == "nan":
                    continue

                df_all_tags.append((row.rowid, (mc + ":" if mc not in no_prefix else "") + str(row[mc]), author,
                                    timestamp, 1))

            for pg in gr.page_group:
                df_all_tags.append((row.rowid, "page_group" + ":" + pg, author, timestamp, 1))

        for _, gr in tqdm(df_merged.groupby(['zdb', 'year', 'month', 'day', 'issue', 'page_group'])):

            for rowid in gr.rowid:
                df_all_tags.append((rowid, "group_pages" + ":" + ",".join(gr.page.astype(str).tolist()), author, timestamp, 1))

        df_all_tags = pd.DataFrame(df_all_tags, columns=['image_id', 'tag', 'user', 'timestamp', 'read_only'])

        if len(df_all_tags) == 0:
            print("No tags added.")
            return

        print("Number of tags written: ", len(df_all_tags))

        df_all_tags.to_sql('tags', con=conn, if_exists='append', index=False)

        links = []
        iiif_links = []
        for _, row in tqdm(df_images.iterrows(), total=len(df_images)):
            url = ("https://content.staatsbibliothek-berlin.de/zefys/"
                   "SNP{}-{}{:02d}{:02d}-{}-{}-0-0/full/full/0/default.jpg").\
                    format(row.zdb, row.year, row.month, row.day, row.issue-1, row.page)

            links.append((url, "", "", row.rowid - 1))
            iiif_links.append((row.rowid, url))

        links = pd.DataFrame(links, columns=['url', 'ppn', 'phys_id', 'index']).set_index('index').sort_index()

        iiif = pd.DataFrame(iiif_links, columns=['image_id', 'url'])

        links.to_sql('links', con=conn, if_exists='replace', index=False)

        setup_links_table(conn)

        iiif.to_sql('iiif_links', con=conn, if_exists='replace', index=False)

        setup_iiif_links_table(conn)


if __name__ == '__main__':
    cli()
