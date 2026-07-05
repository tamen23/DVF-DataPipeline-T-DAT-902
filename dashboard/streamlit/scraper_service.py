from __future__ import annotations

"""
Service de récupération d'annonces pour Streamlit.
Tente SeLoger + LeBonCoin, fallback sur CDC Habitat si bloqué.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from data_pipeline.streaming.scrapers.seloger_scraper import SelogerScraper
from data_pipeline.streaming.scrapers.leboncoin_scraper import LeboncoinScraper
from data_pipeline.streaming.scrapers.cdc_habitat_scraper import CdcHabitatScraper



def _fetch_seloger(code_commune: str, pages: int) -> tuple[list[dict], str | None]:
    try:
        scraper = SelogerScraper()
        listings = []
        for listing in scraper.scrape(location=code_commune, pages=pages):
            listings.append({**listing, "source": "SeLoger"})
        if not listings:
            return [], "SeLoger n'a retourné aucune annonce pour cette commune."
        return listings, None
    except Exception as e:
        return [], f"SeLoger bloqué : {e}"


def _fetch_leboncoin(postal_code: str, pages: int) -> tuple[list[dict], str | None]:
    try:
        scraper = LeboncoinScraper()
        listings = []
        for listing in scraper.scrape(location=postal_code, pages=pages):
            listings.append({**listing, "source": "LeBonCoin"})
        if not listings:
            return [], "LeBonCoin n'a retourné aucune annonce pour cette commune."
        return listings, None
    except Exception as e:
        return [], f"LeBonCoin bloqué : {e}"


def _fetch_cdc(nom_commune: str, postal_code: str, typage: str = "vente") -> tuple[list[dict], str | None]:
    try:
        scraper = CdcHabitatScraper()
        listings = [
            {**l, "source": "CDC Habitat"}
            for l in scraper.scrape(location=nom_commune, postal_code=postal_code, typage=typage)
        ]
        return listings, None
    except Exception as e:
        return [], f"CDC Habitat erreur : {e}"


def fetch_listings(
    code_commune: str,
    nom_commune: str = "",
    postal_code: str | None = None,
    max_price: float | None = None,
    pages: int = 2,
    mode: str = "achat",
) -> dict:
    """
    mode : "achat" (vente) ou "location" (loyers)
    """
    """
    Retourne un dict avec :
      - listings : liste d'annonces
      - sources_status : statut de chaque source (ok / bloqué / fallback)
      - seloger_url : lien direct SeLoger pour cette commune
      - leboncoin_url : lien direct LeBonCoin pour cette commune
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    listings = []
    sources_status = {}

    cdc_typage = "location" if mode == "location" else "vente"
    sl_mode = "location" if mode == "location" else "achat"

    # Lance les 3 en parallèle
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_fetch_seloger, code_commune, pages): "SeLoger",
            executor.submit(_fetch_leboncoin, postal_code or "", pages): "LeBonCoin",
            executor.submit(_fetch_cdc, nom_commune, postal_code or "", cdc_typage): "CDC Habitat",
        }
        results = {}
        for future in as_completed(futures):
            source = futures[future]
            results[source] = future.result()

    sl_listings, sl_error = results["SeLoger"]
    lbc_listings, lbc_error = results["LeBonCoin"]
    cdc_listings, cdc_error = results["CDC Habitat"]

    seloger_ok = not sl_error and sl_listings
    leboncoin_ok = not lbc_error and lbc_listings

    if seloger_ok or leboncoin_ok:
        # Au moins une source commerciale fonctionne — on affiche SeLoger + LeBonCoin
        if seloger_ok:
            sources_status["SeLoger"] = ("ok", f"{len(sl_listings)} annonces")
            listings.extend(sl_listings)
        else:
            sources_status["SeLoger"] = ("blocked", sl_error)

        if leboncoin_ok:
            sources_status["LeBonCoin"] = ("ok", f"{len(lbc_listings)} annonces")
            listings.extend(lbc_listings)
        else:
            sources_status["LeBonCoin"] = ("blocked", lbc_error)
    else:
        # Les deux bloqués → fallback CDC Habitat
        sources_status["SeLoger"] = ("blocked", sl_error)
        sources_status["LeBonCoin"] = ("blocked", lbc_error)
        if cdc_error:
            sources_status["CDC Habitat"] = ("blocked", cdc_error)
        else:
            sources_status["CDC Habitat"] = ("fallback", f"{len(cdc_listings)} logements sociaux")
            listings.extend(cdc_listings)

    # Filtre budget
    if max_price and listings:
        listings = [l for l in listings if not l.get("price") or l["price"] <= max_price]

    # Tri par prix croissant
    listings.sort(key=lambda x: x.get("price") or 99_999_999)

    # Liens directs pour la recherche manuelle
    if mode == "location":
        seloger_url = f"https://www.seloger.com/list.htm?ci={code_commune}&idtt=1&tri=d_dt_crea"
        lbc_url = f"https://www.leboncoin.fr/recherche?category=10&locations={postal_code or ''}"
    else:
        seloger_url = f"https://www.seloger.com/list.htm?ci={code_commune}&idtt=2&tri=d_dt_crea"
        lbc_url = f"https://www.leboncoin.fr/recherche?category=9&locations={postal_code or ''}"

    return {
        "listings": listings,
        "sources_status": sources_status,
        "seloger_url": seloger_url,
        "leboncoin_url": lbc_url,
    }
