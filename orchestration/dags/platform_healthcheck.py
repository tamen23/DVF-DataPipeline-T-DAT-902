"""Manual DAG that verifies the platform wiring:
Airflow scheduler -> Postgres (PostGIS) and the MinIO lake.
Trigger it from the UI after `make up` to prove the infra works.
"""
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator


def _check_lake() -> str:
    import os

    from minio import Minio

    client = Minio(
        os.environ["MINIO_ENDPOINT"].removeprefix("http://"),
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=False,
    )
    bucket = os.environ["LAKE_BUCKET"]
    if not client.bucket_exists(bucket):
        raise RuntimeError(f"lake bucket '{bucket}' not found")
    return f"bucket '{bucket}' reachable"


with DAG(
    dag_id="platform_healthcheck",
    description="Checks Postgres/PostGIS and the MinIO lake from Airflow",
    start_date=datetime(2026, 1, 1),
    schedule=None,  # manual trigger only
    catchup=False,
    tags=["infra"],
) as dag:
    check_postgis = SQLExecuteQueryOperator(
        task_id="check_postgis",
        conn_id="homepedia_postgres",
        sql="SELECT PostGIS_Version();",
    )

    check_lake = PythonOperator(
        task_id="check_lake",
        python_callable=_check_lake,
    )

    check_postgis >> check_lake
