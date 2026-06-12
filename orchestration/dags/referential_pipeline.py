"""Referential pipeline: DDL -> bronze -> PostGIS.

Loads the commune / department / region referential (the spine every other
dataset joins onto). Manual trigger; re-running is safe (upserts).
"""
import sys
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator

sys.path.insert(0, "/opt/airflow/ingestion")


def _download():
    from downloaders import referential

    referential.download_to_bronze()


def _load():
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    from downloaders import referential

    conn = PostgresHook(postgres_conn_id="homepedia_postgres").get_conn()
    try:
        referential.load_postgres(conn)
    finally:
        conn.close()


with DAG(
    dag_id="referential_pipeline",
    description="Commune/department/region referential -> bronze -> PostGIS",
    start_date=datetime(2026, 1, 1),
    schedule=None,  # manual trigger
    catchup=False,
    tags=["v1", "referential"],
    template_searchpath=["/opt/airflow/warehouse/migrations"],
) as dag:
    apply_ddl = SQLExecuteQueryOperator(
        task_id="apply_ddl",
        conn_id="homepedia_postgres",
        sql="001_referential.sql",
    )

    download_to_bronze = PythonOperator(
        task_id="download_to_bronze",
        python_callable=_download,
    )

    load_postgis = PythonOperator(
        task_id="load_postgis",
        python_callable=_load,
    )

    apply_ddl >> download_to_bronze >> load_postgis
