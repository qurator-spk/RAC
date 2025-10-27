import glob
import re
import os
import sqlite3
import io
from io import StringIO
from pathlib import Path

import numpy as np
import click
import pandas as pd

from lxml import etree as ET

import xml.etree.ElementTree as ElementTree
import unicodedata
import json

from pprint import pprint

from matplotlib.image import imread
from tqdm import tqdm
from fnmatch import fnmatch
from zefys import UnzipTask
from parallel import run as prun

from zdb import get_zdb_meta_data


def page_get_reading_order(root):

    order = []

    for order_elem in root.iter('{http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15}RegionRefIndexed'):
        pos = int(order_elem.attrib['index'])
        region_ref = order_elem.attrib['regionRef']

        order.append((pos, region_ref))

    return pd.DataFrame(order, columns=["pos", "region_ref"])

def page_iterate_text_regions(root):

    for region_elem in root.iter('{http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15}TextRegion'):

        the_id = region_elem.attrib['id']
        the_type = region_elem.attrib['type']

        yield the_id, the_type, region_elem

def page_iterate_text_lines(root):

    for line_elem in root.iter('{http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15}TextLine'):

        yield line_elem

def page_iterate_coords(root):

    for coords_elem in root.iter('{http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15}Coords'):

        points = coords_elem.attrib['points']

        yield points

def page_iterate_unicode(root):

    for text_elem in root.iter('{http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15}Unicode'):
        if text_elem.text is None:
            # print("No unicode!")
            continue

        yield text_elem.text

class ExtractRegionsTask:

    def __init__(self, file, xml_data, page):

        self._file = file
        self._xml_data = xml_data
        self._page = page

    def __call__(self, *args, **kwargs):

        # noinspection PyBroadException
        try:
            target_file = io.BytesIO()
            xml_file = UnzipTask(self._file, target_file, self._xml_data)()

            regions = extract_regions(xml_file, self._page)

            return "Regions", regions

        except Exception as e:
            print(e)
            return None, None

class NextArticle:
    def __init__(self, meta):
        self._meta = meta

    def __call__(self, *args, **kwargs):
        return "NextArticle", self._meta

def extract_regions(page_xml_file, page):

    parser = ET.XMLParser(encoding='UTF-8')
    tree = ElementTree.parse(page_xml_file, parser=parser)
    root = tree.getroot()

    order = page_get_reading_order(root)

    regions = []

    for a_id, a_type, region_elem in page_iterate_text_regions(root):

        text = ''
        mean_center_x=0.0
        mean_center_y=0.0
        mean_width = 0.0
        mean_height = 0.0
        count = 0
        for line_elem in page_iterate_text_lines(region_elem):

            points = [p for p in page_iterate_coords(line_elem)]

            x = [int(i) for i in points[0].replace(","," ").split(" ")][0::2]
            y = [int(i) for i in points[0].replace(","," ").split(" ")][1::2]

            text_content = " ".join([tc for tc in page_iterate_unicode(line_elem)])

            if len(text_content) == 0:
                continue

            count += 1
            mean_center_x += np.mean(x)
            mean_center_y += np.mean(y)
            mean_width += max(x) - min(x)
            mean_height += max(y) - min(y)

            text = " ".join([text, text_content])

        if count > 0:

            mean_center_x, mean_center_y, mean_width, mean_height = (mean_center_x/count, mean_center_y/count,
                                                                     mean_width/count, mean_height/count)

            regions.append((a_id, a_type, text, page, mean_center_x, mean_center_y, mean_width, mean_height))

    regions = pd.DataFrame(regions, columns=["id", "type", "text", "page",
                                             "mean_center_x", "mean_center_y",
                                             "mean_width", "mean_height"])

    regions = regions.merge(order, left_on="id", right_on="region_ref")

    regions = regions.sort_values(by=["pos"], ascending=True)

    return regions


def setup_article_database(conn):
    conn.execute('BEGIN EXCLUSIVE TRANSACTION')

    conn.execute('CREATE TABLE IF NOT EXISTS "articles" ('
                 '"index" INTEGER,  "zdb_id" TEXT,  '
                 '"year" INTEGER,  "month" INTEGER,  '
                 '"day" INTEGER,  "issue" INTEGER,  '
                 '"start_page" INTEGER,  "end_page" INTEGER,  '
                 '"article" INTEGER,  "num_pages" INTEGER,  '
                 '"header" TEXT,  "text" TEXT);')

    conn.execute('CREATE INDEX IF NOT EXISTS idx_zdb ON articles(zdb_id);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_year ON articles(year);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_month ON articles(month);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_day ON articles(day);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_issue ON articles(issue);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_start_page ON articles(start_page);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_end_page ON articles(end_page);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_issue_all_pages ON articles(zdb_id, year, month, day, issue);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_zdb_id_year ON articles(zdb_id, year);')

    conn.execute('COMMIT TRANSACTION')


@click.command()
@click.argument('ocr-db-sqlite', type=click.Path(exists=True))
@click.option('--sqlite-file', type=click.Path(exists=False), default=None)
@click.option('--json-file', type=click.Path(exists=False), default=None)
@click.option('--json-single-line-file', type=click.Path(exists=False), default=None)
@click.option('--processes', type=int, default=None, help="Number of parallel processes to be used. "
                                                          "(default all cores)")
def create_article_database(ocr_db_sqlite, sqlite_file, json_file, json_single_line_file, processes):
    """
    """

    with (sqlite3.connect(ocr_db_sqlite) as ocr_db):

        page_xmls = pd.read_sql("SELECT file, zdb_id, year, month, day, issue, page FROM ocr", con=ocr_db)

    df_zdb_meta = get_zdb_meta_data(page_xmls)

    def get_extraction_regions_tasks():

        with (sqlite3.connect(ocr_db_sqlite) as db):
            # noinspection PyShadowingNames
            for ((zdb_id, year, month, day, issue), issue_files) in (
                    page_xmls.groupby(['zdb_id', 'year', 'month', 'day', 'issue'])):
                issue_files = issue_files.sort_values("page")

                num_pages = issue_files.page.max()

                for _, (afile, apage) in issue_files[['file', 'page']].iterrows():

                    xml_data = pd.read_sql("SELECT xml_data FROM ocr "
                                           "WHERE zdb_id=? AND year=? AND month=? AND day=? AND issue=? AND page=?",
                                           params=(str(zdb_id), str(year), str(month), str(day), str(issue), str(apage)),
                                           con=db)

                    if len(xml_data) != 1:
                        print("ERRÖR!!")
                        continue

                    yield ExtractRegionsTask(afile, xml_data.iloc[0].xml_data, apage)

                yield NextArticle((zdb_id, year, month, day, issue, num_pages))


    articles = []
    regions=[]
    for state, result in tqdm(prun(get_extraction_regions_tasks(), processes=processes)):

        if state == "Regions":
            regions.append(result)
            continue

        if state == "NextArticle":
            zdb_id, year, month, day, issue, num_pages = result
            regions = pd.concat(regions)
            articles.append(identify_articles(regions, zdb_id, year, month, day, issue, num_pages))
            regions=[]
            continue

        if state is None:
            print("ERRÖR!!")
            continue

    articles = pd.concat(articles).reset_index(drop=True)

    print("{} articles found.".format(len(articles)))

    if sqlite_file is not None:

        with sqlite3.connect(sqlite_file) as con:

            setup_article_database(con)

            articles.to_sql("articles", con=con, if_exists="append")

    if json_file is None and json_single_line_file is None:
        return

    json_articles = []
    for _, (zdb_id, year, month, day, issue, start_page, end_page, article, num_pages, header, text) \
            in articles.iterrows():

        url=("https://content.staatsbibliothek-berlin.de/zefys/"
             "SNP{}-{}{:02d}{:02d}-{}-{}-0-0/full/full/0/default.jpg".
             format(zdb_id,year, month, day, issue-1,start_page))

        collection = df_zdb_meta.loc[zdb_id].iloc[0]

        j_art  =\
        {
            "title_txt_de": header,
            "text_txt_de": text,
            "id": "{}-{}-{:02d}-{:02d}-{}".format(collection, year, month, day, article-1),
            "book_id_s": "{}-{}-{:02d}-{:02d}".format(collection, year, month, day),
            "position_s" : str(start_page) + "-" + str(article),
            "hasModel_s": "article",
            "url_s": url,
            "collection_s": collection,
            "language_ss": ["german"],
            "issued_s": "{}-{:02d}-{:02d}".format(year, month, day),
            "noOfpages_s": str(num_pages),
            "month_s": "{}-{:02d}".format(year, month),
            "year_s": str(year),
            "decade_s": str(year/10*10)
        }

        json_articles.append(j_art)

    if json_file is not None:
        with open(json_file, "w", encoding="utf-8") as a_file:
            # noinspection PyTypeChecker
            json.dump(json_articles, a_file, ensure_ascii=False, indent=3)
    elif json_single_line_file is not None:
        with open(json_single_line_file, "w", encoding="utf-8") as a_file:
            for j_art in json_articles:
                a_file.write(json.dumps(j_art) + "\n")


def identify_articles(regions, zdb_id, year, month, day, issue, num_pages, strategy="type"):

    articles = []

    if strategy=="type":
        header = ""
        text = ""

        article=1
        start_page=None
        end_page=None
        for _, (aid, atype, atext, page, mean_center_x, mean_center_y, mean_width, mean_height,
                pos, region_ref) in regions.iterrows():

            if len(text) > 0 and atype=="header":  # never done in page start mode
                articles.append(
                    (zdb_id, year, month, day, issue, start_page, end_page, article, num_pages, header, text))
                header = ""
                text = ""
                article += 1
                start_page=None
                end_page=None

            if atype == "header":
                if start_page is None:
                    start_page=page

                end_page=page
                header += ("" if len(header)==0 else " ") + atext
            elif atype == "paragraph":
                if start_page is None:
                    start_page=page

                end_page = page
                text += ("" if len(text) == 0 else " ") + atext
            elif atype == "marginalia":
                pass
            else:
                raise RuntimeError("Unknown type: {}.".format(atype))

        if len(text) > 0 or len(header) > 0:
            articles.append((zdb_id, year, month, day, issue, start_page, end_page, article, num_pages, header, text))

    elif strategy=="height":
        pass

    return pd.DataFrame(articles, columns=["zdb_id", "year", "month", "day", "issue", "start_page", "end_page",
                                           "article", "num_pages", "header", "text"])
