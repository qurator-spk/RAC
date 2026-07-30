import io
import os.path

import click
import numpy as np
import pandas as pd

from tqdm import tqdm
import sqlite3
import zipfile

from lxml import etree as ET
import xml.etree.ElementTree as ElementTree

from .parallel import run as prun

from .zefys import apply_filter
from .article_separation import get_coords, psp

from pathlib import Path

import PIL
from PIL import Image, ImageDraw, ImageStat  # ImageOps, ImageFilter


def page_iterate_graph_regions(root):

    for region_elem in root.iter(f'{psp}ImageRegion'):

        the_id = region_elem.attrib['id']

        yield the_id, region_elem


class ScanImagesTask:

    def __init__(self, meta, xml_data):

        self._meta = meta
        self._xml_data = xml_data

    def __call__(self, *args, **kwargs):

        # noinspection PyBroadException
        try:
            xml_data = io.BytesIO(self._xml_data)

            with zipfile.ZipFile(xml_data, mode="r", compression=zipfile.ZIP_BZIP2) as zf:
                assert len(zf.filelist) == 1
                buffer = zf.read(name=zf.filelist[0].filename)

                parser = ET.XMLParser(encoding='UTF-8')
                tree = ElementTree.parse(io.BytesIO(buffer), parser=parser)

                graph_regions = list()
                for the_id, region in page_iterate_graph_regions(tree):

                    x, y, points, min_x, min_y, max_x, max_y, center_x, center_y, width, height = get_coords(region)

                    graph_regions.append((min_x, min_y, max_x, max_y))

                return self._meta, pd.DataFrame(graph_regions, columns=["x1", "y1", "x2", "y2"])

        except Exception as e:
            print(e)
            return self._meta, None


@click.command()
@click.argument('scan-images-file', type=click.Path(exists=True))
@click.argument('sqlite-file', type=click.Path(exists=True))
@click.argument('out-region-file', type=click.Path())
@click.option('--processes', type=int, default=None, help="Number of parallel processes to be used. "
                                                          "(default all cores)")
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
@click.option('--scan-images-separator', type=str, default='\t', help="")
@click.option('--zefys-prefix', type=str, default='/zefys/archive/', help="")
def scan_images_ocr_database(scan_images_file, sqlite_file, out_region_file, processes, dry_run,
                             zdb_id, year, start_year, stop_year, month, start_month, stop_month,
                             day, start_day, stop_day, issue, start_issue, stop_issue, page, start_page, stop_page,
                             scan_images_separator, zefys_prefix):
    """
    Scan an PAGE-XML OCR database for ImageRegion XML-Elements.
    Writes the region boundaries into a CSV file together with the image file and url.

    SCAN_IMAGES_FILE: The NFS image file list that was used for the OCR database creation (see zefys-scanner).


    SQLITE_FILE : The OCR database.


    OUT_REGION_FILE : Output CSV file.
    """

    df_files = pd.read_csv(scan_images_file, sep=scan_images_separator, low_memory=False).\
        rename(columns={"zdb": "zdb_id"})

    df_files.year = df_files.year.astype(int)
    df_files.month = df_files.month.astype(int)
    df_files.day = df_files.day.astype(int)
    df_files.issue = df_files.issue.astype(int)

    df_files = df_files.drop_duplicates(subset=["zdb_id", "year", "month", "day", "issue", "page"])
    
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

        print(f"{len(page_xmls)} entries remain after filtering.")

        print("Joining with scan files ...")

        page_xmls = page_xmls.merge(df_files, on=["zdb_id", "year", "month", "day", "issue", "page"])

        print(f"{len(page_xmls)} entries remain after join.")

        page_xmls = page_xmls[["id", "file", "fullpath", "url", "zdb_id", "year", "month", "day", "issue", "page"]]

        if dry_run:
            exit()

        def get_scan_tasks():
            with (sqlite3.connect(sqlite_file) as con):

                for _, (rowid, file, image_file, image_url, zdb_id, year, month, day, issue, page) in \
                        tqdm(page_xmls.iterrows(), total=len(page_xmls)):

                    data = pd.read_sql("SELECT xml_data FROM ocr WHERE rowid=?", con=con, params=(rowid,))

                    if len(data) != 1:
                        print("ERROR for rowid {}!".format(rowid))
                        continue
                    xml_data = data.iloc[0].xml_data

                    yield ScanImagesTask((file, image_file, image_url, zdb_id, year, month, day, issue, page),
                                         xml_data)

        write_header = ~os.path.exists(out_region_file)

        for meta, graph_regions in prun(get_scan_tasks(), processes=processes):

            if graph_regions is None or len(graph_regions) < 1:
                continue

            file, image_file, image_url, zdb_id, year, month, day, issue, page = meta

            graph_regions["zdb_id"] = zdb_id
            graph_regions["year"] = year
            graph_regions["month"] = month
            graph_regions["day"] = day
            graph_regions["issue"] = issue
            graph_regions["page"] = page
            graph_regions["image_file"] = zefys_prefix + image_file
            graph_regions["image_url"] = image_url

            graph_regions.to_csv(out_region_file, mode='a', index=False,
                                 header=write_header)

            write_header = False


class CropImagesTask:

    def __init__(self, image_file, regions, flat):

        self._image_file = image_file
        self._regions = regions
        self._flat = flat

    def __call__(self, *args, **kwargs):

        # noinspection PyBroadException
        try:
            img = Image.open(self._image_file).convert('RGB')

            for idx, (_,  (x1, y1, x2, y2, zdb_id, year, month, day, issue, page, image_file, image_url) )\
                    in \
                    enumerate(self._regions.iterrows()):

                target_file = f"{zdb_id}-{year}-{month}-{day}-{issue}-{page}-{idx}.jpeg"

                if self._flat:
                    target_path = "./"
                else:
                    target_path = f"./{zdb_id}/{year}/{month}/{day}/{issue}"

                    Path(target_path).mkdir(parents=True, exist_ok=True)

                target_file = f"{target_path}/{target_file}"

                img_region = img.crop((x1, y1, x2, y2))

                img_region.save(target_file, format="JPEG")

            return True

        except Exception as e:
            print(e)
            return False


@click.command()
@click.argument('image-region-file', type=click.Path())
@click.option('--processes', type=int, default=None, help="Number of parallel processes to be used. "
                                                          "(default all cores)")
@click.option('--flat', type=bool, is_flag=True, default=False, help="Do not create a directory structure.")
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
def crop_images(image_region_file, processes, flat, dry_run,
                   zdb_id, year, start_year, stop_year, month, start_month, stop_month,
                   day, start_day, stop_day, issue, start_issue, stop_issue, page, start_page, stop_page):
    """
    IMAGE_REGION_FILE : Image region CSV file (see scan-graph-regions-ocr-database).
    """

    df_image_regions = pd.read_csv(image_region_file, low_memory=False)

    df_image_regions.year = df_image_regions.year.astype(int)
    df_image_regions.month = df_image_regions.month.astype(int)
    df_image_regions.day = df_image_regions.day.astype(int)
    df_image_regions.issue = df_image_regions.issue.astype(int)

    df_image_regions = df_image_regions.drop_duplicates(subset=["zdb_id", "year", "month", "day", "issue", "page"])

    print(f"Read {len(df_image_regions)} entries from {image_region_file} ...")

    df_image_regions = apply_filter(df_image_regions, "zdb_id", zdb_id, None, None)
    df_image_regions = apply_filter(df_image_regions, "year", year, start_year, stop_year)
    df_image_regions = apply_filter(df_image_regions, "month", month, start_month, stop_month)
    df_image_regions = apply_filter(df_image_regions, "day", day, start_day, stop_day)
    df_image_regions = apply_filter(df_image_regions, "issue", issue, start_issue, stop_issue)
    df_image_regions = apply_filter(df_image_regions, "page", page, start_page, stop_page)

    print(f"{len(df_image_regions)} entries remain after filtering.")

    if dry_run:
        exit()

    num_image_files = len(df_image_regions.image_file.unique())

    print(f"Processing {num_image_files} unique image files ...")

    def get_crop_tasks():

        seq = tqdm(df_image_regions.groupby('image_file'), total=num_image_files)

        for image_file, regions in seq:

            seq.set_description(f"#:{len(regions)}")

            yield CropImagesTask(image_file, regions, flat)

    for _ in prun(get_crop_tasks(), processes=processes):
        pass
