"""
Acts to download from legislation.gov.au.

Each entry needs either:
  - series_id: the FedReg series ID (e.g. "C2009A00028") — most reliable
  - OR search_term: a keyword that will be searched if series_id is unknown

Find a series ID by going to https://www.legislation.gov.au and searching for
an act — the series ID is in the URL of the series page.

Set enabled=False to skip an act without removing it from the list.
"""

ACTS = [
    {
        "name":      "Fair Work Act 2009",
        "series_id": "C2009A00028",
        "enabled":   True,
    },
    {
        "name":      "Corporations Act 2001",
        "series_id": "C2001A00050",
        "enabled":   True,
    },
    {
        "name":      "Privacy Act 1988",
        "series_id": "C1988A00119",
        "enabled":   True,
    },
    {
        "name":      "Competition and Consumer Act 2010",
        "series_id": "C2010A00110",
        "enabled":   True,
    },
    {
        "name":      "Criminal Code Act 1995",
        "series_id": "C1995A00012",
        "enabled":   True,
    },
    {
        "name":      "Australian Consumer Law",
        "search_term": "Australian Consumer Law schedule 2",
        "enabled":   False,   # included in Competition and Consumer Act above
    },
]

# Scraper behaviour
REQUEST_DELAY_SECONDS = 3      # pause between every HTTP request
MAX_RETRIES           = 3      # retry failed requests this many times
RETRY_BACKOFF_SECONDS = 10     # additional wait per retry (linear backoff)
DOWNLOAD_DIR          = "downloads"   # local folder for downloaded PDFs
