
import click
import os

import numpy as np
import pandas as pd

from tqdm import tqdm
import re
import json
from fnmatch import fnmatch

import urllib

from lxml import etree as ET
import xml.etree.ElementTree as ElementTree

from pprint import pprint

import shapely

from shapely.validation import explain_validity
import uuid

from pprint import pprint

from .parallel import run as prun


has_next_part = {"article_head", "article_middle_part"}
has_prev_part = {"article_tail", "article_middle_part"}

valid_tags = {"article", "article_head", "article_middle_part", "article_tail", "heading", "advertisement",
              "page_header", "page_footer", "title_page_header", "title_page_footer", "obituary"}

valid_attributes = {"next_part", "prev_part"}

boolean_attributs = {"toc"}

sequence_starters = {"article", "article_head", "heading", "advertisement",
                     "page_header", "page_footer", "title_page_header", "title_page_footer", "obituary"}

spelling_map = {"aricle_tail": "article_tail", "artice": "article", "articl": "article",
                        "article_header": "article_head", "articl_head": "article_head",
                        "title_page_heade": "title_page_header",
                        "next_prt": "next_part", "nex_part": "next_part", "next_part.": "next_part",
                        "next_pat": "next_part",
                        "prv_part": "prev_part", "prev_part.": "prev_part", "pre_part": "prev_part",
                        "prev_post": "prev_part",
                        "headin": "heading",
                        "advertisment": "advertisement"}

psp = "{http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15}"


def page_get_reading_order(root):

    def traverse_ro(elem):
        if elem.tag == f"{psp}RegionRefIndexed":
            local_pos = int(elem.attrib['index'])
            region_ref = elem.attrib['regionRef']

            return pd.DataFrame([(local_pos, region_ref)], columns=["reading_order", "region_ref"])

        if elem.tag == f"{psp}OrderedGroup":
            return pd.concat([traverse_ro(child) for child in elem]).\
                sort_values(by="reading_order", ascending=True).\
                reset_index(drop=True)

        elif elem.tag == f"{psp}UnorderedGroup" or elem.tag == f"{psp}ReadingOrder":

            order = pd.concat([traverse_ro(child) for child in elem]).reset_index(drop=True)

            order = order.drop(columns=["reading_order"]).reset_index().rename(columns={"index": "reading_order"})

            return order
        else:
            raise RuntimeError("Unsupported RO tag.")

    reading_order = root.findall(f".//{psp}Page/{psp}ReadingOrder")

    ro = traverse_ro(reading_order[0])

    return ro


def page_iterate_text_regions(root):

    for region_elem in root.iter(f'{psp}TextRegion'):

        the_id = region_elem.attrib['id']

        if 'type' in region_elem.attrib:
            the_type = region_elem.attrib['type']
        elif the_id.startswith("TableCell_"):
            the_type = "table_cell"
        else:
            the_type = "paragraph"

        yield the_id, the_type, region_elem


def page_iterate_text_lines(root):

    for line_elem in root.iter(f'{psp}TextLine'):

        yield line_elem


def page_iterate_coords(root):

    for num, coords_elem in enumerate(root.findall(f'{psp}Coords')):

        if num > 0:
            print("Warning multiple coords!")

        points = coords_elem.attrib['points']

        yield points


def page_iterate_unicode(root):

    for text_elem in root.iter(f'{psp}Unicode'):
        if text_elem.text is None:
            # print("Warning no unicode!")
            continue

        yield text_elem.text


def get_coords(elem):
    points = " ".join([p for p in page_iterate_coords(elem)])

    x = [int(i) for i in points.replace(",", " ").split(" ")][0::2]
    y = [int(i) for i in points.replace(",", " ").split(" ")][1::2]

    min_x = np.min(x)
    min_y = np.min(y)

    max_x = np.max(x)
    max_y = np.max(y)

    center_x = np.mean(x)
    center_y = np.mean(y)
    width = max(x) - min(x)
    height = max(y) - min(y)

    return x, y, points, min_x, min_y, max_x, max_y, center_x, center_y, width, height


def str2polgon(points):

    try:
        x = [float(i) for i in points.replace(",", " ").split(" ")][0::2]
        y = [float(i) for i in points.replace(",", " ").split(" ")][1::2]
    except:
        return shapely.Polygon()

    points = [(a, b) for a, b in zip(x, y)]

    poly = shapely.Polygon(points)

    if not poly.is_valid:
        return poly.convex_hull
    else:
        return poly


# noinspection PyTypeChecker
def read_line_sequence(page_xml_file, page, is_start, sq_counter, return_regions=False, skip_empty_lines=False):

    parser = ET.XMLParser(encoding='UTF-8')
    tree = ElementTree.parse(page_xml_file, parser=parser)
    root = tree.getroot()

    try:
        order = page_get_reading_order(root)
    except:
        print(f"No reading order in file {page_xml_file}.")
        order = pd.DataFrame([], columns=["reading_order", "region_ref"])

    text_lines = list()
    text_regions = list()
    custom = list()

    for a_id, a_type, region_elem in page_iterate_text_regions(root):

        x, y, points, min_x, min_y, max_x, max_y, center_x, center_y, width, height = get_coords(region_elem)
        region_id = uuid.uuid4()

        text_regions.append((region_id, a_id, a_type, page, min_x, min_y, max_x, max_y, center_x,
                             center_y, width, height, points))

        for line_number, line_elem in enumerate(page_iterate_text_lines(region_elem)):

            x, y, points, min_x, min_y, max_x, max_y, center_x, center_y, width, height = get_coords(line_elem)

            text = " ".join([tc for tc in page_iterate_unicode(line_elem)])

            if skip_empty_lines and len(text) == 0:
                continue

            text_lines.append((region_id, a_id, line_number, a_type, text, page, min_x, min_y, max_x, max_y,
                               center_x, center_y, width, height, points))

            if 'custom' in line_elem.attrib:

                if m := re.match("readingOrder {index:([0-9]+);} structure {id:a([0-9]+); type:article;}",
                                 line_elem.attrib['custom']):

                    line_reading_order, article_id = m.groups()
                    custom.append((region_id, line_number, line_reading_order, f"{sq_counter}_{page}_{article_id}"))
                else:
                    # print(f"Custom attrib does not match {line_elem.attrib['custom']}. File: {page_xml_file}.")
                    pass

    text_regions = pd.DataFrame(text_regions, columns=["rid",  "region_ref", "type", "page",
                                                       "min_x", "min_y",
                                                       "max_x", "max_y",
                                                       "mean_center_x", "mean_center_y",
                                                       "mean_width", "mean_height",
                                                       "region_coords"])

    text_lines = pd.DataFrame(text_lines, columns=["rid", "region_ref", "line_number", "type", "text", "page",
                                                   "min_x", "min_y",
                                                   "max_x", "max_y",
                                                   "mean_center_x", "mean_center_y",
                                                   "mean_width", "mean_height",
                                                   "line_coords"])

    if len(custom) > 0:

        custom = pd.DataFrame(custom, columns=["rid", "line_number", "line_reading_order", "article_id"])

        text_regions = text_regions.merge(custom[['rid', 'article_id']], on="rid", how="left")

        no_article_id = text_regions.article_id.isnull()
        if no_article_id.sum() > 0:
            # print(f"Warning: {text_regions.article_id.isnull().sum()} regions do not have an article_id")
            text_regions.loc[no_article_id, "article_id"] = "unknown"

    # region_ref information is not permitted to leave this function!!!
    text_lines = text_lines.merge(order, on="region_ref", how="left").drop(columns=["region_ref"])
    text_regions = text_regions.merge(order, on="region_ref", how="left").drop(columns=["region_ref"])

    text_regions = text_regions.drop_duplicates().sort_values(by=["reading_order"]).reset_index(drop=True)

    out_of_order = text_regions.reading_order.isnull()
    if out_of_order.sum() > 0:
        # print(f"{out_of_order.sum()} text regions not in reading order.")
        text_regions.loc[out_of_order, "reading_order"] = -1

    out_of_order = text_lines.reading_order.isnull()
    if out_of_order.sum() > 0:
        # print(f"{out_of_order.sum()} text regions not in reading order.")
        text_lines.loc[out_of_order, "reading_order"] = -1

    text_lines = text_lines.sort_values(by=["reading_order", "line_number"], ascending=True).reset_index(drop=True)

    text_lines['page_sequence'] = sq_counter
    text_regions['page_sequence'] = sq_counter

    page_xml_file = os.path.basename(page_xml_file)
    text_lines['xml_file'] = page_xml_file
    text_regions['xml_file'] = page_xml_file

    text_lines['start_of_page_sequence'] = False
    text_lines.loc[0, "start_of_page_sequence"] = is_start

    if return_regions:
        return text_lines, text_regions

    return text_lines


@click.command()
@click.argument('article_tsv_file', type=click.Path(exists=True))
@click.argument('match_tsv_file', type=click.Path(exists=True))
def evaluate_matching_result(article_tsv_file, match_tsv_file):
    """
    Evaluate various aspects of an article separation - layout/ocr/reading order matching.
    """

    article_separation = pd.read_csv(article_tsv_file, sep='\t')

    num_pages = len(article_separation[['zdb', 'year', 'month', 'day', 'issue', 'page']].drop_duplicates())

    matching = pd.read_csv(match_tsv_file, sep='\t', low_memory=False)

    total_num_lines = len(matching)

    ro_len_per_file = matching[['xml_file', 'reading_order']].drop_duplicates().xml_file.value_counts()

    files_without_reading_order = list(ro_len_per_file.loc[ro_len_per_file == 1].index)

    if len(files_without_reading_order) > 0:
        print(f"{len(files_without_reading_order)} files do not have a reading order at all. "
              f"These will be completely dropped: ")
        pprint(files_without_reading_order)

    article_separation = article_separation.loc[~article_separation.xml_file.isin(files_without_reading_order)].copy().reset_index(drop=True)
    matching = matching.loc[~matching.xml_file.isin(files_without_reading_order)].copy().reset_index(drop=True)

    no_reading_order = (matching.reading_order == -1)

    matching = matching.loc[~no_reading_order].copy().reset_index()

    matching['prev_sequence_id'] = matching.shift(1).sequence_id

    matching['next_sequence_id'] = matching.shift(-1).sequence_id

    def compute_out_of_context(df_match):
        sequence_next_combis = pd.DataFrame([(sequence_id, next_sequence_id, len(tmp))
                                            for (sequence_id, next_sequence_id), tmp in
                                            df_match.groupby(['sequence_id', 'next_sequence_id'])],
                                            columns=["sid", "nid", "occ"])

        between_sequence_jumps = sequence_next_combis.loc[sequence_next_combis.sid != sequence_next_combis.nid]

        peseq = between_sequence_jumps.sid.value_counts()

        oocc = pd.DataFrame(peseq.value_counts()).\
            rename(columns={"count": "#articles"}).reset_index().rename(columns={"count": "#context switches"})

        return oocc, peseq

    art_pages = article_separation[['sequence_id', 'page']].drop_duplicates()

    match_art_pages = matching[['sequence_id', 'page']].drop_duplicates()

    multi_part_articles_on_one_page = article_separation.loc[article_separation[['sequence_id', 'page']].duplicated()].sequence_id.unique()

    num_multi_part_articles_on_one_page = len(multi_part_articles_on_one_page)

    out_of_context_changes, _ = compute_out_of_context(matching)

    mp_out_of_context_changes, per_sequence =\
        compute_out_of_context(matching.loc[matching.sequence_id.isin(multi_part_articles_on_one_page)])

    print("\033[1A<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
    print(f"Article separation file: {article_tsv_file}")
    print(f"Matching file: {match_tsv_file} (The article separation has been matched either against layout GT or against the "
          f"output of an Layout detection system.)")
    # noinspection PyUnresolvedReferences
    print(f"Ignoring {no_reading_order.sum()} lines in matching file (total number is: {total_num_lines}) "
          f"due to missing reading order for those lines.")

    print(f"\n\nNumber of pages in article-GT: {num_pages}")
    print(f"Number of page sequences in article-GT: {matching.page_sequence.max()}")
    print(f"Total number of articles in article-GT: {len(article_separation.sequence_id.unique())}")

    print("Single page articles vs multi-page articles. "
          "How many articles are located over multiple_pages:\n")
    print(pd.DataFrame(art_pages.sequence_id.\
                       value_counts().\
                       value_counts()).rename(columns={"count": "#articles"}).\
          reset_index().rename(columns={"count": "#pages"}).to_markdown(index=False))

    print("\nSingle page articles vs multi-page articles in matched layout. "
          "How many articles of the matched layout are located over multiple_pages:\n")
    print(pd.DataFrame(match_art_pages.sequence_id.\
                       value_counts().\
                       value_counts()).rename(columns={"count": "#articles"}). \
          reset_index().rename(columns={"count": "#pages"}).to_markdown(index=False))

    print(f"\nNumber of multi-part articles on one page: {num_multi_part_articles_on_one_page}\n")

    print("\nNumber of context changes when parsed in reading order per article:")
    print("\t #context switches==1: Article can be passed in one go according to reading order and is not interrupted "
          "by another article (desired result).")
    print("\n")
    print(out_of_context_changes.to_markdown(index=False))
    print(f"\nFor multi-part articles on one page (#{num_multi_part_articles_on_one_page}):\n")
    print(mp_out_of_context_changes.to_markdown(index=False))

    print(f"\n\nNumber of distinct article regions (polygons) in article-GT: {len(article_separation)}")
    print("\nDistribution of tags in article separation: ")

    print(pd.DataFrame(article_separation.tag.value_counts()).reset_index().to_markdown(index=False))

    print(f'\n\nNumber of text lines in XML files {len(matching)}')

    print("\nNumber of text regions with non-zero intersection per TextLine:")
    print("\t num_matches==1: TextLine intersects with exactly one text region (desired result).")
    print("\n")
    print(pd.DataFrame(matching.num_matches.value_counts()).reset_index().to_markdown(index=False))

    print("\n>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
          "\n\n\n\n")


# noinspection PyUnresolvedReferences
@click.command()
@click.argument('directory', type=click.Path(exists=True))
@click.argument('out-file', type=click.Path())
@click.option('--pattern', type=str, default="*.xml",
              help="Consider only XML-files that match this pattern. Default: *.xml.")
@click.option('--follow-symlinks', type=bool, is_flag=True, default=False,
              help="Follow symlinks while traversing the DIRECTORY.")
@click.option('--mode', type=click.Choice(['bnf', 'nlf']), default="bnf",
              help="File parse mode that defines how meta-data information is extracted from the filename - "
                   "if possible. Default: bnf")
def extract_article_separation(directory, out_file, pattern, follow_symlinks, mode):
    """
    A tool that extracts the article separation information
    from the PAGE-XML files of NLF and BnF datasets into a TSV-file (OUT_FILE)
    that describes one article polygon per line and in its entirety
    corresponds to the article polygon sequence of the dataset
    where the article polygons are the <TextRegions> in the XML-files.

    The XML-files to be processed are found by recursively parsing DIRECTORY.
    """

    def file_it(to_scan):
        for af in os.scandir(to_scan):
            try:
                if af.is_dir(follow_symlinks=follow_symlinks):
                    for g in file_it(af):
                        yield g
                else:
                    if not fnmatch(af.path, pattern):
                        continue
                    yield af.path
            except NotADirectoryError:
                continue

    _file_it = tqdm(file_it(directory))

    df = pd.DataFrame([(file,) for file in _file_it], columns=['xml_file'])

    if mode == "bnf":
        df[['year', 'month', 'day', 'issue', 'page']] = df.xml_file.str.extract("./(.{4})(.{2})(.{2})_(.{1})-(.{4}).")

        df["zdb"] = "XXXXXX"
    elif mode == "nlf":
        df[['fid', 'page', 'lid']] = df.xml_file.str.extract("./([0-9]+)_([0-9]+)_([0-9]+).")

        df['zdb'] = df.fid.astype(int)
        df['year'] = 0
        df['month'] = 0
        df['day'] = 0
        df['issue'] = 0
        df['page'] = df.page.astype(int)
    else:
        raise RuntimeError("Unknown filename parse mode.")

    print(f"Number of scanned XML files: {len(df)}")

    df = df.dropna()

    print(f"Number of scanned XML files that match filename convention: {len(df)}")

    if len(df) < 1:
        return

    df[['year', 'month', 'day', 'issue', 'page']] = df[['year', 'month', 'day', 'issue', 'page']].astype(int)

    group_columns = ['zdb', 'year', 'month', 'day', 'issue']

    page_sequence_counter = 0
    region_sequences = list()
    for group_index, group in tqdm(df.groupby(group_columns)):

        pages = group[['xml_file', 'page']].drop_duplicates(). \
            sort_values(by='page', ascending=True). \
            reset_index(drop=True)

        pages['page_sequence_start'] = pages.page.diff() != 1.0
        pages['page_sequence'] = page_sequence_counter + pages.page_sequence_start.cumsum()
        page_sequence_counter += pages.page_sequence_start.cumsum().max()

        pages = pages.sort_values(by='page')

        text_region_sequence = list()
        for _, row in pages.iterrows():
            _, text_regions =\
                read_line_sequence(row.xml_file, row.page, row.page_sequence_start, row.page_sequence,
                                   return_regions=True)

            text_regions['xml_file'] = os.path.basename(row.xml_file)
            text_regions[group_columns] = group_index
            text_region_sequence.append(text_regions)

        region_sequences.append(pd.concat(text_region_sequence).reset_index(drop=True))

    region_sequences = pd.concat(region_sequences).reset_index(drop=True)

    out_of_order = (region_sequences.reading_order == -1)

    print(f"Dropping {out_of_order.sum()} regions that do not appear in the reading order.")

    region_sequences = region_sequences.loc[~out_of_order]

    unknown_article = (region_sequences.article_id == "unknown")

    print(f"Dropping {unknown_article.sum()} regions due to unknown article_id")

    region_sequences = region_sequences.loc[~unknown_article]

    assert (len(region_sequences[['rid', 'article_id']].drop_duplicates()) == len(region_sequences[['rid',
                                                                                                    'article_id']]))

    articles_per_region = []
    for rid, grp in region_sequences.groupby('rid'):
        articles_per_region.append((rid, len(grp.article_id.unique())))

    articles_per_region = pd.DataFrame(articles_per_region, columns=["rid", "apr"])

    # noinspection PyUnresolvedReferences
    assert (articles_per_region.apr == 1).sum() == len(articles_per_region)

    region_sequences[['next_part']] = region_sequences[['rid']].shift(-1)
    region_sequences[['prev_part']] = region_sequences[['rid']].shift(1)

    sequences = region_sequences[['rid', 'article_id']].drop_duplicates(subset=['article_id'], keep='first').\
        rename(columns={'rid': 'sequence_id'}).reset_index(drop=True)

    region_sequences = region_sequences.merge(sequences, on="article_id").\
        rename(columns={'rid': 'id', 'region_coords': 'coords'}).\
        reset_index(drop=True)

    starters = region_sequences.article_id != region_sequences[['article_id']].shift(1).article_id

    ends = region_sequences.article_id != region_sequences[['article_id']].shift(-1).article_id

    assert len(region_sequences.article_id.unique()) == len(region_sequences.loc[starters].article_id.unique())
    assert len(region_sequences.article_id.unique()) == len(region_sequences.loc[ends].article_id.unique())

    region_sequences.loc[starters, 'prev_part'] = 'not_specified'
    region_sequences.loc[ends, 'next_part'] = 'not_specified'

    region_sequences['tag'] = "article_middle_part"
    region_sequences.loc[starters, 'tag'] = "article_head"
    region_sequences.loc[ends, 'tag'] = "article_tail"
    region_sequences.loc[starters & ends, 'tag'] = "article"

    region_sequences = region_sequences[['id', 'sequence_id', 'xml_file', 'coords', 'tag', 'next_part', 'prev_part',
                                         'zdb', 'year', 'month', 'day', 'issue', 'page']]

    print("Number of regions: {}".format(len(region_sequences)))
    print("Number of article sequences: {}".format(len(region_sequences.sequence_id.unique())))

    region_sequences.to_csv(out_file, sep='\t')


class MatchTask:

    polygon_lookup = dict()

    def __init__(self, line_coords, page_polygons):

        self._line_coords = line_coords
        self._page_polygons = page_polygons

    def __call__(self, *args, **kwargs):

        line_polygon = str2polgon(self._line_coords)

        matches = []
        for _, as_row in self._page_polygons.iterrows():
            matches.append((as_row.name,
                            shapely.intersection(MatchTask.polygon_lookup[as_row.name], line_polygon).area))

        matches = pd.DataFrame(matches, columns=["as_row", "area"])

        article_index = matches.as_row.iloc[matches.area.idxmax()]
        problematic = False if matches.area.max() > 0.0 else True
        match_score = matches.area.max() / line_polygon.area
        num_matches = len(matches.loc[matches.area > 0.0])

        return article_index, problematic, match_score, num_matches

    @staticmethod
    def initialize(article_coords):
        for ap_idx, (article_coords,) in article_coords.iterrows():
            MatchTask.polygon_lookup[ap_idx] = str2polgon(article_coords)


@click.command()
@click.argument('article_tsv_file', type=click.Path(exists=True))
@click.argument('xml_dir', type=click.Path(exists=True))
@click.argument('out-file', type=click.Path())
def match_article_sequences(article_tsv_file, xml_dir, out_file):
    """
    A tool that takes the article-polygon-sequence TSV files - obtained by either
    compile-article-separation-gt or extract-article-separation - as well as a
    directory (XML_DIR) with PAGE-XML files as inputs. For each text line in the PAGE-XML-
    files, the article polygon of largest intersection in the TSV file is determined. A
    matching-TSV file is produced, that corresponds to the <TextLine> sequence of
    the entire PAGE-XML input directory mapped to the TSV polygons, first order
    sorted by page sequence, second order sorted by page, and third order sorted by
    the reading order defined in the PAGE-XML files.
    """

    xml_dir = xml_dir if xml_dir.endswith('/') else xml_dir + "/"

    gt = pd.read_csv(article_tsv_file, sep="\t").rename(columns={'coords': 'article_coords'})

    page_sequence_counter = 0
    line_sequences = list()
    for idx, page_sequence_articles in tqdm(gt.groupby(["zdb", "year", "month", "day", "issue"]), leave=False):

        pages = page_sequence_articles[['xml_file', 'page']].drop_duplicates().\
            sort_values(by='page', ascending=True).\
            reset_index(drop=True)

        pages['page_sequence_start'] = pages.page.diff() != 1.0
        pages['page_sequence'] = page_sequence_counter + pages.page_sequence_start.cumsum()
        page_sequence_counter += pages.page_sequence_start.cumsum().max()

        assert len(pages.loc[pages.page_sequence.isnull()]) == 0

        line_sequence = pd.concat([read_line_sequence(xml_dir + xml_file, page, is_start, sq_counter)
                                   for _, (xml_file, page, is_start, sq_counter) in pages.iterrows()]).\
            reset_index(drop=True)

        # noinspection PyUnresolvedReferences
        # assert (line_sequence.text.str.len() == 0).sum() == 0

        matching_info = list()

        def get_matching_tasks():
            for _, (page, line_coords) in line_sequence[['page', 'line_coords']].iterrows():
                page_articles = page_sequence_articles.loc[page_sequence_articles.page == page]

                if len(page_articles) == 0:
                    continue

                yield MatchTask(line_coords, page_sequence_articles.loc[page_sequence_articles.page == page])

        for article_index, problematic, match_score, num_matches in \
                tqdm(prun(get_matching_tasks(), initializer=MatchTask.initialize,
                          initargs=(page_sequence_articles[['article_coords']],), processes=None),
                     total=len(line_sequence),
                     leave=False):

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


def evaluate_w3c_tags(bid, body, url):
    creators = set()
    created = set()

    try:
        tag = None
        next_part = None
        prev_part = None
        is_toc = False

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


# noinspection PyUnresolvedReferences
@click.command()
@click.argument('w3c-anno-json', type=click.Path(exists=True))
@click.argument('out_tsv', type=click.Path(exists=False))
@click.option('--check-only', type=bool, is_flag=True, default=False,
              help="Do not write TSV but output only consistency checks.")
def compile_article_separation_gt(w3c_anno_json, out_tsv, check_only):
    """
     A tool that compiles the W3C-JSON file into a tab separated
     value file (OUT_TSV) that describes one article polygon per line and in its entirety
     corresponds to the article polygon sequence of the dataset including all pages.

     The tool checks the annotations for consistency - as far as this can be done automatically -
     and writes errors to stdout.

     \b
     The W3C-JSON file has been created with the region annotation tool:
     https://github.com/qurator-spk/sbb_images/blob/6623081cd1b80864e6eca85ab4d7940f5045d1b8/doc/region-annotator.md
    """

    with open(w3c_anno_json) as fh:
        data = json.load(fh)

    df = pd.DataFrame([(data[i]["id"][1:],
                        data[i]['target']['source'],
                        evaluate_coordinates(data[i]['target']['selector']['value'])) +
                       evaluate_w3c_tags(data[i]["id"][1:], data[i]["body"], data[i]['target']['source'])
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
        df.url.str.extract("./SNP([^-]+)-(.{4})(.{2})(.{2})-(.{1})-([0-9]+).")

    df[["year", "month", "day", "issue", "page"]] = df[["year", "month", "day", "issue", "page"]].astype(int)

    df["sequence_id"] = "unknown"
    df["sequence_num"] = -1

    starters = df.tag.isin(sequence_starters) | ((df.tag == "article_tail") & (df.prev_part == "unknown"))
    df.loc[starters, "sequence_id"] = df.loc[starters].index

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

    df["xml_file"] = df.url.str.extract('.*/(SNP[0-9-X]+)/.*') + ".xml"

    df.to_csv(out_tsv, sep="\t")


@click.command()
@click.argument('w3c-anno-json', type=click.Path(exists=True))
@click.argument('target_dir', type=click.Path())
@click.option('--from-zefys', type=bool, is_flag=True, default=False, help="Special treatment for ZEFYS links.")
@click.option('--user', type=str, default=None, help="Username for basic auth.")
@click.option('--password', type=str, default=None, help="Password for basic auth")
def download_w3c_annotation_images(w3c_anno_json, target_dir, from_zefys, user, password):
    """
    Batch download of images referenced in a W3C-Annotation-JSON file (W3C-ANNO-JSON) and write them to TARGET_DIR.
    """

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


def _evaluate_matching_result(article_tsv_file, match_tsv_file):

    if not os.path.exists(article_tsv_file) or not os.path.exists(match_tsv_file):
        return None

    articles_sep = pd.read_csv(article_tsv_file, sep='\t')

    art_num_pages = len(articles_sep[['zdb', 'year', 'month', 'day', 'issue', 'page']].drop_duplicates())

    df = pd.read_csv(match_tsv_file, sep='\t', low_memory=False)

    matched_total_num_lines = len(df)

    ro_len_per_file = df[['xml_file', 'reading_order']].drop_duplicates().xml_file.value_counts()

    files_without_reading_order = list(ro_len_per_file.loc[ro_len_per_file == 1].index)

    articles_sep = articles_sep.loc[~articles_sep.xml_file.isin(files_without_reading_order)].copy().reset_index(drop=True)
    df = df.loc[~df.xml_file.isin(files_without_reading_order)].copy().reset_index(drop=True)

    matched_no_reading_order = (df.reading_order == -1)

    df = df.loc[~matched_no_reading_order].copy().reset_index()

    df['prev_sequence_id'] = df.shift(1).sequence_id

    df['next_sequence_id'] = df.shift(-1).sequence_id

    def compute_out_of_context(df_match):
        sequence_next_combis = pd.DataFrame([(sequence_id, next_sequence_id, len(tmp))
                                            for (sequence_id, next_sequence_id), tmp in
                                            df_match.groupby(['sequence_id', 'next_sequence_id'])],
                                            columns=["sid", "nid", "occ"])

        between_sequence_jumps = sequence_next_combis.loc[sequence_next_combis.sid != sequence_next_combis.nid]

        peseq = between_sequence_jumps.sid.value_counts()

        oocc =\
            pd.DataFrame(peseq.value_counts()).\
                rename(columns={"count": "#articles"}).\
                reset_index().\
                rename(columns={"count": "#context switches"})

        return oocc, peseq

    art_pages = articles_sep[['sequence_id', 'page']].drop_duplicates()

    matched_art_pages = df[['sequence_id', 'page']].drop_duplicates()

    multi_part_articles_on_one_page = articles_sep.loc[articles_sep[['sequence_id', 'page']].duplicated()].sequence_id.unique()

    num_multi_part_articles_on_one_page = len(multi_part_articles_on_one_page)

    matched_out_of_context_changes, _ = compute_out_of_context(df)

    matched_multi_part_on_one_page_out_of_context_changes, per_sequence =\
        compute_out_of_context(df.loc[df.sequence_id.isin(multi_part_articles_on_one_page)])

    articles_over_multiple_pages =\
        pd.DataFrame(art_pages.sequence_id.\
            value_counts().\
            value_counts()).\
            rename(columns={"count": "#articles"}).\
            reset_index().\
            rename(columns={"count": "#pages"})

    matched_articles_over_multiple_pages =\
        pd.DataFrame(matched_art_pages.sequence_id.\
            value_counts().\
            value_counts()).\
            rename(columns={"count": "#articles"}).\
            reset_index().\
            rename(columns={"count": "#pages"})

    matched_textline_intersection =\
        pd.DataFrame(df.num_matches.value_counts()).reset_index()

    tag_distribution = pd.DataFrame(articles_sep.tag.value_counts()).reset_index()

    return { 'art_name' : article_tsv_file,
             'ocr_name': match_tsv_file,
             'article_separation': articles_sep,
             'matched' : df,
             'num_pages': art_num_pages,
             'matched_total_num_lines': matched_total_num_lines,
             'files_without_reading_order': files_without_reading_order,
             'matched_no_reading_order': matched_no_reading_order,
             'art_pages': art_pages,
             'matched_art_pages': matched_art_pages,
             'multi_part_articles_on_one_page': multi_part_articles_on_one_page,
             'num_multi_part_articles_on_one_page': num_multi_part_articles_on_one_page,
             'matched_out_of_context_changes': matched_out_of_context_changes,
             'matched_multi_part_on_one_page_out_of_context_changes' : matched_multi_part_on_one_page_out_of_context_changes,
             'articles_over_multiple_pages': articles_over_multiple_pages,
             'matched_articles_over_multiple_pages': matched_articles_over_multiple_pages,
             'matched_textline_intersection': matched_textline_intersection,
             'tag_distribution': tag_distribution }

@click.command()
@click.option('--article-tsv-file', type=click.Path(exists=True), multiple=True, default=[])
@click.option('--match-tsv-file', type=click.Path(exists=True), multiple=True, default=[])
@click.option('--mode', type=click.Choice(['all', 'multi-part-one-page']), default="all",
              help="Perform RAC computation either for all articles or only for multi part articles that do not span "
                   "multiple pages.")
def compute_rac(article_tsv_file, match_tsv_file, mode):

    if len(article_tsv_file)< 1:
        print("You have to provide at least one article-tsv-file!.")
        return

    if len(match_tsv_file)< 1:
        print("You have to provide at least one match-tsv-file!.")
        return

    art_names = article_tsv_file
    match_names = match_tsv_file

    evaluation = dict()

    def _RAC(csw, total):
        rac = 0.0
        for num_sw, (count,) in csw.iterrows():
            rac += 1.0 / float(num_sw) * float(count)

        rac /= float(total)

        return rac

    def compute_out_of_context_table(res_key, total_key):

        columns = [('', '#context switches')]

        moocc = None
        for on, gtn in zip(match_names, art_names):
                columns.append((on, gtn))
                tmp = evaluation[(gtn, on)][res_key].copy().rename(columns={"#articles": f"{gtn}_{on}"})
                moocc = pd.DataFrame(tmp) if moocc is None else moocc.merge(tmp, on="#context switches", how="outer")

        moocc.columns = pd.MultiIndex.from_tuples(columns)

        moocc[moocc.isnull()] = 0.0
        moocc = moocc.astype(int)
        moocc[moocc == "0"] = '-'
        moocc = moocc.set_index(('', '#context switches'))
        moocc.index = moocc.index.rename('context switches')

        total_num = pd.DataFrame([], columns=moocc.columns)

        if total_key == 'article_separation':
            for c in moocc.columns:
                total_num.loc['total #articles', c] = len(evaluation[(c[1], c[0])]['article_separation'].sequence_id.unique())
        elif total_key == 'num_multi_part_articles_on_one_page':
            for c in moocc.columns:
                total_num.loc['total #articles', c] = evaluation[(c[1], c[0])]['num_multi_part_articles_on_one_page']

        RAC = pd.DataFrame([], columns=moocc.columns)

        for c in moocc.columns:
            RAC.loc['RAC', c] = round(_RAC(pd.DataFrame(moocc.loc[:, c]), total_num.loc['total #articles', c]),
                                      3)

        empty = pd.DataFrame([], columns=moocc.columns)
        empty.loc['context switches:', :] = ''

        moocc = pd.concat([total_num, RAC, empty, moocc])

        return moocc

    for art_tsv, ma_tsv in zip(article_tsv_file, match_tsv_file):
        evaluation[art_tsv, ma_tsv] = _evaluate_matching_result(art_tsv, ma_tsv)

    if mode == "all":
        moocc = compute_out_of_context_table('matched_out_of_context_changes', 'article_separation')

    else:
        moocc = compute_out_of_context_table('matched_multi_part_on_one_page_out_of_context_changes',
                                              'num_multi_part_articles_on_one_page')

    print(moocc)

