from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import logging
from pathlib import Path
import re
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import normalize_whitespace, write_json


logger = logging.getLogger(__name__)
CROSSREF_API_URL = "https://api.crossref.org/works"
DEFAULT_USER_AGENT = "Day10DataPipelineLab/0.1 (mailto:lab@example.com)"
JATS_TAG_RE = re.compile(r"</?jats:p>", re.IGNORECASE)
MAX_RETRIES = 5


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _strip_jats(text: str | None) -> str:
    if not text:
        return ""
    return normalize_whitespace(JATS_TAG_RE.sub(" ", text))


def _parse_date(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("date-parts")
    if isinstance(value, list) and value and isinstance(value[0], list):
        value = value[0]
    if isinstance(value, list) and value:
        try:
            year = int(value[0])
            month = int(value[1]) if len(value) > 1 else 1
            day = int(value[2]) if len(value) > 2 else 1
            return datetime(year, month, min(day, 28)).date().isoformat()
        except (TypeError, ValueError):
            return ""
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return ""
    return ""


def _extract_authors(value: Any) -> list[str]:
    result: list[str] = []
    for author in value or []:
        if not isinstance(author, dict):
            continue
        given = normalize_whitespace(str(author.get("given", "")))
        family = normalize_whitespace(str(author.get("family", "")))
        name = f"{family}, {given}".strip(", ").strip()
        if not name:
            name = normalize_whitespace(str(author.get("name", "")))
        if name:
            result.append(name)
    return result


def _extract_pdf_url(item: dict[str, Any]) -> str:
    for link in item.get("link", []) or []:
        if not isinstance(link, dict):
            continue
        url = str(link.get("URL", ""))
        content_type = str(link.get("content-type", "")).lower()
        if url and ("pdf" in content_type or url.lower().endswith(".pdf")):
            return url
    return ""


def parse_crossref_payload(payload: dict[str, Any]) -> list[PaperRecord]:
    """Parse Crossref response payload into normalized paper records."""
    items = (payload.get("message") or {}).get("items") or []
    records: list[PaperRecord] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        doi = normalize_whitespace(str(item.get("DOI", ""))).lower()
        titles = item.get("title") or []
        title = normalize_whitespace(str(titles[0])) if titles else ""
        if not doi or not title:
            continue
        categories = [normalize_whitespace(str(x)) for x in item.get("subject", []) or [] if x]
        issued = item.get("issued") or {}
        updated = item.get("updated") or {}
        published = _parse_date(issued)
        updated_date = _parse_date(updated)
        records.append(
            PaperRecord(
                paper_id=doi,
                title=title,
                summary=_strip_jats(item.get("abstract")),
                authors=_extract_authors(item.get("author")),
                categories=categories,
                primary_category=categories[0] if categories else "",
                published=published or updated_date,
                updated=updated_date,
                abs_url=str(item.get("URL") or f"https://doi.org/{doi}"),
                pdf_url=_extract_pdf_url(item),
                comment=normalize_whitespace(str(item.get("subtitle") or "")),
            )
        )
    return records


def _request_with_backoff(params: dict[str, Any]) -> dict[str, Any]:
    last_error: Exception | None = None
    headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(CROSSREF_API_URL, params=params, headers=headers, timeout=30)
            if response.status_code in {429, 503}:
                time.sleep(min(2**attempt, 30))
                continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(min(2**attempt, 30))
    raise RuntimeError(f"Crossref request failed after {MAX_RETRIES} attempts: {last_error}")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch Crossref records and persist both raw response and parsed snapshot."""
    params: dict[str, Any] = {
        "query.bibliographic": settings.source_query,
        "rows": settings.max_results,
    }
    if settings.source_filter:
        params["filter"] = settings.source_filter
    payload = _request_with_backoff(params)
    write_json(settings.paths.raw_api_response, payload)
    records = parse_crossref_payload(payload)
    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Load a parsed Crossref snapshot from JSON."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected a list of records in {path}")
    return [PaperRecord(**entry) for entry in payload]
