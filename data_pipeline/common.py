from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable

import pandas as pd


def normalize_column_name(name: str) -> str:
    value = unicodedata.normalize("NFKD", str(name))
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return value


def normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame.columns = [normalize_column_name(col) for col in frame.columns]
    return frame


def first_existing_column(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    available = set(columns)
    for candidate in candidates:
        if candidate in available:
            return candidate
    return None


def read_csv_flexible(path: Path, chunksize: int | None = None):
    options = {
        "sep": None,
        "engine": "python",
        "encoding": "utf-8",
        "on_bad_lines": "skip",
    }
    try:
        return pd.read_csv(path, chunksize=chunksize, **options)
    except UnicodeDecodeError:
        options["encoding"] = "latin1"
        return pd.read_csv(path, chunksize=chunksize, **options)


def to_numeric(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.replace(",", ".", regex=False).str.replace(" ", "", regex=False)
    cleaned = cleaned.replace({"nan": None, "None": None, "": None})
    return pd.to_numeric(cleaned, errors="coerce")

