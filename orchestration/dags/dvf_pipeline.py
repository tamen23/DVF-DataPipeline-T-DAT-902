"""DVF pipeline: download -> bronze -> Spark silver -> Spark gold -> Postgres.

Years are controlled by the DVF_YEARS env var (comma-separated, default 2024).
Manual trigger; bronze downloads are skipped when already in the lake.
"""
import os
import sys
from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator

sys.path.insert(0, "/opt/airflow/ingestion")

# driver side runs in this container (client mode): S3A + JDBC fetched once
# from Maven and cached; workers already have them baked in the image
SPARK_PACKAGES = ",".join(
    [
        "org.apache.hadoop:hadoop-aws:3.3.4",
        "com.amazonaws:aws-java-sdk-bundle:1.12.262",
        "org.postgresql:postgresql:42.7.4",
    ]
)

SPARK_ENV = {
    key: os.environ[key]
    for key in [
        "MINIO_ENDPOINT",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "LAKE_BUCKET",
        "POSTGRES_HOST",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    ]
}


def _download():
    from downloaders import dvf

    dvf.download_to_bronze()


with DAG(
    dag_id="dvf_pipeline",
    description="DVF sales: bronze -> silver -> gold indicators -> Postgres",
    start_date=datetime(2026, 1, 1),
    schedule=None,  # manual trigger
    catchup=False,
    tags=["v1", "dvf"],
    template_searchpath=["/opt/airflow/warehouse/migrations"],
) as dag:
    apply_ddl = SQLExecuteQueryOperator(
        task_id="apply_ddl",
        conn_id="homepedia_postgres",
        sql="002_gold_schema.sql",
    )

    download_to_bronze = PythonOperator(
        task_id="download_to_bronze",
        python_callable=_download,
    )

    silver = SparkSubmitOperator(
        task_id="spark_silver",
        conn_id="spark_default",
        application="/opt/airflow/jobs/silver/dvf_clean.py",
        packages=SPARK_PACKAGES,
        env_vars=SPARK_ENV,
        verbose=False,
    )

    gold = SparkSubmitOperator(
        task_id="spark_gold",
        conn_id="spark_default",
        application="/opt/airflow/jobs/gold/dvf_indicators.py",
        packages=SPARK_PACKAGES,
        env_vars=SPARK_ENV,
        verbose=False,
    )

    apply_ddl >> download_to_bronze >> silver >> gold
