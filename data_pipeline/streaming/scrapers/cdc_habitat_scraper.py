from __future__ import annotations

"""
CDC Habitat — Caisse des Dépôts et Consignations Habitat
Source open data: https://www.data.gouv.fr/fr/organizations/cdc-habitat/

CDC Habitat publishes open datasets on social housing (logement social) on DataGouv.
This scraper fetches their latest datasets via the DataGouv API (no scraping needed —
they have a proper open data API).

Produces listings with: commune, type_logement, loyer, surface, nb_pieces
"""

from datetime import datetime, timezone
from typing import Iterator

import requests

from data_pipeline.streaming.scrapers.base_scraper import BaseScraper

# DataGouv API — organization CDC Habitat
DATAGOUV_ORG_API = "https://www.data.gouv.fr/api/1/organizations/cdc-habitat/datasets/?page_size=50"
DATAGOUV_DATASET_API = "https://www.data.gouv.fr/api/1/datasets/{dataset_id}/resources/"


class CdcHabitatScraper(BaseScraper):
    """
    Fetches CDC Habitat open datasets from DataGouv API.
    No scraping — uses the official DataGouv REST API.
    Returns social housing inventory records.
    """

    source = "cdc_habitat"
    base_delay = 1.0
    jitter = 0.5

    DATAGOUV_API = "https://www.data.gouv.fr/api/1"

    def _get_datasets(self) -> list[dict]:
        response = requests.get(
            f"{self.DATAGOUV_API}/organizations/cdc-habitat/datasets/",
            params={"page_size": 50},
            timeout=30,
            headers={"User-Agent": "homepedia/1.0"},
        )
        response.raise_for_status()
        return response.json().get("data", [])

    def _get_csv_resources(self, dataset_id: str) -> list[dict]:
        response = requests.get(
            f"{self.DATAGOUV_API}/datasets/{dataset_id}/resources/",
            timeout=30,
            headers={"User-Agent": "homepedia/1.0"},
        )
        response.raise_for_status()
        return [r for r in response.json().get("data", []) if r.get("format", "").lower() == "csv"]

    def _parse_csv_resource(self, url: str) -> Iterator[dict]:
        import csv
        import io

        response = requests.get(url, timeout=120, headers={"User-Agent": "homepedia/1.0"})
        response.raise_for_status()

        reader = csv.DictReader(io.StringIO(response.text), delimiter=";")
        for row in reader:
            row = {k.lower().strip(): v.strip() for k, v in row.items() if k}
            # Normalize common column names across CDC Habitat datasets
            code_col = next((k for k in row if "insee" in k or "commune" in k), None)
            loyer_col = next((k for k in row if "loyer" in k or "prix" in k), None)
            surface_col = next((k for k in row if "surface" in k or "shab" in k), None)
            type_col = next((k for k in row if "type" in k and "log" in k), None)

            if not code_col:
                continue

            try:
                listing = {
                    "listing_id": f"cdc_{hash(str(row))}",
                    "commune_code": str(row.get(code_col, "")).zfill(5),
                    "city": row.get("commune", row.get("libelle_commune", "")),
                    "property_type": row.get(type_col, "logement_social") if type_col else "logement_social",
                    "surface_m2": float(row[surface_col].replace(",", ".")) if surface_col and row.get(surface_col) else None,
                    "price": float(row[loyer_col].replace(",", ".")) if loyer_col and row.get(loyer_col) else None,
                    "price_m2": None,
                    "rooms": None,
                    "postal_code": row.get("code_postal"),
                    "url": url,
                }
                if listing["price"] and listing["surface_m2"] and listing["surface_m2"] > 0:
                    listing["price_m2"] = round(listing["price"] / listing["surface_m2"], 2)
                yield self._normalize(listing)
            except (ValueError, TypeError):
                continue

    def scrape(self, location: str = "", pages: int = 1) -> Iterator[dict]:
        """
        location is ignored — CDC Habitat data covers all of France.
        Fetches all available CSV datasets from their DataGouv organization.
        """
        print("Fetching CDC Habitat datasets from DataGouv API...")
        try:
            datasets = self._get_datasets()
            print(f"  Found {len(datasets)} datasets")

            for dataset in datasets:
                dataset_id = dataset.get("id")
                title = dataset.get("title", "")
                print(f"  Processing: {title}")

                try:
                    resources = self._get_csv_resources(dataset_id)
                    for resource in resources:
                        url = resource.get("url")
                        if url:
                            yield from self._parse_csv_resource(url)
                except Exception as e:
                    print(f"    [warn] Failed to process dataset {dataset_id}: {e}")
                    continue

        except Exception as e:
            print(f"  [error] CDC Habitat fetch failed: {e}")
