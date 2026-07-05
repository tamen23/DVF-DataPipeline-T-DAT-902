from __future__ import annotations

"""
CDC Habitat — scraper du site cdc-habitat.fr
Utilise un POST pour la recherche (comme le form JS du site) afin d'obtenir
les annonces filtrées par commune via le JSON searchBootstrap embarqué.
"""

import json
import re
import time
from typing import Iterator

from data_pipeline.streaming.scrapers.base_scraper import BaseScraper

CDC_BASE = "https://www.cdc-habitat.fr"
CDC_SEARCH_URL = CDC_BASE + "/Recherche/show"
CDC_LOT_URL = CDC_BASE + "/annonces-immobilieres/{typage}"


class CdcHabitatScraper(BaseScraper):
    source = "cdc_habitat"
    base_delay = 1.0
    jitter = 0.5

    def scrape(self, location: str = "", postal_code: str = "", typage: str = "vente") -> Iterator[dict]:
        """
        Scrape les annonces CDC Habitat pour une commune via POST.
        location : nom de la commune (ex: "Choisy-le-Roi")
        postal_code : code postal (ex: "94600")
        typage : "vente" ou "location"
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            print("  [warn] beautifulsoup4 non installe -- pip install beautifulsoup4")
            return

        # Format canonique attendu par le site
        nom = location.upper().replace("-", " ")
        if postal_code:
            lieu = f"{nom} ({postal_code})"
        else:
            lieu = nom

        print(f"  CDC Habitat POST search: '{lieu}'")

        try:
            time.sleep(self.base_delay)
            resp = self.session.post(
                CDC_SEARCH_URL,
                data={"lbLieu": lieu, "cdTypage": typage, "nbLoyerMax": ""},
                headers={"Referer": CDC_BASE + "/Recherche/"},
                timeout=30,
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"  [warn] CDC Habitat inaccessible : {e}")
            return

        soup = BeautifulSoup(resp.text, "html.parser")

        # Extrait le JSON searchBootstrap embarqué dans le script
        bootstrap = None
        for s in soup.find_all("script"):
            src = s.string or ""
            m = re.search(r"var searchBootstrap = (\{.*?\});", src, re.DOTALL)
            if m:
                try:
                    bootstrap = json.loads(m.group(1))
                except json.JSONDecodeError:
                    continue
                break

        if not bootstrap:
            print("  [warn] CDC Habitat: searchBootstrap non trouve")
            return

        lots = bootstrap.get("lots", [])
        print(f"  CDC Habitat -> {len(lots)} annonces (hasLieu={bootstrap.get('hasLieu')})")

        # Recupere les cartes HTML pour enrichir les donnees
        cards = {self._card_key(c): c for c in soup.select(".residenceCard")}

        for lot in lots:
            try:
                listing = self._build_listing(lot, cards, location, postal_code, typage)
                if listing:
                    yield self._normalize(listing)
            except Exception:
                continue

    def _card_key(self, card) -> str:
        link = card.find("a", href=True)
        return link["href"] if link else ""

    def _build_listing(self, lot: dict, cards: dict, city: str, postal_code: str, typage: str) -> dict | None:
        id_lot = lot.get("id_lot", "")
        id_article = lot.get("id_article", "")
        lat = lot.get("latitude")
        lon = lot.get("longitude")

        # Prix depuis le JSON
        prix_str = lot.get("nb_prix", "").replace(" ", "").replace("\xa0", "")
        price = None
        try:
            price = float(prix_str) if prix_str else None
        except ValueError:
            pass

        # Cherche la carte HTML correspondante (contient surface, pieces, type)
        matching_card = None
        for href, card in cards.items():
            if id_lot in href or (id_article and id_article in href):
                matching_card = card
                break

        surface = None
        rooms = None
        property_type = "appartement"
        listing_url = CDC_BASE + f"/annonces-immobilieres/{typage}/{id_lot}"
        real_city = city

        if matching_card:
            text = matching_card.get_text(" ", strip=True).replace("\xa0", " ")

            surf_m = re.search(r"(\d+(?:[.,]\d+)?)\s*m[²2]", text)
            if surf_m:
                try:
                    surface = float(surf_m.group(1).replace(",", "."))
                except ValueError:
                    pass

            rooms_m = re.search(r"(\d+)\s*pi[eè]ce", text, re.IGNORECASE)
            if rooms_m:
                try:
                    rooms = int(rooms_m.group(1))
                except ValueError:
                    pass

            low = text.lower()
            if "maison" in low:
                property_type = "maison"
            elif "studio" in low:
                property_type = "studio"

            link = matching_card.find("a", href=True)
            if link:
                href = link["href"]
                listing_url = href if href.startswith("http") else CDC_BASE + href

            city_m = re.search(r"([A-Z][A-Z\-\s]+)\s*\(\d{5}\)", text)
            if city_m:
                real_city = city_m.group(1).strip().title()

        if price is None:
            return None

        price_m2 = None
        if price and surface and surface > 0:
            price_m2 = round(price / surface, 2)

        return {
            "listing_id": f"cdc_{id_lot}_{id_article}",
            "commune_code": postal_code,
            "city": real_city,
            "property_type": property_type,
            "surface_m2": surface,
            "price": price,
            "price_m2": price_m2,
            "rooms": rooms,
            "postal_code": postal_code,
            "latitude": float(lat) if lat else None,
            "longitude": float(lon) if lon else None,
            "url": listing_url,
        }
