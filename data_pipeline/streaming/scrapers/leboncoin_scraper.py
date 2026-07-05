from __future__ import annotations

import json
import re
from typing import Iterator

from bs4 import BeautifulSoup

from data_pipeline.streaming.scrapers.base_scraper import BaseScraper

_NEXT_DATA_RE = re.compile(r'"props":\s*\{')


class LeboncoinScraper(BaseScraper):
    source = "leboncoin"
    base_delay = 4.0
    jitter = 3.0

    # LeBonCoin API endpoint for real estate listings
    API_URL = "https://api.leboncoin.fr/api/adfinder/v1/search"

    # Category IDs for real estate
    CATEGORY_VENTE = "9"      # Ventes immobilières
    CATEGORY_LOCATION = "10"  # Locations

    def _api_payload(self, postal_code: str, page: int) -> dict:
        return {
            "filters": {
                "category": {"id": self.CATEGORY_VENTE},
                "location": {
                    "locations": [{"locationType": "city", "zipcode": postal_code}]
                },
                "keywords": {},
            },
            "limit": 35,
            "offset": (page - 1) * 35,
            "sort_by": "time",
            "sort_order": "desc",
        }

    def _extract_listing(self, raw: dict) -> dict | None:
        try:
            attrs = {a["key"]: a.get("value_label", a.get("values", [None])[0])
                     for a in raw.get("attributes", [])}

            price_list = raw.get("price", [])
            price = float(price_list[0]) if price_list else None
            surface_str = attrs.get("square", attrs.get("rooms_surface_area"))
            surface = float(str(surface_str).replace(",", ".")) if surface_str else None

            if not price or not surface:
                return None

            return {
                "listing_id": str(raw.get("list_id", "")),
                "price": price,
                "surface_m2": surface,
                "price_m2": round(price / surface, 2) if surface > 0 else None,
                "rooms": attrs.get("rooms"),
                "city": raw.get("location", {}).get("city"),
                "postal_code": raw.get("location", {}).get("zipcode"),
                "url": raw.get("url"),
                "property_type": attrs.get("real_estate_type"),
                "energy_class": attrs.get("energy_rate"),
            }
        except (ValueError, TypeError, ZeroDivisionError, KeyError):
            return None

    def scrape(self, location: str, pages: int = 5) -> Iterator[dict]:
        """
        location: postal code (e.g. '75001') or INSEE code
        LeBonCoin API uses postal codes, not INSEE codes.
        """
        page_success = False
        last_error = None
        for page in range(1, pages + 1):
            try:
                response = self.session.post(
                    self.API_URL,
                    json=self._api_payload(location, page),
                    headers={
                        **self.session.headers,
                        "Content-Type": "application/json",
                        "api_key": "ba0c2dad52b3585dde1d3678b9ea6c2e8ceaba7c",
                    },
                    timeout=30,
                )

                import time, random
                time.sleep(self.base_delay + random.uniform(0, self.jitter))

                if response.status_code != 200:
                    print(f"  [warn] LeBonCoin API returned {response.status_code}")
                    last_error = RuntimeError(f"HTTP {response.status_code}")
                    break

                page_success = True
                data = response.json()
                ads = data.get("ads", [])

                found = 0
                for ad in ads:
                    listing = self._extract_listing(ad)
                    if listing:
                        listing["commune_code"] = location
                        yield self._normalize(listing)
                        found += 1

                print(f"  LeBonCoin page {page}/{pages} — {found} listings")
                if len(ads) < 35:
                    break  # last page

            except Exception as e:
                last_error = e
                print(f"  [warn] LeBonCoin page {page} failed: {e}")
                continue
        if not page_success and last_error:
            raise RuntimeError(f"LeBonCoin inaccessible: {last_error}")
