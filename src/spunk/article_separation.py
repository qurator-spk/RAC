import io

import click
import os

import numpy as np
import pandas as pd
from sympy.vector.implicitregion import conic_coeff

from tqdm import tqdm
import re
import json
from fnmatch import fnmatch
import sqlite3
import zipfile

import requests
import urllib

from lxml import etree as ET
import xml.etree.ElementTree as ElementTree

from .parallel import run as prun

from pathlib import Path

from .zdb import get_zdb_meta_data  # , get_zdb_meta_dummy

import random as rnd
import string
from pprint import pprint

import shapely

from shapely.validation import explain_validity

has_next_part = {"article_head", "article_middle_part"}
has_prev_part = {"article_tail", "article_middle_part"}

valid_tags = {"article", "article_head", "article_middle_part", "article_tail", "heading", "advertisement",
              "page_header", "page_footer", "title_page_header", "title_page_footer", "obituary"}

valid_attributes = {"next_part", "prev_part"}

boolean_attributs = {"toc"}

sequence_starters = {"article", "article_head", "heading", "advertisement",
                     "page_header", "page_footer", "title_page_header", "title_page_footer", "obituary"}


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

    for num, coords_elem in (
            enumerate(root.iter('{http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15}Coords'))):

        if num > 0:
            print("Warning multiple coords!")

        points = coords_elem.attrib['points']

        yield points


def page_iterate_unicode(root):

    for text_elem in root.iter('{http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15}Unicode'):
        if text_elem.text is None:
            # print("No unicode!")
            continue

        yield text_elem.text


def str2polgon(points):

    x = [float(i) for i in points.replace(",", " ").split(" ")][0::2]
    y = [float(i) for i in points.replace(",", " ").split(" ")][1::2]

    points = [(a, b) for a, b in zip(x, y)]

    poly = shapely.Polygon(points)

    if not poly.is_valid:
        return poly.convex_hull
    else:
        return poly


def read_line_sequence(page_xml_file, page, is_start, sq_counter):

    parser = ET.XMLParser(encoding='UTF-8')
    tree = ElementTree.parse(page_xml_file, parser=parser)
    root = tree.getroot()

    order = page_get_reading_order(root)

    text_lines = list()

    for a_id, a_type, region_elem in page_iterate_text_regions(root):

        for line_number, line_elem in enumerate(page_iterate_text_lines(region_elem)):

            points = " ".join([p for p in page_iterate_coords(line_elem)])

            x = [int(i) for i in points.replace(",", " ").split(" ")][0::2]
            y = [int(i) for i in points.replace(",", " ").split(" ")][1::2]

            text = " ".join([tc for tc in page_iterate_unicode(line_elem)])

            if len(text) == 0:
                continue

            min_x = np.min(x)
            min_y = np.min(y)

            max_x = np.max(x)
            max_y = np.max(y)

            center_x = np.mean(x)
            center_y = np.mean(y)
            width = max(x) - min(x)
            height = max(y) - min(y)

            elem = (a_id, line_number, a_type, text, page, min_x, min_y, max_x, max_y, center_x, center_y, width, height, points)

            text_lines.append(elem)

    text_lines = pd.DataFrame(text_lines, columns=["id",  "line_number", "type", "text", "page", "min_x", "min_y",
                                                   "max_x", "max_y",
                                                   "mean_center_x", "mean_center_y", "mean_width", "mean_height",
                                                   "points"])

    text_lines = text_lines.merge(order, left_on="id", right_on="region_ref")

    text_lines = text_lines.sort_values(by=["pos", "line_number"], ascending=True).\
        drop(columns=['id', 'pos', 'region_ref'])

    text_lines['page_sequence_num'] = sq_counter

    return text_lines


@click.command()
@click.argument('gt_tsv_file', type=click.Path(exists=True))
@click.argument('out-file', type=click.Path())
def match_article_sequences(gt_tsv_file, out_file):
    gt = pd.read_csv(gt_tsv_file, sep="\t")

    page_sequence_counter = 0
    line_sequences = list()
    for idx, page_sequence_articles in tqdm(gt.groupby(["zdb", "year", "month", "day", "issue"])):

        polygon_lookup = dict()

        pages = page_sequence_articles[['xml_file', 'page']].drop_duplicates().\
            sort_values(by='page', ascending=True).\
            reset_index(drop=True)

        pages['page_sequence_start'] = pages.page.diff() != 1.0
        pages['page_sequence_num'] = page_sequence_counter + pages.page_sequence_start.cumsum()
        page_sequence_counter += pages.page_sequence_start.cumsum().max()

        if len(pages.loc[pages.page_sequence_num.isnull()]) > 0:
            import ipdb;ipdb.set_trace()

        line_sequence = pd.concat([read_line_sequence(xml_file, page, is_start, sq_counter)
                                   for _, (xml_file, page, is_start, sq_counter) in pages.iterrows()]).\
            reset_index(drop=True)

        for pidx, coords in page_sequence_articles[['coords']].iterrows():
            polygon_lookup[pidx] = str2polgon(coords.iloc[0])

        matching_info = list()
        for lidx, line_row in line_sequence.iterrows():

            line_polygon = str2polgon(line_row.points)

            matches = []
            for _, as_row in page_sequence_articles.loc[page_sequence_articles.page == line_row.page].iterrows():
                matches.append((as_row.name, shapely.intersection(polygon_lookup[as_row.name], line_polygon).area))

            matches = pd.DataFrame(matches, columns=["as_row", "area"])

            article_index = matches.as_row.iloc[matches.area.idxmax()]
            problematic = False
            if not matches.area.max() > 0.0:
                problematic = True

            match_score = matches.area.max()/line_polygon.area
            num_matches = len(matches.loc[matches.area > 0.0])

            matching_info.append((article_index, problematic, match_score, num_matches))

        matching_info = pd.DataFrame(matching_info,
                                     columns=["article_index", "problematic", "match_score", "num_matches"])

        line_sequence = pd.concat([line_sequence,
                                   page_sequence_articles.loc[matching_info.article_index].\
                                   drop(columns=['page']).\
                                   reset_index(drop=True),
                                   matching_info.drop(columns=['article_index'])], axis=1)

        line_sequences.append(line_sequence)

    line_sequences = pd.concat(line_sequences).reset_index(drop=True)

    line_sequences.to_csv(out_file, sep='\t')


def evaluate_tags(bid, body, url):
    creators = set()
    created = set()

    try:
        tag = None
        next_part = None
        prev_part = None
        is_toc = False

        spelling_map = {"aricle_tail": "article_tail", "artice": "article", "articl": "article",
                        "article_header": "article_head", "articl_head": "article_head",
                        "title_page_heade": "title_page_header",
                        "next_prt": "next_part", "nex_part": "next_part", "next_part.": "next_part",
                        "next_pat": "next_part",
                        "prv_part": "prev_part", "prev_part.": "prev_part", "pre_part": "prev_part",
                        "prev_post": "prev_part",
                        "headin": "heading",
                        "advertisment": "advertisement"}

        for elem in body:
            if elem["purpose"] != "tagging" and elem["value"] not in valid_tags:
                print("Skipping {}...".format(elem["purpose"]))
                continue

            value = elem["value"]

            creators.add(elem["creator"]["id"])
            created.add(elem["created"])

            if value in spelling_map:
                value = spelling_map[value]

            if value in valid_tags:
                if tag is None:
                    tag = value
                    continue

                if value == tag:
                    continue

                raise RuntimeError("Double tag!!")

            if value in boolean_attributs:
                if value == "toc":
                    is_toc = True

                continue

            if m := re.match("([^:]*)(:+)(.*)", value):

                attr, _, aid = m.groups()

            elif m := re.match("(.*)(.{8}-.{4}-.{4}-.{4}-.{10})", value):

                attr, aid = m.groups()
                # import ipdb;ipdb.set_trace()
            else:
                raise RuntimeError("Tag or attribute malformed!!")

            if attr in spelling_map:
                attr = spelling_map[attr]

            if attr not in valid_attributes:
                print("Unknown tag or attribute: {}".format(value))

            if aid == bid:
                print("Self-referencing tag {}({})".format(url, bid))
                continue

            if attr == "next_part":
                next_part = aid
                continue

            if attr == "prev_part":
                prev_part = aid
                continue

        if tag is None and is_toc:
            tag = "article"

        if tag is None:
            raise RuntimeError("No valid tag!!!")

        if tag in has_next_part and next_part is None:
            print("Tag requires next_part but does not have one!")
            next_part = "not_specified"

        if tag in has_prev_part and prev_part is None:
            print("Tag requires prev_part but does not have one!")
            prev_part = "not_specified"

        if tag not in has_next_part and next_part is not None:
            print("Tag does not require next_part but does have one!")

        if tag in has_prev_part and prev_part is None:
            print("Tag does not  require prev_part but does have one!")

        return (tag,
                next_part if next_part is not None else "not_specified",
                prev_part if prev_part is not None else "not_specified",
                ",".join(created), ",".join(creators))

    except RuntimeError as e:
        print("{} : {}({})".format(str(e), url, bid))

        print("Broken body: \n")

        pprint(body)

        print("\n")

        return "not_specified", "not_specified", "not_specified", ",".join(created), ",".join(creators)


def evaluate_coordinates(values):

    if m := re.match("xywh=pixel:(.*)", values):
        (coords,) = m.groups()

        x, y, width, height = (float(f) for f in coords.split(','))

        coords = [(x, y), (x+width, y), (x + width, y + height), (x, y+height)]

        coords = " ".join(["{},{}".format(x, y) for x, y in coords])

    elif m := re.match('<svg><polygon points="(.*)" /></svg>', values):
        coords, = m.groups()
    else:
        raise RuntimeError("Malformed coordinates!")

    return coords


@click.command()
@click.argument('w3c-anno-json', type=click.Path(exists=True))
@click.argument('out_tsv', type=click.Path(exists=False))
@click.argument('image_dir', type=click.Path(exists=True))
@click.argument('xml_dir', type=click.Path(exists=True))
@click.option('--check-only', type=bool, is_flag=True, default=False, help="")
def compile_article_separation_gt(w3c_anno_json, out_tsv, image_dir, xml_dir, check_only):

    image_dir = image_dir + "/" if not image_dir.endswith("/") else ""
    xml_dir = xml_dir + "/" if not xml_dir.endswith("/") else ""

    with open(w3c_anno_json) as fh:
        data = json.load(fh)

    df = pd.DataFrame([(data[i]["id"][1:],
                        data[i]['target']['source'],
                        evaluate_coordinates(data[i]['target']['selector']['value'])) +
                       evaluate_tags(data[i]["id"][1:], data[i]["body"], data[i]['target']['source'])
                       for i in range(0, len(data))],
                      columns=["id", "url", "coords", "tag", "next_part", "prev_part", "created", "creators"]).\
        set_index("id")

    for aid, row in df.loc[df.tag.isin(has_next_part) & (df.next_part == "not_specified")].iterrows():

        df_connected = df.loc[df.prev_part == aid]

        if len(df_connected) != 1:
            print("Cannot fix missing next_part in {}({}). Did not find any connected polygons.".\
                  format(row.url, aid))
            continue

        print("Fixing missing next_part in {}({})".format(row.url, aid))
        df.loc[aid, "next_part"] = df_connected.iloc[0]["prev_part"]

    for aid, row in df.loc[df.tag.isin(has_prev_part) & (df.prev_part == "not_specified")].iterrows():

        df_connected = df.loc[df.next_part == aid]

        if len(df_connected) != 1:
            print("Cannot fix missing prev_part in {}({}). Did not find any connected polygons.".\
                  format(row.url, aid))
            continue

        print("Fixing missing prev_part in {}({})".format(row.url, aid))
        df.loc[aid, "prev_part"] = df_connected.iloc[0]["next_part"]

    df[["zdb", "year", "month", "day", "issue", "page"]] =\
        df.url.str.extract("./SNP([^-]+)-(.{4})(.{2})(.{2})-(.{1})-(.{1}).")

    df[["year", "month", "day", "issue", "page"]] = df[["year", "month", "day", "issue", "page"]].astype(int)

    df["sequence_id"] = "unknown"
    df["sequence_num"] = -1

    df.loc[df.tag.isin(sequence_starters), "sequence_id"] = df.loc[df.tag.isin(sequence_starters)].index

    df.loc[~df.next_part.isin(df.index) & ~df.next_part.isin({"unknown", "not_specified"}), "next_part"] =\
        "not_specified"

    df.loc[~df.prev_part.isin(df.index) & ~df.prev_part.isin({"unknown", "not_specified"}), "prev_part"] = \
        "not_specified"

    # remove direct circular references
    df.loc[df.next_part == df.index, "next_part"] = "not_specified"
    df.loc[df.prev_part == df.index, "prev_part"] = "not_specified"

    def link_next(_aid, seq_id, done):

        df.loc[_aid, "sequence_num"] = len(done)

        if _aid in done:
            return

        done.add(_aid)

        if df.loc[_aid, "sequence_id"] == "unknown":
            df.loc[_aid, "sequence_id"] = seq_id

        if df.loc[_aid, "next_part"] not in {"unknown", "not_specified"}:
            link_next(df.loc[_aid, "next_part"], seq_id, done)

    def link_prev(_aid, seq_id, done):
        if _aid in done:
            return

        done.add(_aid)

        if df.loc[_aid, "sequence_id"] == "unknown":
            df.loc[_aid, "sequence_id"] = seq_id

        if df.loc[_aid, "prev_part"] not in {"unknown", "not_specified"}:
            link_prev(df.loc[_aid, "prev_part"], seq_id, done)

    for aid, row in df.loc[df.sequence_id != "unknown"].iterrows():
        link_next(aid, row.sequence_id, set())

    for aid, row in df.loc[df.sequence_id != "unknown"].iterrows():
        link_prev(aid, row.sequence_id, set())

    error_file = ".".join(w3c_anno_json.split(".")[0:-1]) + "-errors.md"

    print("Problematic annotations (see file {}): \n ".format(error_file))

    problematic = (df.sequence_id == "unknown") | (df.sequence_num == -1)

    df_error = df.loc[problematic].copy()
    df_error["url"] = df_error.url.map(
        lambda u: "http://article-separation.lx0246.sbb.spk-berlin.de/"
                  "region-annotator/region-annotator.html?image=" +
                  urllib.parse.quote(u, safe='/', encoding=None, errors=None))

    df_error[["url", "tag", "next_part", "prev_part", "creators"]].to_markdown(error_file)

    pprint(df.loc[df.sequence_id == "unknown"][["url", "tag", "next_part", "prev_part", "creators"]])

    print("\n\n")

    if check_only:
        return

    df = df.loc[~problematic].copy()

    print("Number of annotations: {}".format(len(df)))
    print("Number of article sequences: {}".format(len(df.sequence_id.unique())))

    df["image_file"] = image_dir + df.url.str.extract('.*/(SNP[0-9-X]+)/.*') + ".jpg"
    df["xml_file"] = xml_dir + df.url.str.extract('.*/(SNP[0-9-X]+)/.*') + ".xml"

    df.to_csv(out_tsv, sep="\t")

