"""HOMEPEDIA — home page. For now: platform status check."""
import os

import requests
import streamlit as st

st.set_page_config(page_title="HOMEPEDIA", page_icon="🏠", layout="wide")

st.title("🏠 HOMEPEDIA")
st.caption("Housing Market Intelligence Platform for France")

st.header("Platform status")


def check_postgres() -> str:
    import psycopg2

    conn = psycopg2.connect(
        host=os.environ["POSTGRES_HOST"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ["POSTGRES_DB"],
        connect_timeout=3,
    )
    with conn.cursor() as cur:
        cur.execute("SELECT PostGIS_Version();")
        version = cur.fetchone()[0]
    conn.close()
    return f"PostGIS {version}"


def check_mongo() -> str:
    from pymongo import MongoClient

    client = MongoClient(os.environ["MONGO_URI"], serverSelectionTimeoutMS=3000)
    info = client.server_info()
    return f"MongoDB {info['version']}"


def check_minio() -> str:
    from minio import Minio

    client = Minio(
        os.environ["MINIO_ENDPOINT"],
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=False,
    )
    buckets = [b.name for b in client.list_buckets()]
    return f"buckets: {', '.join(buckets)}"


def check_spark() -> str:
    resp = requests.get(os.environ["SPARK_MASTER_UI"] + "/json/", timeout=3)
    data = resp.json()
    return f"{data['status']} — {len(data['workers'])} worker(s) alive"


checks = {
    "PostgreSQL + PostGIS": check_postgres,
    "MongoDB": check_mongo,
    "MinIO (data lake)": check_minio,
    "Spark cluster": check_spark,
}

cols = st.columns(len(checks))
for col, (name, fn) in zip(cols, checks.items()):
    with col:
        try:
            detail = fn()
            st.success(f"**{name}**\n\n{detail}")
        except Exception as exc:  # noqa: BLE001 — show any failure on the dashboard
            st.error(f"**{name}**\n\nunreachable: {exc}")
