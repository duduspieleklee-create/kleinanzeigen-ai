from urllib.parse import urlencode
from typing import Optional


def build_kleinanzeigen_url(
    keywords: Optional[str] = None,
    category: Optional[str] = None,
    location: Optional[str] = None,
    price_max: Optional[int] = None,
    radius: Optional[int] = None,
    sort: Optional[str] = "neueste"
) -> str:
    """
    Builds a search URL for kleinanzeigen.de based on user parameters.
    This is a simplified but functional version for Milestone 1.
    """

    base_url = "https://www.kleinanzeigen.de"

    # Build path
    path_parts = []
    if category:
        path_parts.append(f"s-{category}")
    else:
        path_parts.append("s-all")

    if location:
        path_parts.append(location.replace(" ", "-").lower())

    path = "/".join(path_parts) + "/"

    # Build query parameters
    query_params = {}

    if keywords:
        query_params["k0"] = keywords.strip()

    if price_max:
        query_params["p"] = price_max

    if radius:
        query_params["r"] = radius

    if sort:
        query_params["sortierung"] = sort

    # Construct final URL
    if query_params:
        return f"{base_url}/{path}?{urlencode(query_params)}"
    else:
        return f"{base_url}/{path}"
