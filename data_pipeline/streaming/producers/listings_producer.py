from __future__ import annotations

"""
Kafka producer for real estate listings.
Runs scrapers on a schedule and pushes each listing as a JSON message to Kafka.

Usage:
  python -m data_pipeline.streaming.producers.listings_producer --source seloger --communes 75056 69123 31555
  python -m data_pipeline.streaming.producers.listings_producer --source leboncoin --communes 75001 69001
  python -m data_pipeline.streaming.producers.listings_producer --source cdc_habitat --communes Choisy-le-Roi
"""

import argparse
import json
import time

from kafka import KafkaProducer

from data_pipeline.streaming.kafka_config import KAFKA_BOOTSTRAP_SERVERS, SCRAPE_INTERVAL, TOPICS
from data_pipeline.streaming.scrapers.cdc_habitat_scraper import CdcHabitatScraper
from data_pipeline.streaming.scrapers.leboncoin_scraper import LeboncoinScraper
from data_pipeline.streaming.scrapers.seloger_scraper import SelogerScraper

SCRAPERS = {
    "seloger": SelogerScraper,
    "leboncoin": LeboncoinScraper,
    "cdc_habitat": CdcHabitatScraper,
}


def _make_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        acks="all",           # wait for all replicas to confirm
        retries=3,
        compression_type="gzip",
    )


def run_producer(source: str, communes: list[str], loop: bool = False) -> None:
    if source not in SCRAPERS:
        raise ValueError(f"Unknown source '{source}'. Choose from: {list(SCRAPERS)}")

    topic = TOPICS[source]
    interval = SCRAPE_INTERVAL[source]
    scraper = SCRAPERS[source]()
    producer = _make_producer()

    print(f"Producer started — source={source} topic={topic}")

    while True:
        total = 0
        for commune in communes:
            print(f"\nScraping {source} for commune {commune}...")
            try:
                for listing in scraper.scrape(location=commune):
                    key = f"{source}_{listing.get('listing_id', commune)}"
                    producer.send(topic, key=key, value=listing)
                    total += 1
            except Exception as e:
                print(f"  [error] {source}/{commune}: {e}")

        producer.flush()
        print(f"\n[{source}] Cycle complete — {total} listings sent to Kafka")

        if not loop:
            break

        print(f"Next cycle in {interval // 60} min...")
        time.sleep(interval)

    producer.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Kafka producer for real estate listings.")
    parser.add_argument("--source", required=True, choices=list(SCRAPERS))
    parser.add_argument("--communes", nargs="+", required=True, help="INSEE/postal codes (or commune names for cdc_habitat) to scrape.")
    parser.add_argument("--loop", action="store_true", help="Run continuously on a schedule.")
    args = parser.parse_args()
    run_producer(args.source, args.communes, loop=args.loop)


if __name__ == "__main__":
    main()
