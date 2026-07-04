from __future__ import annotations

import os
from contextlib import contextmanager

from pyhive import hive

HIVE_HOST = os.getenv("HIVE_HOST", "localhost")
HIVE_PORT = int(os.getenv("HIVE_PORT", "10000"))
HIVE_DATABASE = os.getenv("HIVE_DATABASE", "homepedia")
HIVE_USERNAME = os.getenv("HIVE_USERNAME", "hive")


def get_connection() -> hive.Connection:
    return hive.connect(
        host=HIVE_HOST,
        port=HIVE_PORT,
        database=HIVE_DATABASE,
        username=HIVE_USERNAME,
        auth="NOSASL",
    )


@contextmanager
def get_db():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        yield cursor
    finally:
        cursor.close()
        conn.close()


def execute_query(query: str, params: dict | None = None) -> list[dict]:
    """Execute a HiveQL query and return results as list of dicts."""
    with get_db() as cursor:
        cursor.execute(query)
        columns = [col[0].split(".")[-1] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
