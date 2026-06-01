"""
Entry point: download all enabled acts from legislation.gov.au,
upload each PDF to Firebase Storage, then remove the local copy.

Usage:
    cd scraper
    cp .env.example .env        # fill in your credentials
    pip install -r requirements.txt
    python main.py
"""

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env before any module that reads os.environ
load_dotenv()

from config import ACTS, DOWNLOAD_DIR
from scraper import fetch_act
from uploader import upload_pdf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DEST_DIR = Path(DOWNLOAD_DIR)


def main() -> None:
    enabled = [a for a in ACTS if a.get("enabled", True)]
    log.info(f"Starting — {len(enabled)} act(s) to process")

    succeeded: list[str] = []
    failed: list[str] = []

    for act in enabled:
        name = act["name"]
        log.info(f"{'─' * 10} {name} {'─' * 10}")

        try:
            local_paths = fetch_act(
                name=name,
                series_id=act.get("series_id"),
                search_term=act.get("search_term"),
                dest_dir=DEST_DIR,
            )

            if not local_paths:
                log.error(f"[{name}] Download failed — skipping upload")
                failed.append(name)
                continue

            for local_path in local_paths:
                blob_name = upload_pdf(local_path, name)
                log.info(f"[{name}] Stored: {blob_name}")
                local_path.unlink(missing_ok=True)

            succeeded.append(name)

        except PermissionError as exc:
            log.error(f"[{name}] Blocked by robots.txt: {exc}")
            failed.append(name)
        except Exception as exc:
            log.exception(f"[{name}] Unexpected error: {exc}")
            failed.append(name)

    log.info("─" * 50)
    log.info(f"Finished.  Succeeded: {len(succeeded)}  Failed: {len(failed)}")
    if failed:
        log.warning(f"Failed: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
