"""
Polite scraper for legislation.gov.au.

Etiquette rules applied:
  - Checks robots.txt before fetching any www.legislation.gov.au path
  - Waits REQUEST_DELAY_SECONDS between every request
  - Identifies itself with a descriptive User-Agent
  - Uses linear back-off on transient errors
  - Never retries a path that returned 404

The Federal Register of Legislation exposes a public REST API at
api.prod.legislation.gov.au/v1 (used by its own SPA). We use that API to
look up the latest compilation date and available PDF volumes, then
construct direct PDF download URLs — no HTML scraping required.
"""

import logging
import re
import time
from pathlib import Path
from urllib.parse import quote
from urllib.robotparser import RobotFileParser

import requests

from config import REQUEST_DELAY_SECONDS, MAX_RETRIES, RETRY_BACKOFF_SECONDS

log = logging.getLogger(__name__)

BASE_URL = "https://www.legislation.gov.au"
API_BASE = "https://api.prod.legislation.gov.au/v1"
USER_AGENT = (
    "LoRAai-Legal-Research/1.0 "
    "(polite educational scraper; github.com/your-repo; "
    "contact: your@email.com)"
)

# ── Shared session ─────────────────────────────────────────────────────────────
_session = requests.Session()
_session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept":     "text/html,application/xhtml+xml,application/pdf,application/json,*/*",
})

# ── robots.txt cache (www domain only) ────────────────────────────────────────
_rp: RobotFileParser | None = None


def _robots() -> RobotFileParser:
    global _rp
    if _rp is None:
        _rp = RobotFileParser()
        _rp.set_url(f"{BASE_URL}/robots.txt")
        try:
            _rp.read()
            log.info("robots.txt loaded")
        except Exception as exc:
            log.warning(f"Could not read robots.txt: {exc} — proceeding cautiously")
    return _rp


def _allowed(url: str) -> bool:
    # Only check robots.txt for the www domain; the REST API has no robots.txt
    if not url.startswith(BASE_URL):
        return True
    return _robots().can_fetch(USER_AGENT, url)


# ── Polite GET ─────────────────────────────────────────────────────────────────
def _get(url: str, stream: bool = False) -> requests.Response:
    if not _allowed(url):
        raise PermissionError(f"robots.txt disallows: {url}")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log.debug(f"GET {url}  (attempt {attempt})")
            time.sleep(REQUEST_DELAY_SECONDS)
            resp = _session.get(url, timeout=60, stream=stream, allow_redirects=True)
            if resp.status_code == 404:
                log.warning(f"404 Not Found: {url}")
                return resp             # do not retry 404s
            resp.raise_for_status()
            return resp
        except requests.HTTPError as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = RETRY_BACKOFF_SECONDS * attempt
            log.warning(f"HTTP error {exc} — retrying in {wait}s …")
            time.sleep(wait)
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = RETRY_BACKOFF_SECONDS * attempt
            log.warning(f"Request failed: {exc} — retrying in {wait}s …")
            time.sleep(wait)


# ── FRL REST API ───────────────────────────────────────────────────────────────

def _api_get_latest_version(series_id: str) -> dict | None:
    """
    Return the latest version metadata for a series from the FRL API.
    The dict contains at least 'start' (ISO datetime), 'compilationNumber',
    and 'registerId'.
    """
    url = f"{API_BASE}/versions/find(titleId='{series_id}',asAtSpecification='latest')"
    log.info(f"API: latest version for {series_id}")
    try:
        resp = _get(url)
        if resp.status_code == 404:
            log.error(f"Series not found in API: {series_id}")
            return None
        return resp.json()
    except Exception as exc:
        log.error(f"API version lookup failed for {series_id}: {exc}")
        return None


def _api_get_pdf_volumes(series_id: str, date: str, comp_number: str) -> list[dict]:
    """
    Return document records for every PDF volume of a compilation,
    sorted by volumeNumber ascending.
    """
    url = (
        f"{API_BASE}/documents"
        f"?$filter=retrospectiveStart eq {date}"
        f" and start eq {date}"
        f" and titleId eq '{series_id}'"
        f" and compilationNumber eq '{comp_number}'"
    )
    log.info(f"API: documents for {series_id} at {date}")
    try:
        resp = _get(url)
        if resp.status_code != 200:
            return []
        docs = resp.json().get("value", [])
        pdfs = [d for d in docs if d.get("format", "").lower() == "pdf"]
        pdfs.sort(key=lambda d: d.get("volumeNumber", 0))
        return pdfs
    except Exception as exc:
        log.error(f"API documents lookup failed: {exc}")
        return []


# ── Download ───────────────────────────────────────────────────────────────────

def download_pdf(pdf_url: str, dest_dir: Path, suggested_name: str = "") -> Path | None:
    """
    Stream-download a PDF to dest_dir.
    Returns the local Path on success, None on failure.
    """
    log.info(f"Downloading: {pdf_url}")
    resp = _get(pdf_url, stream=True)
    if resp.status_code != 200:
        log.error(f"Download failed ({resp.status_code}): {pdf_url}")
        return None

    ct = resp.headers.get("Content-Type", "").lower()
    if "html" in ct:
        log.error(f"Got HTML instead of PDF (Content-Type: {ct}): {pdf_url}")
        return None

    # Derive filename: Content-Disposition > suggested_name > URL tail
    cd = resp.headers.get("Content-Disposition", "")
    m = re.search(r'filename[^;=\n]*=\s*["\']?([^"\';\n]+)', cd)
    if m:
        filename = m.group(1).strip().strip("\"'")
    elif suggested_name:
        filename = re.sub(r"[^\w\-. ]", "_", suggested_name) + ".pdf"
    else:
        filename = pdf_url.split("/")[-1].split("?")[0] or "legislation.pdf"

    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    dest_path = dest_dir / filename
    dest_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            total += len(chunk)

    log.info(f"Saved: {dest_path.name}  ({total / 1024:.0f} KB)")
    return dest_path


# ── Search fallback ────────────────────────────────────────────────────────────

def search_for_series(keyword: str) -> str | None:
    """
    Search the FRL API for a title by keyword and return its series ID.
    """
    url = (
        f"{API_BASE}/titles"
        f"?$filter=contains(name,'{quote(keyword)}') and status eq 'InForce'"
        f"&$select=id,name&$top=5"
    )
    log.info(f"API search: '{keyword}'")
    try:
        resp = _get(url)
        if resp.status_code != 200:
            return None
        items = resp.json().get("value", [])
        if items:
            found_id = items[0]["id"]
            log.info(f"Found series: {found_id} for '{keyword}'")
            return found_id
    except Exception as exc:
        log.warning(f"API search failed: {exc}")
    return None


# ── Public API ─────────────────────────────────────────────────────────────────

def fetch_act(name: str, series_id: str | None = None, search_term: str | None = None,
              dest_dir: Path = Path("downloads")) -> list[Path]:
    """
    Download all compiled PDF volumes for an act via the FRL REST API.

    Provide series_id for reliability, or search_term as a fallback.
    Returns a list of local Paths (one per volume) on success, empty list on failure.
    Multi-volume acts (e.g. Fair Work Act) produce multiple files.
    """
    if not series_id and search_term:
        log.info(f"[{name}] No series ID — searching for '{search_term}' …")
        series_id = search_for_series(search_term)
        if not series_id:
            log.error(f"[{name}] Could not find series ID via search")
            return []

    # 1. Get latest compilation metadata
    version = _api_get_latest_version(series_id)
    if not version:
        return []

    date = version["start"][:10]                 # "2026-04-02T00:00:00" → "2026-04-02"
    comp_number = version["compilationNumber"]
    register_id = version.get("registerId", "?")
    log.info(f"[{name}] Latest: {register_id} (C{comp_number}, effective {date})")

    # 2. List available PDF volumes
    pdf_docs = _api_get_pdf_volumes(series_id, date, comp_number)
    if not pdf_docs:
        log.error(f"[{name}] No PDF volumes returned by API")
        return []

    log.info(f"[{name}] {len(pdf_docs)} PDF volume(s) to download")

    # 3. Download each volume
    # PDF URL pattern: /{series_id}/{date}/{date}/text/original/pdf/{volumeNumber}
    paths: list[Path] = []
    for doc in pdf_docs:
        vol = doc["volumeNumber"]
        pdf_url = f"{BASE_URL}/{series_id}/{date}/{date}/text/original/pdf/{vol}"
        vol_label = f"{name} Vol {vol}" if len(pdf_docs) > 1 else name
        local_path = download_pdf(pdf_url, dest_dir, suggested_name=vol_label)
        if local_path:
            paths.append(local_path)
        else:
            log.warning(f"[{name}] Volume {vol} download failed — continuing with other volumes")

    return paths
