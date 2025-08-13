import click
import os

import numpy as np
import pandas as pd
from fontTools.ttLib.tables.S_V_G_ import doc_index_entry_format_0Size
from tqdm import tqdm


@click.command()
@click.argument('scan-images-file', type=click.Path(exists=True))
@click.argument('target-path', type=click.Path(exists=False))
@click.option('--zefys-prefix', type=str, default=None,
              help="")
@click.option('--zdb-id', type=str, multiple=True, default=None,
              help="")
@click.option('--year', type=int, multiple=True, default=None,
              help="")
@click.option('--start-year', type=int, default=None,
              help="")
@click.option('--stop-year', type=int, default=None,
              help="")
@click.option('--month', type=int, multiple=True, default=None,
              help="")
@click.option('--start-month', type=int, default=None,
              help="")
@click.option('--stop-month', type=int, default=None,
              help="")
@click.option('--day', type=int, multiple=True, default=None,
              help="")
@click.option('--start-day', type=int, default=None,
              help="")
@click.option('--stop-day', type=int, default=None,
              help="")
@click.option('--issue', type=int, multiple=True, default=None,
              help="")
@click.option('--start-issue', type=int, default=None,
              help="")
@click.option('--stop-issue', type=int, default=None,
              help="")
@click.option('--page', type=int, multiple=True, default=None,
              help="")
@click.option('--start-page', type=int, default=None,
              help="")
@click.option('--stop-page', type=int, default=None,
              help="")
@click.option('--language', type=int, multiple=True, default=None,
              help="")
@click.option('--batch-size', type=int, default=None,
              help="")
@click.option('--start-batch', type=int, default=0,
              help="")
@click.option('--num-batches', type=int, default=None,
              help="")
def downloader(scan_images_file, target_path, zefys_prefix, zdb_id,
               year, start_year, stop_year,
               month, start_month, stop_month,
               day, start_day, stop_day,
               issue, start_issue, stop_issue,
               page, start_page, stop_page,
               language, batch_size, start_batch, num_batches):

    def apply_filter(df, column_name, values, start, stop):

        if start is not None and stop is not None:

            df = df.loc[(df[column_name] >= start) & (df[column_name] < stop)]

        elif len(values) > 0:
            df = df.loc[df[column_name].isin(values)]

        return df

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

    print("{} entries remain after filtering.".format(len(df_files)))

    print("Sorting ...")

    df_files = df_files.sort_values(by=['year', 'month', 'day', 'issue', 'page'])

    print("done.")

    def link_batch(batch, tpath):

        os.mkdir(tpath)

        for _, (fullpath, url, z, y, m, d, i, p, t) \
                in tqdm(batch[['fullpath', 'url', 'zdb', 'year', 'month', 'day', 'issue', 'page', 'type']].
                                iterrows(), total=len(df_files), desc="Creating symlinks "):

            file = zefys_prefix + fullpath

            if not os.path.exists(file):
                print("Warning! File {} does not exist!.".format(file))
                continue

            dest = "{}/{}-{}-{}-{}-{}-{}.{}".format(tpath, z, y, m, d, i, p, t)

            os.symlink(file, dest)

    if zefys_prefix is not None:
            if batch_size is None:
                link_batch(df_files, target_path)
            else:
                max_batches = int(np.ceil(len(df_files)/batch_size))
                print("max number of batches: {}".format(max_batches))

                num_batches = num_batches if start_batch + num_batches < max_batches else max_batches - start_batch

                for b in range(start_batch, num_batches):
                    link_batch(df_files.iloc[b*batch_size:(b+1)*batch_size, :],
                               "{}-batch-{}".format(target_path, b))
    else:
        pass

    pass
