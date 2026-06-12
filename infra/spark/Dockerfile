# 3.5.3 to match exactly the pyspark version pinned by the Airflow
# constraints file — Spark serialization breaks across patch versions
FROM apache/spark:3.5.3

# S3A connector so Spark can read/write the MinIO data lake
# (versions matched to the Hadoop 3.3.4 bundled with Spark 3.5.x)
USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && curl -fSL -o /opt/spark/jars/hadoop-aws-3.3.4.jar \
        https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar \
    && curl -fSL -o /opt/spark/jars/aws-java-sdk-bundle-1.12.262.jar \
        https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar \
    && curl -fSL -o /opt/spark/jars/postgresql-42.7.4.jar \
        https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.4/postgresql-42.7.4.jar \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

USER spark
