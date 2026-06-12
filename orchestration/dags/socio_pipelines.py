"""Two small pipelines on the same rails: rents (Carte des loyers) and
socio-economic indicators (INSEE Filosofi). Both: DDL -> bronze -> Postgres.
"""
import sys
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator

sys.path.insert(0, "/opt/airflow/ingestion")


def _pg_conn():
    from airflow.providers.postgres.hooks.postgres import PostgresHook

    return PostgresHook(postgres_conn_id="homepedia_postgres").get_conn()


def _make(dag_id: str, description: str, module_name: str, tags: list[str]) -> DAG:
    def _download():
        import importlib

        module = importlib.import_module(f"downloaders.{module_name}")
        module.download_to_bronze()

    def _load():
        import importlib

        module = importlib.import_module(f"downloaders.{module_name}")
        conn = _pg_conn()
        try:
            module.load_postgres(conn)
        finally:
            conn.close()

    dag = DAG(
        dag_id=dag_id,
        description=description,
        start_date=datetime(2026, 1, 1),
        schedule=None,  # manual trigger
        catchup=False,
        tags=tags,
        template_searchpath=["/opt/airflow/warehouse/migrations"],
    )
    with dag:
        ddl = SQLExecuteQueryOperator(
            task_id="apply_ddl",
            conn_id="homepedia_postgres",
            sql="003_socio_tables.sql",
        )
        download = PythonOperator(task_id="download_to_bronze", python_callable=_download)
        load = PythonOperator(task_id="load_postgres", python_callable=_load)
        ddl >> download >> load
    return dag


loyers_dag = _make(
    "loyers_pipeline",
    "Carte des loyers: rent €/m² per commune -> gold.loyers_commune",
    "loyers",
    ["v1", "loyers"],
)

filosofi_dag = _make(
    "insee_filosofi_pipeline",
    "INSEE Filosofi: median income & poverty per commune -> gold.filosofi_commune",
    "insee_filosofi",
    ["v1", "insee"],
)
