import click
import pandas as pd
import numpy as np
import re

from tqdm import tqdm

import sqlite3

from pprint import pprint

from transformers import pipeline, AutoModelForCausalLM, AutoTokenizer, AutoModelForSeq2SeqLM

from summary_prompts import prompts, prompt_BASIC_1_S_EN

from zefys import apply_filter

import torch


# noinspection PyTypeChecker
@click.command()
@click.argument('art-db-sqlite', type=click.Path(exists=True))
@click.argument('model_dir', type=click.Path(exists=True))
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
@click.option('--prompt', type=str, default="prompt_BASIC_1_S_EN",
              help="Prompt identifier (see summary_prompts.py). Default: prompt_BASIC_1_S_EN")
@click.option('--max-new-tokens', type=int, default=512, help="Maximum number of tokens per summary. "
                                                              "Default 512")
@click.option('--temperature', type=float, default=None, help="Randomness temperature for generation."
                                                              "Default is deterministic generation.")
@click.option('--random', is_flag=True, default=False, help="Specify this to randomly select articles f"
                                                            "or generation.")
def compute_summaries(art_db_sqlite, model_dir, zdb_id, year, start_year, stop_year, month, start_month, stop_month,
                      day, start_day, stop_day, issue, start_issue, stop_issue, page, start_page, stop_page, prompt,
                      max_new_tokens, temperature, random):

    # model_id = "openai/gpt-oss-20b"

    model = AutoModelForCausalLM.from_pretrained(
        model_dir,
        dtype="auto",
        device_map="cuda",
        # Flash Attention with Sinks
        # attn_implementation="kernels-community/vllm-flash-attn3",
    )

    tokenizer = AutoTokenizer.from_pretrained(model_dir)

    summary_pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        dtype="auto",
        device_map="cuda",
    )

    pfunc = prompts[prompt]

    with sqlite3.connect(art_db_sqlite) as art_db:
        art_db.execute('BEGIN EXCLUSIVE TRANSACTION')

        art_db.execute('CREATE TABLE IF NOT EXISTS "summaries" '
                       '("article_id" INTEGER, "prompt" TEXT, "model_dir" TEXT, "max_tokens" INTEGER, '
                       '"temperature" REAL, "summary" TEXT);')

        art_db.execute('CREATE INDEX IF NOT EXISTS idx_summary ON summaries(article_id, prompt, model_dir, max_tokens,'
                       'temperature);')

        art_db.execute('COMMIT TRANSACTION')

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

        if random:
            df_articles = df_articles.iloc[np.random.permutation(len(df_articles))].reset_index(drop=True)

        for (_, (article_id, zdb_id, year, month, day, issue, start_page, num_pages)) \
                in tqdm(df_articles.iterrows(), total=len(df_articles)):

            df_summary = pd.read_sql("SELECT * from summaries "
                                     "WHERE article_id=? AND prompt=? AND max_tokens=? AND model_dir=? "
                                     "AND temperature=?",
                                     params=(article_id, prompt, max_new_tokens, model_dir,
                                             0.0 if temperature is None else temperature),
                                     con=art_db)

            if len(df_summary) > 0:
                continue

            df_regions = pd.read_sql("SELECT type, text, article_pos FROM regions WHERE article_id=?", con=art_db,
                                     params=(article_id,))

            header = " ".join(df_regions.loc[df_regions.type == "header"].\
                              sort_values(by="article_pos", ascending=True).text.tolist())

            text = " ".join(df_regions.loc[df_regions.type == "paragraph"].\
                            sort_values(by="article_pos", ascending=True).text.tolist())

            if len(header) > 0:
                article = "{}:\n{}".format(header, text)
            else:
                article = text

            input_txt = pfunc(article)

            try:
                outputs = summary_pipe(
                    [input_txt],
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    do_sample=False
                )

                # import ipdb;ipdb.set_trace()

                summary = outputs[0]["generated_text"][-1]['content']
                summary = re.sub("^final", "", summary)

                art_db.execute('BEGIN EXCLUSIVE TRANSACTION')

                art_db.execute('INSERT INTO summaries(article_id, prompt, model_dir, max_tokens, temperature, summary)'
                               ' VALUES(?,?,?,?,?,?)', (article_id, prompt, model_dir, max_new_tokens,
                                                        0.0 if temperature is None else temperature, summary))
                art_db.execute('COMMIT TRANSACTION')
            except:
                print(article_id, len(article))
                pass

            torch.cuda.empty_cache()


@click.command()
@click.argument('model_dir', type=click.Path(exists=True))
def sum_test1(model_dir):
    from article_samples import article_2

    model = AutoModelForSeq2SeqLM.from_pretrained(
        model_dir,
        dtype="auto",
        device_map="cuda",

        # Flash Attention with Sinks
        # attn_implementation="kernels-community/vllm-flash-attn3",
    )

    tokenizer = AutoTokenizer.from_pretrained(model_dir)

    pipe = pipeline(
        task="summarization",
        model=model,
        tokenizer=tokenizer,
        dtype="auto",
        device_map="cuda",
        min_length=250,
        max_length=500
        # src_lang="de_XX",
        # tgt_lang="de_XX",
    )

    pprint(pipe(article_2))


# noinspection LanguageDetectionInspection
@click.command()
@click.argument('model_dir', type=click.Path(exists=True))
def sum_test(model_dir):
    from article_samples import article_1, article_2, article_3, article_4, article_5

    # model_id = "openai/gpt-oss-20b"

    model = AutoModelForCausalLM.from_pretrained(
        model_dir,
        dtype="auto",
        device_map="cuda",
        # Flash Attention with Sinks
        # attn_implementation="kernels-community/vllm-flash-attn3",
    )

    tokenizer = AutoTokenizer.from_pretrained(model_dir)

    pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        dtype="auto",
        device_map="cuda",
    )

    articles = [article_1, article_2, article_3, article_4, article_5]

    pfunc = prompt_BASIC_1_S_EN

    for ar in articles:

        messages = [
            pfunc(ar)
        ]

        outputs = pipe(
                    messages,
                    max_new_tokens=512,
                    temperature=None,
                    do_sample=False
                )

        # import ipdb;ipdb.set_trace()

        summary = outputs[0]["generated_text"][-1]['content']
        summary = re.sub("^final", "", summary)

        pprint("Zusammenfassung: \n" + summary)
        print("\n\n")
        pprint("Artikel: \n" + ar)
        print("========================================")
