import io

import click
import os

import numpy as np
import pandas as pd

from tqdm import tqdm
import re
import json
from fnmatch import fnmatch
import sqlite3
import zipfile

import requests


from lxml import etree as ET
import xml.etree.ElementTree as ElementTree

from .parallel import run as prun

from pathlib import Path

from .zdb import get_zdb_meta_data  # , get_zdb_meta_dummy

import random as rnd
import string


def apply_filter(df, column_name, values, start, stop):
    if start is not None and stop is not None:

        df = df.loc[(df[column_name] >= start) & (df[column_name] < stop)]
    elif start is not None:
        df = df.loc[df[column_name] >= start]
    elif stop is not None:
        df = df.loc[df[column_name] < stop]
    elif len(values) > 0:
        df = df.loc[df[column_name].isin(values)]

    return df


@click.command()
@click.argument('w3c-anno-json', type=click.Path(exists=True))
@click.argument('target_dir', type=click.Path())
@click.option('--from-zefys', type=bool, is_flag=True, default=False, help="")
@click.option('--user', type=str, default=None, help="")
@click.option('--password', type=str, default=None, help="")
def download_w3c_annotation_images(w3c_anno_json, target_dir, from_zefys, user, password):

    with open(w3c_anno_json) as fh:
        data = json.load(fh)

    df = pd.DataFrame([(data[i]['target']['source'],
                        data[i]['target']['selector']['value']) for i in range(0, len(data))],
                      columns=["url", "value"])

    print("Number of annotations: {}".format(len(df)))

    urls = df.drop_duplicates(subset=["url"])[["url"]].reset_index(drop=True)

    if from_zefys:
        urls["file"] = urls.url.str.extract('.*/(SNP[0-9-X]+)/.*') + ".jpg"
        urls["path"] = target_dir + "/" if not target_dir.endswith("/") else ""
    else:
        urls[['protocol', 'path', 'file']] =\
            urls.url.str.extract("(.*)://(.*)/(.*)").\
                rename(columns={0: "protocol", 1: "path", 2: "file"})

        urls["path"] = target_dir + "/" if not target_dir.endswith("/") else "" + urls.path

        urls.loc[urls.file.str.len() == 0, 'file'] = "default.jpg"
        urls.loc[~urls.file.str.endswith(".jpg"), 'file'] += ".jpg"

    urls['target_file'] = urls.path + "/" + urls.file

    for _, row in tqdm(urls.iterrows(), desc="Downloading image files ..."):

        if os.path.exists(row.target_file):
            print("Skipping {}".format(row.target_file))
            continue

        if user is None and password is None:
            img_data = requests.get(row.url).content
        else:
            img_data = requests.get(row.url, auth=(user, password)).content

        if 'path' in urls.columns:
            os.makedirs(row.path, exist_ok=True)

        with open(row.target_file, 'wb') as imf:
            imf.write(img_data)


@click.command()
@click.argument('out-file', type=click.Path(exists=False))
@click.option('--directory', type=str, default=None,
              help="Recursively search image files in the directory. See also options: "
                   "pattern, follow-symlinks, subset-json, subset-dirs-json")
@click.option('--zefys-filelist', type=str,
              default=None, help="A pre-computed image file list as text file. "
                                 "One image file with absolute path per line. "
                                 "Can be obtained for instance from "
                                 "running in /nfs/zefys (takes roughly 24 hours!):         "
                                 "find ./ -wholename \"*/presentation/*.jpg\" "
                                 "   -o -wholename \"*/presentation/*.jpeg\""
                                 "   -o -wholename \"*/presentation/*.png\" > "
                                 "zefys_image_files.txt")
@click.option('--pattern', type=str, multiple=True,
              default=["*/presentation/*.jpg", "*/presentation/*.jpeg", "*/presentation/*.png" ],
              help="File pattern to search for in case of directory search. "
                   "Default: "
                   "[\"*/presentation/*.jpg\", \"*/presentation/*.jpeg\", \"*/presentation/*.png\" ]"
                   "Can be used in order to consider"
                   " only a particular subset of subdirectories in the recursive search, for "
                   "instance */presentation/*.jpg considers only .jpg files located in a "
                   "subdirectory \"presentation\"")
@click.option('--follow-symlinks', type=bool, is_flag=True, default=False)
@click.option('--subset-json', type=click.Path(exists=True), default=None,
              help="Consider only the subset of page-XML files defined in this json file.")
@click.option('--subset-dirs-json', type=click.Path(exists=True), default=None,
              help="Recursively search only through a subset of sub-directories as defined in this json file.")
def scanner(out_file, directory, zefys_filelist, pattern, follow_symlinks, subset_json, subset_dirs_json):
    """
    Recursively search some directory for image files. Process the filenames of the found files
    with regular expressions in order to extract information such as ZDB_ID, YEAR, MONTH, DAY,
    ISSUE, PAGE from them. Output a tab separated value file (TSV) that contains all this
    information for further use for instance with zefys-downloader.
    """

    if zefys_filelist is not None:
        df_all = pd.read_csv(zefys_filelist, header=None, names=["fullpath"])
    elif directory is not None:
        subset_dirs = None
        if subset_dirs_json is not None:
            with open(subset_dirs_json, 'r') as sdf:
                subset_dirs = set(json.load(sdf))

        def file_it(to_scan):
            nonlocal subset_dirs
            nonlocal follow_symlinks

            for af in os.scandir(to_scan):

                try:
                    if af.is_dir(follow_symlinks=follow_symlinks):

                        if subset_dirs is not None and af.path not in subset_dirs:
                            continue

                        for g in file_it(af):
                            yield g
                    else:
                        if not fnmatch(af.path, pattern):
                            continue
                        yield af.path
                except NotADirectoryError:
                    continue

        subset = None
        if subset_json is not None:
            with open(subset_json, 'r') as f:
                subset = json.load(f)

        _file_it = tqdm(file_it(directory))

        df_all = []

        for file in _file_it:

            if subset is not None:
                if os.path.basename(file) not in subset:
                    continue

            df_all.append(file)

        df_all = pd.DataFrame(df_all, columns=["fullpath"])
    else:
        raise RuntimeError("Either directory or zefys-filelist have to be given!.")

    # remove certain files since they are XML files but not of interest for our purposes
    df = df_all.loc[~df_all.fullpath.str.startswith('./scandata')
                    & ~df_all.fullpath.str.startswith('./_tosort')].copy()

    df[['zdb', 'year', 'month', 'day', 'issue']] =\
        df.fullpath.str.extract('./[publish/]*([^/]+)/([^/]+)/([^/]+)/([^/]+)/([^/]+)/.*')

    df = df.dropna()

    df[['zdb']] = df.zdb.str.extract('([^_]+).*')

    df[['page', 'type']] = df.fullpath.str.extract('.*?([0-9]+).(png|jpg|jpeg|tif)$')

    df.page = df.page.astype(int)

    counter = dict()
    for _, df_part in tqdm(df.groupby(['zdb', 'year', 'month', 'day', 'issue']), total=len(df)):
        min_page = df_part.page.min()
        if min_page not in counter:
            counter[min_page] = 0

        counter[min_page] += 1

    df = df.loc[df.page > 0]

    df.issue = df.issue.astype(int)

    df_meta = get_zdb_meta_data(df)

    df_meta.title = df_meta.title.str.extract('([^:]*).*?')

    df_tmp = df_meta.merge(df, on='zdb')

    df_tmp['url'] = "https://content.staatsbibliothek-berlin.de/zefys/SNP" + \
                    df_tmp.zdb + "-" + df_tmp.year + df_tmp.month + df_tmp.day + "-" + \
                    (df_tmp.issue - 1).astype(str) + "-" + df_tmp.page.astype(str) + "-0-0/full/full/0/default.jpg"

    df_tmp.reset_index(drop=True).to_csv(out_file, sep='\t')


@click.command()
@click.argument('scan-images-file', type=click.Path(exists=True))
@click.argument('target-path', type=click.Path(exists=False))
@click.option('--zefys-prefix', type=str, default=None,
              help="ZEFYY NFS storage path. If specified only symlinks to this location will be created.")
@click.option('--zdb-id', type=str, multiple=True, default=None,
              help="Consider only this ZDB-ID (can be supplied multiple times).")
@click.option('--year', type=int, multiple=True, default=None,
              help="Consider only this year (can be supplied multiple times).")
@click.option('--start-year', type=int, default=None,
              help="Consider a time interval [start-year, stop-year[")
@click.option('--stop-year', type=int, default=None,
              help="Consider a time interval [start-year, stop-year[")
@click.option('--month', type=int, multiple=True, default=None,
              help="Consider only this month (can be supplied multiple times).")
@click.option('--start-month', type=int, default=None,
              help="Consider a time interval [start-month, stop-month[")
@click.option('--stop-month', type=int, default=None,
              help="Consider a time interval [start-month, stop-month[")
@click.option('--day', type=int, multiple=True, default=None,
              help="Consider only this day (can be supplied multiple times).")
@click.option('--start-day', type=int, default=None,
              help="Consider a time interval [start-day, stop-day[")
@click.option('--stop-day', type=int, default=None,
              help="Consider a time interval [start-day, stop-day[")
@click.option('--issue', type=int, multiple=True, default=None,
              help="Consider only this issue (can be supplied multiple times).")
@click.option('--start-issue', type=int, default=None,
              help="Consider a time interval [start-issue, stop-issue[")
@click.option('--stop-issue', type=int, default=None,
              help="Consider a time interval [start-issue, stop-issue[")
@click.option('--page', type=int, multiple=True, default=None,
              help="Consider only this page (can be supplied multiple times).")
@click.option('--start-page', type=int, default=None,
              help="Consider a page interval [start-page, stop-page[")
@click.option('--stop-page', type=int, default=None,
              help="Consider a page interval [start-page, stop-page[")
@click.option('--language', type=int, multiple=True, default=None,
              help="Consider only this language (can be supplied multiple times).")
@click.option('--batch-size', type=int, default=None,
              help="Split into batches of this size.")
@click.option('--start-batch', type=int, default=0,
              help="Ignore all batches before start-batch.")
@click.option('--num-batches', type=int, default=None,
              help="Create at most num-batches.")
@click.option('--exclude-tsv', type=click.Path(exists=True), multiple=True, default=None,
              help="Exclude the files listed in this TSV file. Can be supplied multiple times")
@click.option('--dry-run', type=bool, is_flag=True, default=False,
              help="Do not actually do anything.")
@click.option('--random', is_flag=True, default=False, help="")
@click.option('--page-sequence-len', type=int, default=None,
              help="")
@click.option('--max-count', type=int, default=None,
              help="Limits the number of returned items.")
@click.option('--tag-csv-file', type=str, default=None, help="")
@click.option('--scan-images-separator', type=str, default='\t', help="")
def downloader(scan_images_file, target_path, zefys_prefix, zdb_id,
               year, start_year, stop_year,
               month, start_month, stop_month,
               day, start_day, stop_day,
               issue, start_issue, stop_issue,
               page, start_page, stop_page,
               language, batch_size, start_batch, num_batches, exclude_tsv, dry_run,
               random, page_sequence_len, max_count, tag_csv_file, scan_images_separator):
    """
    The tool either creates symlinks to ZEFYS image files or downloads ZEFYS image files in full resolution from the
    SBB content server. The option --zefys-prefix controls if sysmlinks are used or rather the files are downloaded
    from the content server. If --zefys-prefix is provided, it should point to a directory where the ZEFYS NFS is
    mounted. Then the resulting batch directories will only contain sysmlinks to the full resolution images.
    If --zefys-prefix is omitted then the images would be downloaded.

    The symlinks or files are stored in a batch directory structure where the option --batch-size controls how many
    items are stored per batch directory. Which newspapers and time periods are included can be controlled by the
    --zdb-id, --year, --month ... options. If batch-size is not given then all items are stored flatly in one directory.

    The --max-count option limits the number of returned items.
    The --random option implements a uniform sampling from the items remaining after filtering.
    For instance max-count=1000 and --random option combined create a uniform random sample of size 1000.

    The --page_sequence_len option force a grouping of pages for instance page-sequence-len=3 returns random
    page-sequences of length 3. When combined with tag-csv-file, a CSV file ist written that contains the grouping
    information which can be imported into the image-search via the add_ZEFYS_tags tool that is also included in this
    package.

    SCAN_IMAGES_FILE: A TSV file containing of list of all ZEFYS page scan image files that are to be considered.
    This file can be created with zefys-scanner.

    TARGET_PATH: Either the name of the new directory where the symlinks or downloaded images are stored if batch-size
    is omitted or a prefix for the batch directories names to be created if batch-size is specified.
    """

    df_files = pd.read_csv(scan_images_file, sep=scan_images_separator, low_memory=False)

    df_files.year = df_files.year.astype(int)
    df_files.month = df_files.month.astype(int)
    df_files.day = df_files.day.astype(int)
    df_files.issue = df_files.issue.astype(int)

    df_files = df_files.drop_duplicates(subset=["zdb", "year", "month", "day", "issue", "page"])

    print("Read {} entries from {} ...".format(len(df_files), scan_images_file))

    df_files = apply_filter(df_files, "zdb", zdb_id, None, None)
    df_files = apply_filter(df_files, "year", year, start_year, stop_year)
    df_files = apply_filter(df_files, "month", month, start_month, stop_month)
    df_files = apply_filter(df_files, "day", day, start_day, stop_day)
    df_files = apply_filter(df_files, "issue", issue, start_issue, stop_issue)
    df_files = apply_filter(df_files, "page", page, start_page, stop_page)
    df_files = apply_filter(df_files, "language", language, None, None)

    if exclude_tsv is not None and len(exclude_tsv) > 0:
        df_excl = []
        for tsv_file in exclude_tsv:
            df_excl.append(pd.read_csv(tsv_file, sep='\t', low_memory=False).rename(columns={"zdb_id": "zdb"}))
        df_excl = pd.concat(df_excl).reset_index(drop=True)

        df_files = df_files.merge(df_excl, on=['zdb', 'year', 'month', 'day', 'issue', 'page'], how="left")
        df_files = df_files.loc[df_files.file.isnull()]
        df_files = df_files.drop(columns=["file"])

    print("Sorting ...")

    if random:
        df_files = df_files.iloc[np.random.permutation(len(df_files))]
    else:
        df_files = df_files.sort_values(by=['year', 'month', 'day', 'issue', 'page'])

    print("done.")

    if page_sequence_len is not None:

        k = 10
        seq_ids = set()

        def rnd_seq_id():

            while True:
                aid = ''.join(rnd.choices(string.ascii_uppercase + string.digits, k=k))

                if aid not in seq_ids:
                    seq_ids.add(aid)
                    return aid

        page_groups = []

        for _, gr in tqdm(df_files.groupby(by=['zdb', 'year', 'month', 'day', 'issue'])):

            gr = gr.sort_values(by=['year', 'month', 'day', 'issue', 'page']).reset_index(drop=True)

            gr_ids = [rnd_seq_id() for _ in range(0, (page_sequence_len*(page_sequence_len-1))*(len(gr)+1))]

            for offset in range(0, page_sequence_len):

                gr["page_group".format(offset)] =\
                        gr.index.map(lambda i: gr_ids[(offset*(page_sequence_len+1)) +
                                                      ((i+offset) - ((i+offset) % page_sequence_len))])
                page_groups.append(gr.copy())

        page_groups = pd.concat(page_groups)

        page_groups = page_groups.sort_values(by=['page_group', 'year', 'month', 'day', 'issue', 'page'])

        page_groups = page_groups.drop_duplicates(subset=['page_group', 'year', 'month', 'day', 'issue', 'page'])

        vc = page_groups.page_group.value_counts()

        page_groups["count"] = page_groups.page_group.map(lambda pg: vc[pg])

        page_groups = page_groups.loc[page_groups["count"] == page_sequence_len]

        if max_count is not None:
            page_groups = page_groups.iloc[0:max_count]

        if tag_csv_file is not None:
            page_groups.to_csv(tag_csv_file)

        df_files = page_groups.drop_duplicates(subset=["zdb", "year", "month", "day", "issue", "page"])

    elif max_count is not None:
        df_files = df_files.iloc[0:max_count]

    if tag_csv_file is not None and page_sequence_len is None:
        df_files.to_csv(tag_csv_file)

    print("{} entries remain after filtering.".format(len(df_files)))

    def link_batch(batch, tpath):

        os.mkdir(tpath)

        for _, (fullpath, url, z, y, m, d, i, p, t) \
                in tqdm(batch[['fullpath', 'url', 'zdb', 'year', 'month', 'day', 'issue', 'page', 'type']].
                                iterrows(), total=len(batch), desc="Creating symlinks in {}".format(tpath)):

            file = zefys_prefix + fullpath

            if not os.path.exists(file):
                print("Warning! File {} does not exist!.".format(file))
                continue

            dest = "{}/{}-{}-{}-{}-{}-{}.{}".format(tpath, z, y, m, d, i, p, t)

            try:
                os.symlink(file, dest)
            except Exception as e:
                print("Error creating {} -> {}".format(file, dest))
                print(str(e))

    def download_batch(batch, tpath):

        os.mkdir(tpath)

        for _, (fullpath, url, z, y, m, d, i, p, t) \
                in tqdm(batch[['fullpath', 'url', 'zdb', 'year', 'month', 'day', 'issue', 'page', 'type']].
                                iterrows(), total=len(batch), desc="Creating symlinks in {}".format(tpath)):

            dest = "{}/{}-{}-{}-{}-{}-{}.{}".format(tpath, z, y, m, d, i, p, t)

            image_url = None
            try:
                image_url = \
                    ("https://content.staatsbibliothek-berlin.de/zefys/"
                     "SNP{}-{}{:02d}{:02d}-{}-{}-0-0/full/full/0/default.jpg"). \
                        format(z, y, m, d, i - 1, p)

                img_data = requests.get(image_url).content

                with open(dest, 'wb') as imf:
                    imf.write(img_data)

            except Exception as e:
                print("Error downloading {}".format(image_url))
                print(str(e))

    if zefys_prefix is not None:

        if not zefys_prefix.endswith("/"):
            zefys_prefix += "/"

        if batch_size is None:
            if dry_run:
                return

            link_batch(df_files, target_path)
        else:

            if not target_path.endswith("/"):
                target_path += "/"

            max_batches = int(np.ceil(len(df_files)/batch_size))
            print("max number of batches: {}".format(max_batches))

            if dry_run:
                return

            if num_batches is None:
                num_batches = max_batches

            num_batches = num_batches if start_batch + num_batches < max_batches else max_batches - start_batch

            for b in range(start_batch, start_batch + num_batches):
                link_batch(df_files.iloc[b*batch_size:(b+1)*batch_size, :],
                           "{}batch-{}".format(target_path, b))
    else:
        if batch_size is None:
            if dry_run:
                return

            download_batch(df_files, target_path)
        else:

            if not target_path.endswith("/"):
                target_path += "/"

            max_batches = int(np.ceil(len(df_files)/batch_size))
            print("max number of batches: {}".format(max_batches))

            if dry_run:
                return

            if num_batches is None:
                num_batches = max_batches

            num_batches = num_batches if start_batch + num_batches < max_batches else max_batches - start_batch

            for b in range(start_batch, start_batch + num_batches):
                download_batch(df_files.iloc[b*batch_size:(b+1)*batch_size, :],
                           "{}batch-{}".format(target_path, b))


def setup_ocr_database(conn):
    conn.execute('BEGIN EXCLUSIVE TRANSACTION')

    conn.execute('CREATE TABLE IF NOT EXISTS ocr ('
                 'id INTEGER PRIMARY KEY, '
                 'zdb_id TEXT NOT NULL, '
                 'year INTEGER,'
                 'month INTEGER, '
                 'day INTEGER, '
                 'issue INTEGER, '
                 'page INTEGER, '
                 'file TEXT NOT NULL, '
                 'xml_data BLOB NOT NULL)'
                 )

    conn.execute('CREATE INDEX IF NOT EXISTS idx_zdb ON ocr(zdb_id);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_year ON ocr(year);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_month ON ocr(month);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_day ON ocr(day);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_issue ON ocr(issue);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_page ON ocr(page);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_issue_all_pages ON ocr(zdb_id, year, month, day, issue);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_zdb_id_year ON ocr(zdb_id, year);')

    conn.execute('COMMIT TRANSACTION')


class UnzipTask:

    def __init__(self, file, target_file, xml_data, target_path=None, image_url=None):

        self._file = file
        self._target_file = target_file
        self._xml_data = xml_data
        self._target_path = target_path
        self._image_url = image_url

    def __call__(self, *args, **kwargs):

        # noinspection PyBroadException
        try:
            xml_data = io.BytesIO(self._xml_data)

            with zipfile.ZipFile(xml_data, mode="r", compression=zipfile.ZIP_BZIP2) as zf:
                assert len(zf.filelist) == 1
                buffer = zf.read(name=zf.filelist[0].filename)

            if self._target_path is not None and self._image_url is not None:

                parser = ET.XMLParser(encoding='UTF-8')
                tree = ElementTree.parse(io.BytesIO(buffer), parser=parser)
                page = tree.find("{http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15}Page")
                meta_data_creator = (
                    tree.find("{http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15}Metadata/"
                              "{http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15}Creator"))

                img_filename = os.path.basename(page.attrib['imageFilename'])
                # img_width = page.attrib['imageWidth']
                # img_height = page.attrib['imageHeight']

                # img_url = self._image_url.replace("__PAGE_SHAPE__", "{},{}".format(img_width, img_height))

                img_url = self._image_url.replace("__PAGE_SHAPE__", "full")

                neat_url = img_url.replace("__RECT__", "left,top,width,height")

                img_url = img_url.replace("__RECT__", "full")

                if meta_data_creator is not None:
                    meta_data_creator.text = (meta_data_creator.text + "|IIIF_URL:" + img_url +
                                              "|NEAT_URL:" + neat_url + "|")

                page.attrib['imageFilename'] = img_filename

                img_data = requests.get(img_url).content
                with open("{}/{}".format(self._target_path,img_filename), 'wb') as imf:
                    imf.write(img_data)

                buffer = ET.tostring(tree.getroot(), encoding='UTF-8')

            if type(self._target_file) == str:
                with open(self._target_file, "wb") as tf:
                    tf.write(buffer)
            else:
                self._target_file.write(buffer)
                self._target_file.seek(0)

        except Exception as e:
            print(e)
            return None

        return self._target_file


# noinspection SpellCheckingInspection
@click.command()
@click.argument('sqlite-file', type=click.Path(exists=True))
@click.argument('tsv-file-out', type=click.Path(exists=False))
def extract_filelist_ocr_database(sqlite_file, tsv_file_out):

    with sqlite3.connect(sqlite_file) as con:
        df_files = pd.read_sql("SELECT zdb_id, year , month, day, issue, page, file FROM ocr", con=con)

        df_files.to_csv(tsv_file_out, sep='\t', index=False)


@click.command()
@click.argument('sqlite-file', type=click.Path(exists=False))
@click.option('--flat', type=bool, is_flag=True, default=False, help="Do not create a directory structure.")
@click.option('--processes', type=int, default=None, help="Number of parallel processes to be used. "
                                                          "(default all cores)")
@click.option('--download-images',
              type=bool, is_flag=True, default=False, help="Download corresponding images from SBB content server."
                                                           "BEWARE: USE WITH CARE!!!!!")
@click.option('--dry-run', type=bool, is_flag=True, default=False, help="Do not actually unpack anything.")
@click.option('--zdb-id', type=str, multiple=True, default=None,
              help="Consider only this ZDB-ID (can be supplied multiple times).")
@click.option('--year', type=int, multiple=True, default=None,
              help="Consider only this year (can be supplied multiple times).")
@click.option('--start-year', type=int, default=None,
              help="Consider a time interval [start-year, stop-year[")
@click.option('--stop-year', type=int, default=None,
              help="Consider a time interval [start-year, stop-year[")
@click.option('--month', type=int, multiple=True, default=None,
              help="Consider only this month (can be supplied multiple times).")
@click.option('--start-month', type=int, default=None,
              help="Consider a time interval [start-month, stop-month[")
@click.option('--stop-month', type=int, default=None,
              help="Consider a time interval [start-month, stop-month[")
@click.option('--day', type=int, multiple=True, default=None,
              help="Consider only this day (can be supplied multiple times).")
@click.option('--start-day', type=int, default=None,
              help="Consider a time interval [start-day, stop-day[")
@click.option('--stop-day', type=int, default=None,
              help="Consider a time interval [start-day, stop-day[")
@click.option('--issue', type=int, multiple=True, default=None,
              help="Consider only this issue (can be supplied multiple times).")
@click.option('--start-issue', type=int, default=None,
              help="Consider a time interval [start-issue, stop-issue[")
@click.option('--stop-issue', type=int, default=None,
              help="Consider a time interval [start-issue, stop-issue[")
@click.option('--page', type=int, multiple=True, default=None,
              help="Consider only this page (can be supplied multiple times).")
@click.option('--start-page', type=int, default=None,
              help="Consider a page interval [start-page, stop-page[")
@click.option('--stop-page', type=int, default=None,
              help="Consider a page interval [start-page, stop-page[")
def unpack_ocr_database(sqlite_file, flat, processes, download_images, dry_run,
                        zdb_id, year, start_year, stop_year, month, start_month, stop_month,
                        day, start_day, stop_day, issue, start_issue, stop_issue, page, start_page, stop_page):
    with (sqlite3.connect(sqlite_file) as con):

        page_xmls = pd.read_sql("SELECT rowid, file, zdb_id, year, month, day, issue, page FROM ocr",
                                con=con)

        page_xmls.year = page_xmls.year.astype(int)
        page_xmls.month = page_xmls.month.astype(int)
        page_xmls.day = page_xmls.day.astype(int)
        page_xmls.issue = page_xmls.issue.astype(int)

        print("Read {} entries from {} ...".format(len(page_xmls), sqlite_file))

        page_xmls = apply_filter(page_xmls, "zdb_id", zdb_id, None, None)
        page_xmls = apply_filter(page_xmls, "year", year, start_year, stop_year)
        page_xmls = apply_filter(page_xmls, "month", month, start_month, stop_month)
        page_xmls = apply_filter(page_xmls, "day", day, start_day, stop_day)
        page_xmls = apply_filter(page_xmls, "issue", issue, start_issue, stop_issue)
        page_xmls = apply_filter(page_xmls, "page", page, start_page, stop_page)

        print("{} entries remain after filtering.".format(len(page_xmls)))

        if dry_run:
            exit()

        def get_unzip_tasks():
            with (sqlite3.connect(sqlite_file) as con):

                for _, (rowid, file, zdb_id, year, month, day, issue, page) in \
                        tqdm(page_xmls.iterrows(), total=len(page_xmls)):

                    data = pd.read_sql("SELECT xml_data FROM ocr WHERE rowid=?", con=con, params=(rowid,))

                    if len(data) != 1:
                        print("ERROR for rowid {}!".format(rowid))
                        continue
                    xml_data = data.iloc[0].xml_data

                    if flat:
                        target_file = "{}-{}-{}-{}-{}-{}.xml".format(zdb_id, year,
                                                                        month, day, issue, page)

                        target_path = "./"
                    else:

                        target_path = "./{}/{}/{}/{}/{}".format(zdb_id, year, month, day, issue)

                        Path(target_path).mkdir(parents=True, exist_ok=True)

                        target_file = "{}/{}-{}-{}-{}-{}-{}.xml".format(target_path, zdb_id, year,
                                                                        month, day, issue, page)

                    image_url = None
                    if download_images:
                        image_url =\
                            ("https://content.staatsbibliothek-berlin.de/zefys/"
                             "SNP{}-{}{:02d}{:02d}-{}-{}-0-0/__RECT__/__PAGE_SHAPE__/0/default.jpg").\
                                format(zdb_id, year, month, day, issue-1, page)

                    yield UnzipTask(file, target_file, xml_data, target_path, image_url)

        for written_file in prun(get_unzip_tasks(), processes=processes):
            # print(written_file)
            pass


class ZipTask:

    def __init__(self, filename):

        self._filename = filename

    def __call__(self, *args, **kwargs):

        # noinspection PyBroadException
        try:
            xml_data = io.BytesIO()

            with zipfile.ZipFile(xml_data, mode="w", compression=zipfile.ZIP_BZIP2, compresslevel=1) as zf:
                zf.write(filename=self._filename)

            xml_data.seek(0)
        except Exception as e:
            print(e)
            return None, None

        return self._filename, xml_data


@click.command()
@click.argument('directory', type=click.Path(exists=True))
@click.argument('sqlite-file', type=click.Path(exists=False))
@click.option('--pattern', type=str, default="*.xml", help="File pattern to search for. Default: *.xml . "
                                                           "Can be used in order to consider only a particular subset "
                                                           "of subdirectories in the recursive search, for instance "
                                                           "*/ey-ocr*/*.xml considers only XML files located in a "
                                                           "subdirectory that starts with ey-ocr...")
@click.option('--append', type=bool, is_flag=True, default=False,
              help="Append to database file instead of creating a new one. Entries that already exist for a particular "
                   "combination of ZDB-ID,YEAR,MONTH,DAY,ISSUE, and PAGE will be ignored. Only new entries will be "
                   "added.")
@click.option('--update', type=bool, is_flag=True, default=False,
              help="Update database file instead of creating a new one. If a particular combination of "
                   "ZDB-ID,YEAR,MONTH,DAY,ISSUE, and PAGE alreadys exists it would be replaced by the new file.")
@click.option('--follow-symlinks', type=bool, is_flag=True, default=False)
@click.option('--subset-json', type=click.Path(exists=True), default=None,
              help="Consider only the subset of page-XML files defined in this json file.")
@click.option('--subset-dirs-json', type=click.Path(exists=True), default=None,
              help="Recursively search only through a subset of sub-directories as defined in this json file.")
@click.option('--processes', type=int, default=None, help="Number of parallel processes to be used. "
                                                          "(default all cores)")
def create_ocr_database(directory, sqlite_file, pattern, append, update, follow_symlinks, subset_json, subset_dirs_json,
                        processes):
    """
    Creates, appends to, or updates a (new) SQLITE database where the PAGE-XML-OCR files are stored as ZIP-compressed
    binary blobs. This enables space efficient storage, performant access with respect to the properties
    ZDB-ID, YEAR, MONTH, DAY, ISSUE, and PAGE. Additionally, these SQLITE database files can be efficiently copied
    between different host computers, for instance by "scp".

    The tool expects the PAGE-XML filenames to have the following structure: ZDBID-YEAR-MONTH-DAY-ISSUE-PAGE.xml .

    All the XML-files in the database or a particular subset of them can be extract by the command
    "zefys-unpack-ocr-database".

    DIRECTORY: Recursively search XML files in this directory.
    SQLITE_FILE: The database file.
    """

    if os.path.exists(sqlite_file) and not append:
        print("Database file {} exists. Exiting. Did you mean --append or --update ?".format(sqlite_file))
        exit()

    if not os.path.exists(sqlite_file) and (append or update):
        print("Database file {} does not exist but you provided --append or --update?".format(sqlite_file))
        exit()

    subset_dirs = None
    if subset_dirs_json is not None:
        with open(subset_dirs_json, 'r') as sdf:
            subset_dirs = set(json.load(sdf))

    def file_it(to_scan):
        nonlocal subset_dirs
        nonlocal follow_symlinks

        for af in os.scandir(to_scan):

            try:
                if af.is_dir(follow_symlinks=follow_symlinks):

                    if subset_dirs is not None and af.path not in subset_dirs:
                        continue

                    for g in file_it(af):
                        yield g
                else:
                    if not fnmatch(af.path, pattern):
                        continue
                    yield af.path
            except NotADirectoryError:
                continue

    _file_it = tqdm(file_it(directory))

    subset = None
    if subset_json is not None:
        with open(subset_json, 'r') as f:
            subset = json.load(f)

    with (sqlite3.connect(sqlite_file) as con):
        setup_ocr_database(con)

        print("Scanning for {} files ...".format(pattern))
        page_xmls = []
        for afile in _file_it:

            if subset is not None:
                if os.path.basename(afile) not in subset:
                    continue

            if not (m := re.match("(.*?)-(.*?)-(.*?)-(.*?)-(.*?)-(.*?).xml", os.path.basename(afile))):
                print("Warning! XML filename doest not match ZDBID-YEAR-MONTH-DAY-ISSUE-PAGE.xml pattern: {}".format(afile))
                continue

            zdb_id, year, month, day, issue, page = m.group(1, 2, 3, 4, 5, 6)

            if append:
                found = con.execute('SELECT COUNT(*) from ocr '
                                    'WHERE zdb_id=? AND year=? AND month=? AND day=? AND issue=? AND page=?',
                                    (zdb_id, year, month, day, issue, page)).fetchone()[0] > 0

                if found:
                    continue

            page_xmls.append((afile, zdb_id, year, month, day, issue, page))

            _file_it.set_description("[{}]".format(len(page_xmls)))

        page_xmls = pd.DataFrame(page_xmls, columns=['file', 'zdb_id', 'year', 'month', 'day', 'issue', 'page'])

        # noinspection PyTypeChecker
        def get_zip_tasks():
            for _, (a_file,) in page_xmls[['file']].iterrows():
                yield ZipTask(a_file)

        for col in ['year', 'month', 'day', 'issue', 'page']:
            page_xmls[col] = page_xmls[col].astype(int)

        for (_, (file, zdb_id, year, month, day, issue, page)), (x_file, xml_data) \
                        in tqdm(zip(page_xmls.iterrows(), prun(get_zip_tasks(), processes=processes)),
                                total=len(page_xmls)):

            if x_file is None or xml_data is None:
                continue

            assert (file == x_file)

            found = False
            if update:
                found = con.execute('SELECT COUNT(*) from ocr '
                                    'WHERE zdb_id=? AND year=? AND month=? AND day=? AND issue=? AND page=?',
                                    (zdb_id, year, month, day, issue, page)).fetchone()[0] > 0
            if found:
                con.execute('UPDATE ocr SET file=?, xml_data=? '
                            'WHERE zdb_id=? AND year=? AND month=? AND day=? AND issue=? AND page=?',
                            (file, sqlite3.Binary(xml_data.read()), zdb_id, year, month, day, issue, page))
            else:
                con.execute('INSERT INTO ocr(zdb_id, year, month, day, issue, page, file, xml_data) '
                            'VALUES(?,?,?,?,?,?,?,?)',
                            (zdb_id, year, month, day, issue, page, file, sqlite3.Binary(xml_data.read())))


@click.command()
@click.argument('target_sqlite', type=click.Path())
@click.argument('source_sqlite', type=click.Path(exists=True), nargs=-1)
def join_ocr_databases(target_sqlite, source_sqlite):

    print("target: {}".format(target_sqlite))

    with sqlite3.connect(target_sqlite) as tdb:
        setup_ocr_database(tdb)

        for sfile in source_sqlite:
            print("source: {}".format(sfile))

            with sqlite3.connect(sfile) as sdb:

                num_ocr = sdb.execute('SELECT COUNT(*) from ocr').fetchone()[0]

                cur = sdb.cursor()
                cur.execute('SELECT * from ocr')

                _cur_it = tqdm(cur, total=num_ocr)

                for (aid, zdb_id, year, month, day, issue, page, file, xml_data) in _cur_it:

                    tdb.execute('INSERT INTO ocr(zdb_id, year, month, day, issue, page, file, xml_data) '
                                'VALUES(?,?,?,?,?,?,?,?)',
                                (zdb_id, year, month, day, issue, page, file,
                                 sqlite3.Binary(io.BytesIO(xml_data).read())))
