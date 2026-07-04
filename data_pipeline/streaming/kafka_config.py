from __future__ import annotations

import os

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# One topic per data source — keeps messages isolated and replayable
TOPICS = {
    "seloger":         "homepedia.listings.seloger",
    "leboncoin":       "homepedia.listings.leboncoin",
    "cdc_habitat":     "homepedia.listings.cdc_habitat",
    "meilleursagents": "homepedia.prices.meilleursagents",
}

# Consumer group — all bronze consumers share the same group
CONSUMER_GROUP = "homepedia-bronze-writer"

# How long to wait between scrape cycles (seconds)
SCRAPE_INTERVAL = {
    "seloger":         3600,   # 1 hour
    "leboncoin":       1800,   # 30 min
    "cdc_habitat":     86400,  # 24 hours (less volatile)
    "meilleursagents": 86400,  # 24 hours
}
