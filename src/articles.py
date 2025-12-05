import sqlite3
import io

import numpy as np
import click
import pandas as pd

from lxml import etree as ET

import xml.etree.ElementTree as ElementTree
import json

from tqdm import tqdm
from zefys import UnzipTask
from parallel import run as prun

from zdb import get_zdb_meta_data  # , get_zdb_meta_dummy
from zefys import apply_filter


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


class NextIssue:
    def __init__(self, meta):
        self._meta = meta

    def __call__(self, *args, **kwargs):
        return "NextIssue", self._meta


def extract_regions(page_xml_file, page):

    parser = ET.XMLParser(encoding='UTF-8')
    tree = ElementTree.parse(page_xml_file, parser=parser)
    root = tree.getroot()

    order = page_get_reading_order(root)

    regions = []

    for a_id, a_type, region_elem in page_iterate_text_regions(root):

        text = ''
        min_x = np.inf
        min_y = np.inf
        max_x = 0.0
        max_y = 0.0
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

            min_x = min(min_x, np.min(x))
            min_y = min(min_y, np.min(y))

            max_x = min(max_x, np.max(x))
            max_y = min(max_y, np.max(y))

            count += 1
            mean_center_x += np.mean(x)
            mean_center_y += np.mean(y)
            mean_width += max(x) - min(x)
            mean_height += max(y) - min(y)

            text = " ".join([text, text_content])

        if count > 0:

            mean_center_x, mean_center_y, mean_width, mean_height = (mean_center_x/count, mean_center_y/count,
                                                                     mean_width/count, mean_height/count)

            regions.append((a_id, a_type, text, page,
                            min_x, min_y, max_x, max_y,
                            mean_center_x, mean_center_y, mean_width, mean_height))

    regions = pd.DataFrame(regions, columns=["id", "type", "text", "page",
                                             "min_x", "min_y", "max_x", "max_y",
                                             "mean_center_x", "mean_center_y",
                                             "mean_width", "mean_height"])

    regions = regions.merge(order, left_on="id", right_on="region_ref")

    regions = regions.sort_values(by=["pos"], ascending=True).drop(columns=['id', 'pos', 'region_ref'])

    return regions


@click.command()
@click.argument('ocr-db-sqlite', type=click.Path(exists=True))
@click.argument('sqlite-file', type=click.Path(exists=False))
@click.option('--processes', type=int, default=None, help="Number of parallel processes to be used. "
                                                          "(default all cores)")
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
def create_article_database(ocr_db_sqlite, sqlite_file, processes,
                            zdb_id, year, start_year, stop_year, month, start_month, stop_month,
                            day, start_day, stop_day, issue, start_issue, stop_issue, page, start_page, stop_page):
    """
    """

    with (sqlite3.connect(ocr_db_sqlite) as ocr_db):

        page_xmls = pd.read_sql("SELECT file, zdb_id, year, month, day, issue, page FROM ocr", con=ocr_db)

        page_xmls.year = page_xmls.year.astype(int)
        page_xmls.month = page_xmls.month.astype(int)
        page_xmls.day = page_xmls.day.astype(int)
        page_xmls.issue = page_xmls.issue.astype(int)

        print("Read {} entries from {} ...".format(len(page_xmls), ocr_db_sqlite))

        page_xmls = apply_filter(page_xmls, "zdb_id", zdb_id, None, None)
        page_xmls = apply_filter(page_xmls, "year", year, start_year, stop_year)
        page_xmls = apply_filter(page_xmls, "month", month, start_month, stop_month)
        page_xmls = apply_filter(page_xmls, "day", day, start_day, stop_day)
        page_xmls = apply_filter(page_xmls, "issue", issue, start_issue, stop_issue)
        page_xmls = apply_filter(page_xmls, "page", page, start_page, stop_page)

        print("{} entries remain after filtering.".format(len(page_xmls)))

    if len(page_xmls) < 1:
        return

    def get_extraction_regions_tasks():

        with (sqlite3.connect(ocr_db_sqlite) as db):
            # noinspection PyShadowingNames
            for ((zdb_id, year, month, day, issue), issue_files) in (
                    page_xmls.groupby(['zdb_id', 'year', 'month', 'day', 'issue'])):
                issue_files = issue_files.sort_values("page")

                _num_pages = issue_files.page.max()

                for _, (afile, apage) in issue_files[['file', 'page']].iterrows():

                    xml_data = pd.read_sql("SELECT xml_data FROM ocr "
                                           "WHERE zdb_id=? AND year=? AND month=? AND day=? AND issue=? AND page=?",
                                           params=(str(zdb_id), str(year), str(month), str(day), str(issue), str(apage)),
                                           con=db)

                    if len(xml_data) != 1:
                        print("ERRÖR!!")
                        continue

                    yield ExtractRegionsTask(afile, xml_data.iloc[0].xml_data, apage)

                yield NextIssue((zdb_id, year, month, day, issue, _num_pages))

    def get_identify_articles_tasks():
        regions=[]
        for state, result in tqdm(prun(get_extraction_regions_tasks(), processes=processes)):

            if state == "Regions":
                if len(result) == 0:
                    continue

                regions.append(result)
                continue

            if state == "NextIssue":
                yield IdentifyArticlesTask(pd.concat(regions).reset_index(drop=True), *result)

                regions=[]
                continue

            if state is None:
                print("ERRÖR!!")
                continue

    if sqlite_file is not None:
        with sqlite3.connect(sqlite_file) as con:
            setup_article_database(con)

    with sqlite3.connect(sqlite_file) as con:

        setup_article_database(con)

        for issue_regions, issue_articles in prun(get_identify_articles_tasks(), processes=processes):

            max_rowid = con.execute("SELECT max(rowid) FROM articles;").fetchone()[0]
            max_rowid = max_rowid + 1 if max_rowid is not None else 1

            issue_articles.index += max_rowid
            issue_articles.article_id += max_rowid
            issue_regions.article_id += max_rowid

            issue_articles.to_sql("articles", con=con, if_exists="append")
            issue_regions.to_sql("regions", con=con, if_exists="append")
    return


def setup_article_database(conn):
    conn.execute('BEGIN EXCLUSIVE TRANSACTION')

    conn.execute('CREATE TABLE IF NOT EXISTS "articles" ('
                 '"index" INTEGER PRIMARY_KEY,  "zdb_id" TEXT,  '
                 '"year" INTEGER,  "month" INTEGER,  '
                 '"day" INTEGER,  "issue" INTEGER,  '
                 '"start_page" INTEGER,  "end_page" INTEGER,  '
                 '"article_id" INTEGER,  "num_pages" INTEGER);')

    conn.execute('CREATE INDEX IF NOT EXISTS idx_zdb ON articles(zdb_id);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_year ON articles(year);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_month ON articles(month);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_day ON articles(day);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_issue ON articles(issue);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_start_page ON articles(start_page);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_end_page ON articles(end_page);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_issue_all_pages ON articles(zdb_id, year, month, day, issue);')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_zdb_id_year ON articles(zdb_id, year);')

    conn.execute('CREATE TABLE IF NOT EXISTS "regions" ('
                 '"index" INTEGER,  "type" TEXT,  "text" TEXT,  "page" INTEGER,  "min_x" INTEGER,  "min_y" INTEGER,  '
                 '"max_x" REAL,  "max_y" REAL,  "mean_center_x" REAL,  "mean_center_y" REAL,  "mean_width" REAL,  '
                 '"mean_height" REAL,  "article_id" INTEGER,  "article_pos" INTEGER);')

    conn.execute('CREATE INDEX IF NOT EXISTS "ix_regions_index"ON "regions" ("index");')
    conn.execute('CREATE INDEX IF NOT EXISTS "ix_regions_article_id" ON "regions" ("article_id");')

    conn.execute('COMMIT TRANSACTION')


class IdentifyArticlesTask:
    def __init__(self, regions, zdb_id, year, month, day, issue, num_pages):
        self._regions = regions
        self._zdb_id, self._year, self._month, self._day, self._issue, self._num_pages = \
            (zdb_id, year, month, day, issue, num_pages)

    def __call__(self, *args, **kwargs):
        regions, issue_articles = identify_articles(self._regions, self._zdb_id, self._year, self._month, self._day,
                                                    self._issue, self._num_pages)
        return regions, issue_articles


def identify_articles(regions, zdb_id, year, month, day, issue, num_pages, strategy="type"):

    articles = []
    regions["article_id"] = 0
    regions["article_pos"] = 0

    if strategy == "type":
        article_id = 0
        article_pos = 0

        start_page=None
        end_page=None
        prev_type=None

        for region_index, (atype, page) in regions[['type', 'page']].iterrows():

            if atype != "header" and atype != "paragraph":
                continue

            if prev_type == "paragraph" and atype=="header":
                articles.append((zdb_id, year, month, day, issue, start_page, end_page, article_id, num_pages))
                article_pos = 0
                article_id += 1
                start_page=None

            prev_type=atype
            regions.loc[region_index, "article_id"] = article_id
            regions.loc[region_index, "article_pos"] = article_pos
            article_pos += 1

            if start_page is None:
                start_page = page
            end_page = page

        if start_page is not None:
            articles.append((zdb_id, year, month, day, issue, start_page, end_page, article_id, num_pages))

    elif strategy=="height":
        pass

    return regions, pd.DataFrame(articles, columns=["zdb_id", "year", "month", "day", "issue", "start_page", "end_page",
                                           "article_id", "num_pages"])


@click.command()
@click.argument('art-db-sqlite', type=click.Path(exists=True))
@click.option('--json-file', type=click.Path(exists=False), default=None, help="")
@click.option('--json-single-line-file', type=click.Path(exists=False), default=None)
@click.option('--zdb-json-meta-file', type=click.Path(), default=None)
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
def article_json_export(art_db_sqlite, json_file, json_single_line_file, zdb_json_meta_file,
                        zdb_id, year, start_year, stop_year, month, start_month, stop_month,
                        day, start_day, stop_day, issue, start_issue, stop_issue, page, start_page, stop_page):

    with sqlite3.connect(art_db_sqlite) as art_db:
        df_articles = pd.read_sql("SELECT article_id, zdb_id, year, month, day, issue, start_page, num_pages "
                                  "FROM articles", con=art_db)

        df_articles.year = df_articles.year.astype(int)
        df_articles.month = df_articles.month.astype(int)
        df_articles.day = df_articles.day.astype(int)
        df_articles.issue = df_articles.issue.astype(int)

        print("Read {} entries from {} ...".format(len(df_articles), art_db_sqlite))

        df_articles = apply_filter(df_articles, "zdb_id", zdb_id, None, None)
        df_articles = apply_filter(df_articles, "year", year, start_year, stop_year)
        df_articles = apply_filter(df_articles, "month", month, start_month, stop_month)
        df_articles = apply_filter(df_articles, "day", day, start_day, stop_day)
        df_articles = apply_filter(df_articles, "issue", issue, start_issue, stop_issue)
        df_articles = apply_filter(df_articles, "page", page, start_page, stop_page)

        print("{} entries remain after filtering.".format(len(df_articles)))

        df_zdb_meta = get_zdb_meta_data(df_articles, zdb_json_meta_file)
        # df_zdb_meta = get_zdb_meta_dummy(df_articles)

        sl_file = open(json_single_line_file, "a+", encoding="utf-8") if json_single_line_file is not None else None

        json_articles = []
        for (_, (article_id, zdb_id, year, month, day, issue, start_page, num_pages)) \
                in tqdm(df_articles.iterrows(), total=len(df_articles)):

            url = ("https://dfg-viewer.de/show/?set%5Bmets%5D=https://content.staatsbibliothek-berlin.de/zefys/"
                   "SNP{}-{}{:02d}{:02d}-{}-0-0-0.xml&tx_dlf[page]={}".
                       format(zdb_id, year, month, day, issue - 1, start_page))

            img_url = ("https://content.staatsbibliothek-berlin.de/zefys/"
                   "SNP{}-{}{:02d}{:02d}-{}-{}-0-0/full/full/0/default.jpg".
                   format(zdb_id, year, month, day, issue - 1, start_page))

            collection = df_zdb_meta.loc[zdb_id].iloc[0]

            df_regions = pd.read_sql("SELECT type, text, article_pos FROM regions WHERE article_id=?", con=art_db,
                                     params=(article_id,))

            header = " ".join(df_regions.loc[df_regions.type=="header"].\
                              sort_values(by="article_pos", ascending=True).text.tolist())

            text = " ".join(df_regions.loc[df_regions.type == "paragraph"].\
                              sort_values(by="article_pos", ascending=True).text.tolist())
            j_art = \
                {
                    "title_txt_de": header,
                    "text_txt_de": text,
                    "id": "{}-{}-{:02d}-{:02d}-{}".format(collection, year, month, day, article_id - 1),
                    "book_id_s": "{}-{}-{:02d}-{:02d}".format(collection, year, month, day),
                    "position_s": str(start_page) + "-" + str(article_id),
                    "hasModel_s": "article",
                    "url_s": url,
                    "image_url_s": img_url,
                    "collection_s": collection,
                    "language_ss": ["german"],
                    "issued_s": "{}-{:02d}-{:02d}".format(year, month, day),
                    "noOfpages_s": str(num_pages),
                    "month_s": "{}-{:02d}".format(year, month),
                    "year_s": str(year),
                    "decade_s": str(int(year/10)*10)
                }

            if sl_file is not None:
                sl_file.write(json.dumps(j_art) + "\n")

            if json_file is not None:
                json_articles.append(j_art)

        if sl_file is not None:
            sl_file.close()

        if json_file is None:
            return

        with open(json_file, "w", encoding="utf-8") as a_file:
            # noinspection PyTypeChecker
            json.dump(json_articles, a_file, ensure_ascii=False, indent=3)
