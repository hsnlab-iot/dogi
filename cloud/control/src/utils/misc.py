from .translate import lang_short, lang_long, translate


def select_text(text_dict, language, do_translate=False):
    if lang_short(language) in text_dict:
        return text_dict[lang_short(language)]
    elif lang_long(language) in text_dict:
        return text_dict[lang_long(language)]

    # If exact language not found, try English version as fallback, with optional translation
    en = text_dict.get('en', None)
    if not do_translate:
        if en:
            return en
        else:
            return text_dict[next(iter(text_dict))]  # First item
    else:
        if en:
            return translate(en, "en", language)
        else:
            first_lang = next(iter(text_dict))
            first_item = text_dict[next(iter(text_dict))]  # First item
            return translate(first_item, first_lang, language)  # First item
