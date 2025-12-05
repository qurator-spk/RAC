import io

import click
import os

import ipdb
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


def apply_filter(df, column_name, values, start, stop):
    if start is not None and stop is not None:

        df = df.loc[(df[column_name] >= start) & (df[column_name] < stop)]

    elif len(values) > 0:
        df = df.loc[df[column_name].isin(values)]

    return df


@click.command()
@click.option('--zefys-filelist', type=str, default=None,help=""
                                                              "Run in /nfs/zefys (takes roughly 24 hours!):         "
                                                              "find ./ -wholename \"*/presentation/*.jpg\" "
                                                              "   -o -wholename \"*/presentation/*.jpeg\""
                                                              "   -o -wholename \"*/presentation/*.png\" > "
                                                              "~/SPUNK/workbench/zefys_image_files.txt")
def scanner(zefys_filelist):
    """
    :return:
    """
    pass


@click.command()
@click.argument('scan-images-file', type=click.Path(exists=True))
@click.argument('target-path', type=click.Path(exists=False))
@click.option('--zefys-prefix', type=str, default=None,
              help="")
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
def downloader(scan_images_file, target_path, zefys_prefix, zdb_id,
               year, start_year, stop_year,
               month, start_month, stop_month,
               day, start_day, stop_day,
               issue, start_issue, stop_issue,
               page, start_page, stop_page,
               language, batch_size, start_batch, num_batches, exclude_tsv):
    """
    SCAN_IMAGES_FILE: A TSV file containing of list of all ZEFYS page scan image files that are to be considered.
    (see zefys-scanner)
    """

    df_files = pd.read_csv(scan_images_file, sep='\t', low_memory=False)

    df_files.year = df_files.year.astype(int)
    df_files.month = df_files.month.astype(int)
    df_files.day = df_files.day.astype(int)
    df_files.issue = df_files.issue.astype(int)

    print("Read {} entries from {} ...".format(len(df_files), scan_images_file))

    df_files = apply_filter(df_files, "zdb", zdb_id, None, None)
    df_files = apply_filter(df_files, "year", year, start_year, stop_year)
    df_files = apply_filter(df_files, "month", month, start_month, stop_month)
    df_files = apply_filter(df_files, "day", day, start_day, stop_day)
    df_files = apply_filter(df_files, "issue", issue, start_issue, stop_issue)
    df_files = apply_filter(df_files, "page", page, start_page, stop_page)
    df_files = apply_filter(df_files, "language", language, None, None)

    if exclude_tsv is not None:
        df_excl = []
        for tsv_file in exclude_tsv:
            df_excl.append(pd.read_csv(tsv_file, sep='\t', low_memory=False).rename(columns={"zdb_id": "zdb"}))
        df_excl = pd.concat(df_excl).reset_index(drop=True)

        df_files = df_files.merge(df_excl, on=['zdb', 'year', 'month', 'day', 'issue', 'page'], how="left")
        df_files = df_files.loc[df_files.file.isnull()]
        df_files = df_files.drop(columns=["file"])

    print("{} entries remain after filtering.".format(len(df_files)))

    print("Sorting ...")

    df_files = df_files.sort_values(by=['year', 'month', 'day', 'issue', 'page'])

    print("done.")

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

    if zefys_prefix is not None:

        if not zefys_prefix.endswith("/"):
            zefys_prefix += "/"

        if batch_size is None:
            link_batch(df_files, target_path)
        else:

            if not target_path.endswith("/"):
                target_path += "/"

            max_batches = int(np.ceil(len(df_files)/batch_size))
            print("max number of batches: {}".format(max_batches))

            if num_batches is None:
                num_batches = max_batches

            num_batches = num_batches if start_batch + num_batches < max_batches else max_batches - start_batch

            for b in range(start_batch, start_batch + num_batches):
                link_batch(df_files.iloc[b*batch_size:(b+1)*batch_size, :],
                           "{}batch-{}".format(target_path, b))
    else:
        pass

    pass


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

    def __init__(self, file, target_file, xml_data):

        self._file = file
        self._target_file = target_file
        self._xml_data = xml_data

    def __call__(self, *args, **kwargs):

        # noinspection PyBroadException
        try:
            xml_data = io.BytesIO(self._xml_data)

            with zipfile.ZipFile(xml_data, mode="r", compression=zipfile.ZIP_BZIP2) as zf:
                buffer = zf.read(name=self._file)

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
def unpack_ocr_database(sqlite_file, flat, processes):
        def get_unzip_tasks():
            with (sqlite3.connect(sqlite_file) as con):
                cur = con.cursor()
                cur.execute('SELECT * from ocr')

                _cur_it = tqdm(cur)

                for (aid, zdb_id, year, month, day, issue, page, file, xml_data) in _cur_it:

                    if flat:
                        target_file = "{}-{}-{}-{}-{}-{}.xml".format(zdb_id, year,
                                                                        month, day, issue, page)
                    else:

                        target_path = "./{}/{}/{}/{}/{}".format(zdb_id, year, month, day, issue)

                        Path(target_path).mkdir(parents=True, exist_ok=True)

                        target_file = "{}/{}-{}-{}-{}-{}-{}.xml".format(target_path, zdb_id, year,
                                                                        month, day, issue, page)

                    # _cur_it.set_description(target_file +"\t\t\t\t")

                    yield UnzipTask(file, target_file, xml_data)

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
@click.option('--pattern', type=str, default="*.xml", help="File pattern to search for. Default: *.xml")
@click.option('--follow-symlinks', type=bool, is_flag=True, default=False)
@click.option('--subset-json', type=click.Path(exists=True), default=None,
              help="Consider only the subset of page-XML files defined in this json file.")
@click.option('--subset-dirs-json', type=click.Path(exists=True), default=None,
              help="Recursively search only through a subset of sub-directories as defined in this json file.")
@click.option('--processes', type=int, default=None, help="Number of parallel processes to be used. "
                                                          "(default all cores)")
def create_ocr_database(directory, sqlite_file, pattern, follow_symlinks, subset_json, subset_dirs_json, processes):

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

    print("Scanning for {} files ...".format(pattern))
    page_xmls = []
    for afile in _file_it:

        if subset is not None:
            if os.path.basename(afile) not in subset:
                continue

        if not (m := re.match("(.*?)-(.*?)-(.*?)-(.*?)-(.*?)-(.*?).xml", os.path.basename(afile))):
            print("Warning! XML filename doest not match ZDBID-YEAR-MONTH-DAY-ISSUE-PAGE.xml pattern: {}".format(afile))
            continue

        page_xmls.append((afile,) + m.group(1, 2, 3, 4, 5, 6))

        _file_it.set_description("[{}]".format(len(page_xmls)))

    page_xmls = pd.DataFrame(page_xmls, columns=['file', 'zdb_id', 'year', 'month', 'day', 'issue', 'page'])

    def get_zip_tasks():
        for _, (a_file,) in page_xmls[['file']].iterrows():
            yield ZipTask(a_file)

    for col in ['year', 'month', 'day', 'issue', 'page']:
        page_xmls[col] = page_xmls[col].astype(int)

    with (sqlite3.connect(sqlite_file) as con):
        setup_ocr_database(con)

        for (_, (file, zdb_id, year, month, day, issue, page)), (xfile, xml_data) \
                        in tqdm(zip(page_xmls.iterrows(), prun(get_zip_tasks(), processes=processes)),
                                total=len(page_xmls)):

            if xfile is None or xml_data is None:
                continue

            assert (file == xfile)

            con.execute('INSERT INTO ocr(zdb_id, year, month, day, issue, page, file, xml_data) '
                        'VALUES(?,?,?,?,?,?,?,?)',
                        (zdb_id, year, month, day, issue, page, file, sqlite3.Binary(xml_data.read())))
