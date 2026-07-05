from __future__ import annotations

"""
Scraping d'annonces BienIci via Playwright (navigateur headless).
Fallback sur liens directs si Playwright non installé.
"""

import asyncio
from typing import Optional


async def _scrape_bienici_async(url: str, max_results: int = 15) -> list[dict]:
    from playwright.async_api import async_playwright

    listings = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        # Intercepte les réponses JSON de l'API BienIci
        api_data: list[dict] = []

        async def handle_response(response):
            if "realEstateAds.json" in response.url:
                try:
                    body = await response.json()
                    api_data.extend(body.get("realEstateAds", []))
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
        except Exception:
            pass  # timeout partiel OK si l'API a déjà répondu

        await browser.close()

        for ad in api_data[:max_results]:
            price = ad.get("price")
            surface = ad.get("surfaceArea")
            listings.append({
                "source": "BienIci",
                "title": ad.get("title", ""),
                "city": ad.get("city", ""),
                "price": price,
                "surface_m2": surface,
                "price_m2": round(price / surface, 0) if price and surface else None,
                "rooms": ad.get("roomsQuantity"),
                "url": "https://www.bienici.com" + ad.get("url", ""),
                "photo": (ad.get("photos") or [{}])[0].get("url_photo"),
            })

    return listings


def scrape_bienici(
    commune_slug: str,
    code_insee: str,
    mode: str = "achat",
    max_results: int = 15,
) -> tuple[list[dict], Optional[str]]:
    """
    Scrape BienIci pour une commune donnée.
    Retourne (listings, error_message).
    """
    try:
        filter_type = "location" if mode == "location" else "achat"
        url = (
            f"https://www.bienici.com/recherche/{filter_type}/"
            f"ville-{commune_slug}_{code_insee}"
            f"?typesBiens=flat&tri=publication-desc"
        )
        listings = asyncio.run(_scrape_bienici_async(url, max_results))
        if not listings:
            return [], "Aucune annonce trouvée (la page a peut-être mis du temps à charger)"
        return listings, None
    except ImportError:
        return [], "Playwright non installé — exécutez : pip install playwright && playwright install chromium"
    except Exception as e:
        return [], f"Erreur scraping : {e}"


def fetch_listings(
    code_commune: str,
    nom_commune: str = "",
    postal_code: str | None = None,
    commune_slug: str = "",
    max_price: float | None = None,
    mode: str = "achat",
) -> dict:
    """
    Scrape BienIci via Playwright.
    Retourne dict avec listings, sources_status, et urls de fallback.
    """
    import re as _re
    slug = commune_slug or _re.sub(r"[^a-z0-9]+", "-", nom_commune.lower().strip()).strip("-")

    listings, error = scrape_bienici(slug, code_commune, mode=mode)

    sources_status = {}
    if error:
        sources_status["BienIci"] = ("blocked", error)
    else:
        sources_status["BienIci"] = ("ok", f"{len(listings)} annonces")

    if max_price and listings:
        listings = [l for l in listings if not l.get("price") or l["price"] <= max_price]

    listings.sort(key=lambda x: x.get("price") or 99_999_999)

    filter_type = "location" if mode == "location" else "achat"
    bienici_url = f"https://www.bienici.com/recherche/{filter_type}/ville-{slug}_{code_commune}"
    seloger_idtt = "1" if mode == "location" else "2"
    lbc_cat = "10" if mode == "location" else "9"

    return {
        "listings": listings,
        "sources_status": sources_status,
        "bienici_url": bienici_url,
        "seloger_url": f"https://www.seloger.com/list.htm?ci={code_commune}&idtt={seloger_idtt}&tri=d_dt_crea",
        "leboncoin_url": f"https://www.leboncoin.fr/recherche?category={lbc_cat}&locations={postal_code or ''}",
    }
