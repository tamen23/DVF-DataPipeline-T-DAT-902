from __future__ import annotations

"""
Kafka consumer — reads listing messages from all source topics
and writes them to the bronze data lake as Parquet files.

Messages are batched (500 listings or 60 seconds, whichever comes first)
then flushed to bronze/listings/{source}/{date}/batch_{timestamp}.parquet

Runs as a long-lived service by default; pass --idle-timeout for batch-style
invocations that should exit once the topics have been quiet for N seconds.

Usage:
  python -m data_pipeline.streaming.consumers.bronze_consumer
  python -m data_pipeline.streaming.consumers.bronze_consumer --sources seloger leboncoin
  python -m data_pipeline.streaming.consumers.bronze_consumer --idle-timeout 120
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from kafka import KafkaConsumer

from data_pipeline.settings import file_path
from data_pipeline.streaming.kafka_config import (
    CONSUMER_GROUP,
    KAFKA_BOOTSTRAP_SERVERS,
    MONGO_COLLECTION,
    MONGO_DATABASE,
    MONGO_URL,
    TOPICS,
)

BATCH_SIZE = 500       # flush after this many messages
BATCH_TIMEOUT = 60     # flush after this many seconds even if batch not full


def _mongo_collection():
    """Optional NoSQL sink: raw listing JSON goes to MongoDB as well.

    Returns None (with a warning) when pymongo is missing or the server
    is unreachable — the Parquet bronze layer keeps working regardless.
    """
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        collection = client[MONGO_DATABASE][MONGO_COLLECTION]
        collection.create_index([("source", 1), ("listing_id", 1)])
        print(f"MongoDB connecte : {MONGO_URL} -> {MONGO_DATABASE}.{MONGO_COLLECTION}")
        return collection
    except ImportError:
        print("  [warn] pymongo non installé — archivage MongoDB désactivé (pip install pymongo)")
    except Exception as exc:
        print(f"  [warn] MongoDB injoignable ({exc}) — archivage MongoDB désactivé")
    return None


def _flush_batch(source: str, batch: list[dict], mongo=None) -> None:
    if not batch:
        return

    if mongo is not None:
        try:
            mongo.insert_many([dict(listing) for listing in batch], ordered=False)
        except Exception as exc:
            print(f"  [warn] insertion MongoDB échouée : {exc}")

    frame = pd.DataFrame(batch)
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    ts = int(now.timestamp())

    output = file_path(
        "bronze", "listings", source, date_str, f"batch_{ts}.parquet"
    )
    frame.to_parquet(output, index=False)
    print(f"  [{source}] Flushed {len(batch)} listings -> {output}")


def run_consumer(sources: list[str] | None = None, idle_timeout: int | None = None) -> None:
    topics_to_consume = (
        [TOPICS[s] for s in sources if s in TOPICS]
        if sources
        else list(TOPICS.values())
    )

    print(f"Consumer started — topics: {topics_to_consume}")

    consumer = KafkaConsumer(
        *topics_to_consume,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=CONSUMER_GROUP,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=True,
    )

    # One buffer per source
    buffers: dict[str, list[dict]] = defaultdict(list)
    last_flush = datetime.now(timezone.utc).timestamp()
    last_message = last_flush
    mongo = _mongo_collection()

    try:
        # poll() instead of iterating the consumer: iteration stops after a
        # timeout, but this service must keep running (and keep flushing on
        # the time trigger) even when the topics are quiet.
        while True:
            records = consumer.poll(timeout_ms=1000)
            for _, messages in records.items():
                for message in messages:
                    listing = message.value
                    source = listing.get("source", "unknown")
                    buffers[source].append(listing)

            now = datetime.now(timezone.utc).timestamp()
            if records:
                last_message = now
            elif idle_timeout and (now - last_message) >= idle_timeout:
                print(f"\nNo messages for {idle_timeout}s — exiting (idle timeout).")
                break
            should_flush = (
                any(len(batch) >= BATCH_SIZE for batch in buffers.values())
                or ((now - last_flush) >= BATCH_TIMEOUT and any(buffers.values()))
            )

            if should_flush:
                for src, batch in buffers.items():
                    _flush_batch(src, batch, mongo)
                buffers.clear()
                last_flush = now

    except KeyboardInterrupt:
        print("\nStopping consumer...")
    finally:
        # Flush remaining messages
        for src, batch in buffers.items():
            _flush_batch(src, batch, mongo)
        consumer.close()
        print("Consumer stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Kafka consumer — writes listings to bronze layer.")
    parser.add_argument("--sources", nargs="+", default=None, choices=list(TOPICS))
    parser.add_argument("--idle-timeout", type=int, default=None,
                        help="Exit after this many seconds without messages (default: run forever).")
    args = parser.parse_args()
    run_consumer(args.sources, idle_timeout=args.idle_timeout)


if __name__ == "__main__":
    main()
