import unicodedata


def normalize_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()
