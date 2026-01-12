def prompt_BASIC_1_S_EN(art):
    return {"role": "user",
            "content": "Generate a summary in German for the following article. "
                       "The summary should be around 2 to 3 sentences. "
                       ""
                       "Article: {}"
                       "Summary:".format(art)}


def prompt_BASIC_1_S_DE(art):
    return {"role": "user",
            "content": "Erstelle eine Zusammenfassung vom folgenden Artikel in 3 oder weniger Sätzen:"
                       ""
                       "Artikel: {}"
                       "Zusammenfassung:".format(art)}


def prompt_BASIC_5_EN(art):
    return {"role": "user",
            "content": "Summarize the article: {}".format(art)}


def prompt_BASIC_5_S_DE(art):
    return {"role": "user",
            "content": "Fasse den Artikel zusammen: {}".format(art)}


def prompt_BASIC_6_EN(art):
    return {"role": "user",
            "content": "Summarize the news article: {}".format(art)}


def prompt_BASIC_6_S_DE(art):
    return {"role": "user",
            "content": "Fassen Sie den Nachrichtenartikel zusammen: {}".format(art)}


def prompt_TL_DR(art):
    return {"role": "user",
            "content": "{}"
                       "TL;DR".format(art)}


def prompt_SEP_ONLY_S(art):
    return {"role": "user",
            "content": "{}"
                       "Zusammenfassung:".format(art)}


def prompt_BULLET_S_DE(art):
    return {"role": "user",
            "content": "Fassen Sie die wichtigsten Punkte des Artikels in Aufzählungspunkten zusammen."
                       "Artikel: {}"
                       "Zusammenfassung:".format(art)}


def prompt_ORIG_TONE_EN(art):
    return {"role": "user",
            "content": "Summarize the main points of the following text maintaining the original tone."
                       "{}".format(art)}


prompts = {"prompt_BASIC_1_S_EN": prompt_BASIC_1_S_EN,
           "prompt_BASIC_1_S_DE": prompt_BASIC_1_S_DE,
           "prompt_BASIC_5_EN": prompt_BASIC_5_EN,
           "prompt_BASIC_5_S_DE": prompt_BASIC_5_S_DE,
           "prompt_BASIC_6_EN": prompt_BASIC_6_EN,
           "prompt_BASIC_6_S_DE": prompt_BASIC_6_S_DE,
           "prompt_TL_DR": prompt_TL_DR,
           "prompt_SEP_ONLY_S": prompt_SEP_ONLY_S,
           "prompt_BULLET_S_DE": prompt_BULLET_S_DE,
           "prompt_ORIG_TONE_EN": prompt_ORIG_TONE_EN
           }
