from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator


PROJECT_DIR = "/opt/airflow/homepedia"
YEAR = "{{ dag_run.conf.get('year', 2022) }}"
DVF_INPUT = "{{ dag_run.conf.get('dvf_input', '/opt/airflow/input/dvf.csv') }}"


with DAG(
    dag_id="homepedia_dvf_pipeline",
    description="Raw to gold DVF pipeline for HOMEPEDIA.",
    start_date=datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["homepedia", "dvf", "real-estate"],
) as dag:
    ingest = BashOperator(
        task_id="ingest_dvf",
        bash_command=f"cd {PROJECT_DIR} && python -m data_pipeline.ingestion.ingest_dvf --input {DVF_INPUT} --year {YEAR}",
    )

    bronze = BashOperator(
        task_id="bronze_dvf",
        bash_command=f"cd {PROJECT_DIR} && python -m data_pipeline.transformation.bronze_dvf --year {YEAR}",
    )

    silver = BashOperator(
        task_id="silver_dvf",
        bash_command=f"cd {PROJECT_DIR} && python -m data_pipeline.cleaning.silver_dvf --year {YEAR}",
    )

    gold = BashOperator(
        task_id="gold_real_estate",
        bash_command=f"cd {PROJECT_DIR} && python -m data_pipeline.transformation.gold_real_estate --year {YEAR}",
    )

    quality = BashOperator(
        task_id="quality_checks",
        bash_command=f"cd {PROJECT_DIR} && python -m data_pipeline.quality_checks.check_gold --year {YEAR}",
    )

    ingest >> bronze >> silver >> gold >> quality

