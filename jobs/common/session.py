"""Spark session factory — wires S3A to the MinIO data lake.

Credentials/endpoint come from the environment (set in docker-compose.yml),
so the same job runs locally and on the VPS without change.
"""
import os

from pyspark.sql import SparkSession


def get_spark(app_name: str) -> SparkSession:
    endpoint = os.environ["MINIO_ENDPOINT"]
    return (
        SparkSession.builder.appName(app_name)
        .config("spark.hadoop.fs.s3a.endpoint", endpoint)
        .config("spark.hadoop.fs.s3a.access.key", os.environ["MINIO_ACCESS_KEY"])
        .config("spark.hadoop.fs.s3a.secret.key", os.environ["MINIO_SECRET_KEY"])
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config(
            "spark.hadoop.fs.s3a.aws.credentials.provider",
            "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
        )
        .getOrCreate()
    )


def lake_path(layer_and_key: str) -> str:
    """s3a:// path inside the lake bucket, e.g. lake_path('silver/dvf')."""
    return f"s3a://{os.environ['LAKE_BUCKET']}/{layer_and_key}"
