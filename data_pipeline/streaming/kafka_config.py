from __future__ import annotations

import os

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

# MongoDB (base non-relationnelle) : le consumer bronze y archive les
# annonces JSON brutes en plus des fichiers Parquet.
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "homepedia")
MONGO_COLLECTION = "listings_raw"

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
