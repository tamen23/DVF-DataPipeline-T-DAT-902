from __future__ import annotations

import json
import re
from typing import Iterator

from bs4 import BeautifulSoup

from data_pipeline.streaming.scrapers.base_scraper import BaseScraper

# SeLoger structures its listing data as JSON-LD inside <script> tags
# This avoids parsing the full HTML layout which changes often
_JSONLD_RE = re.compile(r'application/ld\+json', re.IGNORECASE)


class SelogerScraper(BaseScraper):
    source = "seloger"
    base_delay = 3.0
    jitter = 2.0

    BASE_URL = "https://www.seloger.com/list.htm"

    # SeLoger type codes
    PROPERTY_TYPES = {
        "appartement": 1,
        "maison": 2,
    }

    def _build_url(self, location: str, page: int, property_type: int = 1) -> str:
        return (
            f"{self.BASE_URL}"
            f"?ci={location}"           # INSEE code
            f"&idtypebien={property_type}"
            f"&idtt=2"                   # 2 = sale
            f"&page={page}"
            f"&tri=d_dt_crea"           # newest first
        )

    def _parse_jsonld(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results = []
        for script in soup.find_all("script", type=_JSONLD_RE):
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    results.extend(data)
                else:
                    results.append(data)
            except (json.JSONDecodeError, TypeError):
                continue
        return results

    def _parse_next_data(self, html: str) -> list[dict]:
        """SeLoger also embeds data in __NEXT_DATA__ script tag."""
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find("script", id="__NEXT_DATA__")
        if not tag:
            return []
        try:
            data = json.loads(tag.string)
            props = data.get("props", {}).get("pageProps", {})
            listings = props.get("listings", props.get("results", []))
            return listings if isinstance(listings, list) else []
        except (json.JSONDecodeError, TypeError, AttributeError):
            return []

    def _extract_listing(self, raw: dict) -> dict | None:
        """Normalize a raw SeLoger listing dict."""
        try:
            price = raw.get("price", raw.get("prix"))
            surface = raw.get("surface", raw.get("surfaceArea"))
            rooms = raw.get("rooms", raw.get("nombreDePieces"))
            city = raw.get("city", raw.get("ville", raw.get("address", {}).get("addressLocality")))
            postal_code = raw.get("postalCode", raw.get("codePostal"))
            listing_id = str(raw.get("id", raw.get("idAnnonce", "")))
            url = raw.get("url", raw.get("lien", ""))

            if not price or not surface:
                return None

            price = float(str(price).replace(" ", "").replace("€", "").replace(",", "."))
            surface = float(str(surface).replace(",", ".").split("m")[0].strip())

            return {
                "listing_id": listing_id,
                "price": price,
                "surface_m2": surface,
                "price_m2": round(price / surface, 2) if surface > 0 else None,
                "rooms": int(rooms) if rooms else None,
                "city": city,
                "postal_code": str(postal_code) if postal_code else None,
                "url": url,
                "property_type": raw.get("type", raw.get("typeBien")),
            }
        except (ValueError, TypeError, ZeroDivisionError):
            return None

    def scrape(self, location: str, pages: int = 5) -> Iterator[dict]:
        """
        location: INSEE commune code (e.g. '75056' for Paris)
        """
        for page in range(1, pages + 1):
            url = self._build_url(location, page)
            try:
                response = self._get(url)
                raw_listings = self._parse_next_data(response.text)
                if not raw_listings:
                    raw_listings = self._parse_jsonld(response.text)

                found = 0
                for raw in raw_listings:
                    listing = self._extract_listing(raw)
                    if listing:
                        listing["commune_code"] = location
                        yield self._normalize(listing)
                        found += 1

                print(f"  SeLoger page {page}/{pages} — {found} listings")
                if found == 0:
                    break  # no more results

            except Exception as e:
                print(f"  [warn] SeLoger page {page} failed: {e}")
                continue
