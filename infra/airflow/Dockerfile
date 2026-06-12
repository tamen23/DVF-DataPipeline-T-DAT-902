# Python 3.10 to match the Python shipped in the apache/spark image
# (PySpark requires the same minor version on driver and executors)
FROM apache/airflow:2.10.4-python3.10

# Java is required by spark-submit (client mode driver runs in this container)
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends default-jre-headless procps \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/default-java

USER airflow
COPY requirements.txt /requirements.txt
# the official constraints file pins provider versions known to work with
# this exact Airflow release — without it pip's resolver backtracks forever
RUN pip install --no-cache-dir -r /requirements.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.4/constraints-3.10.txt"
