"""Public Data Portal festival collector and SQLite upsert script."""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import httpx
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from app.database import BACKEND_DIR, SessionLocal, init_db
from app.models import Festival, build_festival_key

load_dotenv(BACKEND_DIR / ".env")

DEFAULT_API_URL = "http://api.data.go.kr/openapi/tn_pubr_public_cltur_fstvl_api"
PLACEHOLDER_KEYS = {"", "your_public_data_api_key_here"}

logger = logging.getLogger(__name__)


@dataclass
class CollectionStats:
    """Summary metrics returned after running the festival collector."""

    total_count: int
    pages_fetched: int
    records_parsed: int
    records_upserted: int
    skipped_rows: int


def normalize_service_key(raw_key: str) -> str:
    """Normalize either an Encoding or Decoding Public Data Portal service key.

    Encoding keys already contain percent-escaped sequences (e.g. ``%2B``, ``%3D``).
    Unquoting once yields the raw decoded key so ``httpx`` URL-encodes it exactly once.
    """
    cleaned = raw_key.strip()
    if "%" in cleaned:
        return unquote(cleaned)
    return cleaned


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("+", ", ")
    return re.sub(r"\s+", " ", text).strip()


def _parse_api_response(response: httpx.Response) -> tuple[list[dict[str, Any]], int]:
    """Parse Public Data Portal JSON (or surface XML/error details cleanly)."""
    text = response.text.strip()
    if not text:
        raise RuntimeError("Empty response received from Public Data Portal API.")

    if text.startswith("<"):
        err_msg = "XML error response received from Public Data Portal API."
        try:
            root = ET.fromstring(text)
            msg = root.findtext(".//returnAuthMsg") or root.findtext(".//errMsg")
            code = root.findtext(".//returnReasonCode") or root.findtext(".//resultCode")
            if msg or code:
                err_msg = f"Public Data Portal API error (code={code}): {msg}"
        except ET.ParseError:
            pass
        raise RuntimeError(err_msg)

    payload: dict[str, Any] = response.json()
    resp_node = payload.get("response") if "response" in payload else payload
    if not isinstance(resp_node, dict) or ("header" not in resp_node and "body" not in resp_node):
        raise RuntimeError(f"Unexpected API response structure: {payload}")

    header = resp_node.get("header") or {}
    result_code = str(header.get("resultCode") or "")
    result_msg = str(header.get("resultMsg") or "")
    if result_code and result_code != "00":
        raise RuntimeError(
            f"Public Data Portal API returned error (resultCode={result_code}): {result_msg}"
        )

    body = resp_node.get("body") or {}
    total_count = int(body.get("totalCount") or 0)
    raw_items = body.get("items")

    if isinstance(raw_items, list):
        items = [item for item in raw_items if isinstance(item, dict)]
    elif isinstance(raw_items, dict):
        # Some data.go.kr endpoints wrap a list under {"item": [...]} or return a single dict.
        nested = raw_items.get("item")
        if isinstance(nested, list):
            items = [item for item in nested if isinstance(item, dict)]
        elif isinstance(nested, dict):
            items = [nested]
        else:
            items = [raw_items]
    else:
        items = []

    return items, total_count


def _map_item_to_row(item: dict[str, Any]) -> dict[str, str] | None:
    """Map one API item dict into festival column values, skipping rows without a name."""
    fstvl_nm = _clean_text(item.get("fstvlNm"))
    if not fstvl_nm:
        return None

    start = _clean_text(item.get("fstvlStartDate"))
    end = _clean_text(item.get("fstvlEndDate"))
    opar = _clean_text(item.get("opar"))
    return {
        "unique_key": build_festival_key(fstvl_nm, start, end, opar),
        "fstvl_nm": fstvl_nm,
        "fstvl_start_date": start,
        "fstvl_end_date": end,
        "opar": opar,
        "fstvl_co": _clean_text(item.get("fstvlCo")),
        "rdnmadr": _clean_text(item.get("rdnmadr")),
    }


def upsert_rows(session: Session, rows: list[dict[str, str]], batch_size: int = 500) -> int:
    """Upsert rows keyed by unique_key; ai_summary columns are never touched."""
    deduped = {row["unique_key"]: row for row in rows}
    values = list(deduped.values())
    now = datetime.now(timezone.utc)
    for start in range(0, len(values), batch_size):
        batch = [{**row, "updated_at": now} for row in values[start : start + batch_size]]
        stmt = sqlite_insert(Festival).values(batch)
        update_cols = {c: stmt.excluded[c] for c in batch[0] if c != "unique_key"}
        session.execute(stmt.on_conflict_do_update(index_elements=["unique_key"], set_=update_cols))
    session.commit()
    return len(values)


async def fetch_all_festivals(
    api_key: str,
    api_url: str,
    num_of_rows: int = 100,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[list[dict[str, str]], int, int, int]:
    """Fetch every page of festival data from the Public Data Portal API."""
    normalized_key = normalize_service_key(api_key)
    all_records: list[dict[str, str]] = []
    skipped_rows = 0
    pages_fetched = 0
    total_count = 0

    async with httpx.AsyncClient(timeout=30.0, transport=transport) as client:
        page_no = 1
        total_pages = 1

        while page_no <= total_pages:
            params = {
                "serviceKey": normalized_key,
                "pageNo": str(page_no),
                "numOfRows": str(num_of_rows),
                "type": "json",
            }
            response = await client.get(api_url, params=params)
            response.raise_for_status()

            items, reported_total = _parse_api_response(response)
            pages_fetched += 1

            if page_no == 1:
                total_count = reported_total
                total_pages = max(1, math.ceil(total_count / num_of_rows)) if total_count else 1

            for item in items:
                record = _map_item_to_row(item)
                if record is None:
                    skipped_rows += 1
                else:
                    all_records.append(record)

            logger.info(
                "Fetched page %d/%d (%d items)", page_no, total_pages, len(items)
            )
            if total_count == 0 or not items:
                break
            page_no += 1

    return all_records, total_count, pages_fetched, skipped_rows


async def collect_and_store(
    num_of_rows: int = 100,
    session: Session | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> CollectionStats:
    """Collect all festivals from Public Data Portal and upsert into SQLite."""
    raw_api_key = os.getenv("PUBLIC_DATA_API_KEY") or ""
    if raw_api_key.strip() in PLACEHOLDER_KEYS:
        raise RuntimeError(
            "PUBLIC_DATA_API_KEY is not configured. Set your actual API key in backend/.env."
        )

    api_url = (os.getenv("PUBLIC_DATA_API_URL") or DEFAULT_API_URL).strip()
    records, total_count, pages_fetched, skipped_rows = await fetch_all_festivals(
        api_key=raw_api_key,
        api_url=api_url,
        num_of_rows=num_of_rows,
        transport=transport,
    )

    init_db()
    owns_session = session is None
    db = session or SessionLocal()
    try:
        upserted = upsert_rows(db, records)
    finally:
        if owns_session:
            db.close()

    return CollectionStats(
        total_count=total_count,
        pages_fetched=pages_fetched,
        records_parsed=len(records),
        records_upserted=upserted,
        skipped_rows=skipped_rows,
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    # httpx logs full request URLs at INFO, which would leak serviceKey.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(
        description="Collect Korean cultural festival data and store in SQLite."
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Number of rows per API page request (default: 100).",
    )
    args = parser.parse_args()

    stats = asyncio.run(collect_and_store(num_of_rows=args.page_size))
    print(
        f"Collection complete: totalCount={stats.total_count}, "
        f"pages={stats.pages_fetched}, parsed={stats.records_parsed}, "
        f"upserted={stats.records_upserted}, skipped={stats.skipped_rows}"
    )


if __name__ == "__main__":
    main()
