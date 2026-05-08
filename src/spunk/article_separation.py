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

    for coords_elem in root.iter('{http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15}Coords'):

        points = coords_elem.attrib['points']

        yield points


def page_iterate_unicode(root):

    for text_elem in root.iter('{http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15}Unicode'):
        if text_elem.text is None:
            # print("No unicode!")
            continue

        yield text_elem.text


def text_line_sequence(xml_files, ):
    pass


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

        coords = [(x, y), (x+width, y), (x, y+height), (x + width, y + height)]

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

