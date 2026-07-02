"""Seller data extraction from kleinanzeigen.de listing pages.

This module handles scraping seller information (rating, badges, ID, name)
from individual listing detail pages. It complements the main scraper which
extracts listing metadata from search result pages.
"""
import logging
from typing import Optional, Dict
from bs4 import BeautifulSoup

logger = logging.getLogger("kleinanzeigen-ai")


def extract_seller_info(html: str) -> Optional[Dict]:
    """Extract seller information from a listing detail page HTML.

    Returns a dict with keys: seller_id, seller_name, seller_rating, seller_badges
    or None if extraction fails.

    Seller data is typically found in:
    - Seller ID: data-userid or in profile link href
    - Seller Name: in profile section text
    - Rating: "TOP Zufriedenheit", "OK", "NAJA"
    - Badges: "Freundlich", "Zuverlässig" (as separate badge elements)
    """
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception as e:
        logger.warning(f"Failed to parse HTML for seller info: {e}")
        return None

    seller_info = {
        "seller_id": None,
        "seller_name": None,
        "seller_rating": None,
        "seller_badges": None,
    }

    # Find the seller profile section (usually contains user name and badges)
    profile_section = soup.find("div", class_="profile-userbadges")
    if not profile_section:
        # Try alternative selector
        profile_section = soup.find("div", class_="userprofile-vip")

    if profile_section:
        # Extract seller name from the profile link or heading
        name_tag = profile_section.find("a", href=lambda x: x and "bestandsliste" in x)
        if name_tag:
            seller_info["seller_name"] = name_tag.get_text(strip=True)
            # Extract seller_id from href (e.g., ?userId=144701528)
            href = name_tag.get("href", "")
            if "userId=" in href:
                seller_info["seller_id"] = href.split("userId=")[-1].split("&")[0]

        # Extract rating badge (TOP, OK, NAJA)
        rating_badge = profile_section.find("a", href=lambda x: x and "nutzerbewertung" in x)
        if rating_badge:
            rating_text = rating_badge.get_text(strip=True)
            # Extract just the rating part (e.g., "TOP Zufriedenheit" -> "TOP")
            if "TOP" in rating_text:
                seller_info["seller_rating"] = "TOP"
            elif "OK" in rating_text:
                seller_info["seller_rating"] = "OK"
            elif "NAJA" in rating_text:
                seller_info["seller_rating"] = "NAJA"

        # Extract badges (Freundlich, Zuverlässig)
        badges = []
        badge_elements = profile_section.find_all("a", href=lambda x: x and ("freundlichkeits" in x or "zuverlaessigkeits" in x))
        for badge_elem in badge_elements:
            badge_text = badge_elem.get_text(strip=True)
            if "Freundlich" in badge_text:
                badges.append("Freundlich")
            elif "Zuverlässig" in badge_text:
                badges.append("Zuverlässig")

        if badges:
            seller_info["seller_badges"] = ",".join(badges)

    # Fallback: try to find seller info in the main contact section
    if not seller_info["seller_name"]:
        contact_section = soup.find("div", class_="viewad-contact")
        if contact_section:
            name_link = contact_section.find("a", href=lambda x: x and "bestandsliste" in x)
            if name_link:
                seller_info["seller_name"] = name_link.get_text(strip=True)
                href = name_link.get("href", "")
                if "userId=" in href:
                    seller_info["seller_id"] = href.split("userId=")[-1].split("&")[0]

    # Only return if we found at least some data
    if any(seller_info.values()):
        return seller_info

    return None


def fetch_and_extract_seller_info(url: str, session=None) -> Optional[Dict]:
    """Fetch a listing detail page and extract seller information.

    Args:
        url: Full URL to the listing detail page
        session: Optional requests.Session for connection pooling

    Returns:
        Dict with seller info or None if extraction fails
    """
    import requests

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        if session:
            response = session.get(url, headers=headers, timeout=10)
        else:
            response = requests.get(url, headers=headers, timeout=10)

        response.raise_for_status()
        return extract_seller_info(response.text)

    except Exception as e:
        logger.warning(f"Failed to fetch seller info from {url}: {e}")
        return None
