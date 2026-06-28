# URL Builder — `app/shared/url_builder.py`

Builds dynamic search URLs for kleinanzeigen.de based on user-provided parameters.

## Function Signature

```python
def build_kleinanzeigen_url(
    keywords: Optional[str] = None,
    category: Optional[str] = None,
    location: Optional[str] = None,
    price_max: Optional[int] = None,
    radius: Optional[int] = None,
    sort: Optional[str] = "neueste"
) -> str:
```

## Parameters

| Parameter   | Type            | Default     | Query Param    | Description                        |
|-------------|-----------------|-------------|----------------|------------------------------------|
| `keywords`  | `str\|None`     | `None`      | `k0`           | Free-text search keywords          |
| `category`  | `str\|None`     | `None`      | path segment   | Category slug (e.g. `handwerk`)    |
| `location`  | `str\|None`     | `None`      | path segment   | City or region (e.g. `berlin`)     |
| `price_max` | `int\|None`     | `None`      | `p`            | Maximum price filter               |
| `radius`    | `int\|None`     | `None`      | `r`            | Search radius in km                |
| `sort`      | `str\|None`     | `"neueste"` | `sortierung`   | Sort order (`neueste`, `preis`)    |

## Usage Examples

### Full search with all parameters

```python
from app.shared.url_builder import build_kleinanzeigen_url

url = build_kleinanzeigen_url(
    keywords="handwerker",
    category="handwerk",
    location="berlin",
    price_max=150,
    radius=50
)

print(url)
# https://www.kleinanzeigen.de/s-handwerk/berlin/?k0=handwerker&p=150&r=50&sortierung=neueste
```

### Category only

```python
url = build_kleinanzeigen_url(category="elektronik")
# https://www.kleinanzeigen.de/s-elektronik/
```

### No filters — all listings

```python
url = build_kleinanzeigen_url()
# https://www.kleinanzeigen.de/s-all/
```

### Keywords with location

```python
url = build_kleinanzeigen_url(keywords="sofa", location="muenchen")
# https://www.kleinanzeigen.de/s-all/muenchen/?k0=sofa&sortierung=neueste
```

## Notes

- Category is prefixed with `s-` in the URL path (e.g. `handwerk` → `s-handwerk`)
- If no category is provided, defaults to `s-all`
- Query parameters are URL-encoded via `urllib.parse.urlencode`
- Pagination support (page number) is planned for post-M1
