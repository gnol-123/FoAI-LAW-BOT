"""
Acts to download from legislation.gov.au.

Each entry needs either:
  - series_id: the FedReg series ID (e.g. "C2009A00028") — most reliable
  - OR search_term: a keyword that will be searched if series_id is unknown

Find a series ID by going to https://www.legislation.gov.au and searching for
an act — the series ID is in the URL of the series page.

NOTE: Series IDs use the year the title was registered in the Federal Register,
NOT the year the Act was passed. Most pre-2005 acts were digitised in 2004 and
carry a C2004A... prefix regardless of their enactment year.

Set enabled=False to skip an act without removing it from the list.
"""

ACTS = [
    # ── Core commercial & employment ──────────────────────────────────────────
    {
        "name":      "Fair Work Act 2009",
        "series_id": "C2009A00028",
        "enabled":   True,
    },
    {
        "name":      "Corporations Act 2001",
        "series_id": "C2004A00818",
        "enabled":   True,
    },
    {
        "name":      "Privacy Act 1988",
        "series_id": "C2004A03712",
        "enabled":   True,
    },
    {
        "name":      "Competition and Consumer Act 2010",
        "series_id": "C2010A00110",
        "enabled":   True,
    },
    {
        "name":      "Criminal Code Act 1995",
        "series_id": "C2004A04868",
        "enabled":   True,
    },
    {
        "name":      "Australian Consumer Law",
        "search_term": "Australian Consumer Law schedule 2",
        "enabled":   False,   # Schedule 2 of Competition and Consumer Act — already covered above
    },

    # ── Family & Civil Law ────────────────────────────────────────────────────
    {
        "name":      "Family Law Act 1975",
        "series_id": "C2004A00275",
        "enabled":   True,
    },
    {
        "name":      "Bankruptcy Act 1966",
        "series_id": "C1966A00033",
        "enabled":   True,
    },

    # ── Criminal & Evidence Law ───────────────────────────────────────────────
    {
        "name":      "Crimes Act 1914",
        "series_id": "C1914A00012",
        "enabled":   True,
    },
    {
        "name":      "Evidence Act 1995",
        "series_id": "C2004A04858",
        "enabled":   True,
    },

    # ── Administrative Law ────────────────────────────────────────────────────
    {
        "name":      "Administrative Decisions (Judicial Review) Act 1977",
        "series_id": "C2004A01697",
        "enabled":   True,
    },
    {
        "name":      "Administrative Appeals Tribunal Act 1975",
        "series_id": "C2004A01401",
        "enabled":   True,
    },
    {
        "name":      "Acts Interpretation Act 1901",
        "series_id": "C1901A00002",
        "enabled":   True,
    },

    # ── Tax Law ───────────────────────────────────────────────────────────────
    {
        "name":      "Income Tax Assessment Act 1997",
        "series_id": "C2004A05138",
        "enabled":   True,
    },
    {
        "name":      "Taxation Administration Act 1953",
        "series_id": "C1953A00001",
        "enabled":   True,
    },

    # ── Employment & Safety ───────────────────────────────────────────────────
    {
        "name":      "Work Health and Safety Act 2011",
        "series_id": "C2011A00137",
        "enabled":   True,
    },
    {
        "name":      "Safety, Rehabilitation and Compensation Act 1988",
        "series_id": "C2004A03668",
        "enabled":   True,
    },

    # ── Financial Services ────────────────────────────────────────────────────
    {
        "name":      "Australian Securities and Investments Commission Act 2001",
        "series_id": "C2004A00819",
        "enabled":   True,
    },
    {
        "name":      "Superannuation Industry (Supervision) Act 1993",
        "series_id": "C2004A04633",
        "enabled":   True,
    },
    {
        "name":      "National Consumer Credit Protection Act 2009",
        "series_id": "C2009A00134",
        "enabled":   True,
    },
    {
        "name":      "Anti-Money Laundering and Counter-Terrorism Financing Act 2006",
        "series_id": "C2006A00169",
        "enabled":   True,
    },

    # ── Intellectual Property ─────────────────────────────────────────────────
    {
        "name":      "Copyright Act 1968",
        "series_id": "C1968A00063",
        "enabled":   True,
    },
    {
        "name":      "Trade Marks Act 1995",
        "series_id": "C2004A04969",
        "enabled":   True,
    },
    {
        "name":      "Patents Act 1990",
        "series_id": "C2004A04014",
        "enabled":   True,
    },

    # ── Environment & Planning ────────────────────────────────────────────────
    {
        "name":      "Environment Protection and Biodiversity Conservation Act 1999",
        "series_id": "C2004A00485",
        "enabled":   True,
    },

    # ── Migration ─────────────────────────────────────────────────────────────
    {
        "name":      "Migration Act 1958",
        "series_id": "C1958A00062",
        "enabled":   True,
    },
]

# Scraper behaviour
REQUEST_DELAY_SECONDS = 3      # pause between every HTTP request
MAX_RETRIES           = 3      # retry failed requests this many times
RETRY_BACKOFF_SECONDS = 10     # additional wait per retry (linear backoff)
DOWNLOAD_DIR          = "downloads"   # local folder for downloaded PDFs
