"""Crossref ingestion - Role 2 (Ingestion owner).

Trach nhiem cua module nay:
  1. Goi Crossref REST API theo contract trong `Settings` (query / filter / max_results).
  2. Luu raw API response *truoc khi parse* -> `data/raw/crossref_response.json`.
  3. Parse payload thanh `PaperRecord` co `paper_id` stable (derive tu DOI).
  4. Luu raw records da parse -> `data/raw/crossref_records.json` (kem lineage metadata).
  5. Doc lai snapshot bang `load_raw_records` de repair khong can fetch lai source.

Ba diem hop dong voi cac role khac:
  - Cleaning owner nhan `list[PaperRecord]`, moi field luon la str / list[str] (khong None).
  - `paper_id` = DOI lowercase => truy vet duoc raw -> clean -> index metadata.
  - Repair flow chi doc lai file snapshot, khong bao gio goi lai API.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import hashlib
import os
import random
import re
import time
from typing import Any, Iterable

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json, now_utc

CROSSREF_API_URL = "https://api.crossref.org/works"

# Status code tam thoi -> nen retry thay vi fail pipeline.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 1.5
REQUEST_TIMEOUT_SECONDS = 30

# Abstract cua Crossref la JATS XML: <jats:p>, <jats:italic>, ...
_JATS_TAG_RE = re.compile(r"<[^>]+>")
_ABSTRACT_LABEL_RE = re.compile(r"^\s*abstract[:\s-]*", flags=re.IGNORECASE)


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


@dataclass(frozen=True)
class RejectedItem:
    """Mot item cua source bi loai khi parse - luon co ly do de truy vet."""

    item_index: int
    doi: str
    title: str
    reason: str


@dataclass(frozen=True)
class ParseReport:
    """Ket qua parse day du: records + ly do loai bo (khong mat record am tham)."""

    records: list[PaperRecord] = field(default_factory=list)
    rejected: list[RejectedItem] = field(default_factory=list)
    items_seen: int = 0

    @property
    def reason_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.rejected:
            counts[item.reason] = counts.get(item.reason, 0) + 1
        return counts

    def as_dict(self) -> dict[str, Any]:
        return {
            "items_seen": self.items_seen,
            "records_kept": len(self.records),
            "records_rejected": len(self.rejected),
            "reject_reason_counts": self.reason_counts,
            "rejected": [asdict(item) for item in self.rejected],
        }


# ---------------------------------------------------------------------------
# Field-level helpers
# ---------------------------------------------------------------------------


def _clean_text(value: Any) -> str:
    """Ep bat ky gia tri nao ve string da normalize whitespace."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(item) for item in value if item)
    return normalize_whitespace(str(value))


def _clean_abstract(value: Any) -> str:
    """Bo JATS tag va tien to 'Abstract' trong abstract cua Crossref."""
    text = _clean_text(value)
    if not text:
        return ""
    text = _JATS_TAG_RE.sub(" ", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#x2018;", "'")
        .replace("&#x2019;", "'")
        .replace("&apos;", "'")
    )
    text = _ABSTRACT_LABEL_RE.sub("", text)
    return normalize_whitespace(text)


def _first_non_empty(values: Iterable[Any]) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _parse_author_names(authors: Any) -> list[str]:
    """Crossref author: {given, family} hoac {name} cho to chuc."""
    if not isinstance(authors, list):
        return []
    names: list[str] = []
    for author in authors:
        if not isinstance(author, dict):
            name = _clean_text(author)
            if name:
                names.append(name)
            continue
        given = _clean_text(author.get("given"))
        family = _clean_text(author.get("family"))
        full = _clean_text(f"{given} {family}") or _clean_text(author.get("name"))
        if full and full not in names:
            names.append(full)
    return names


def _parse_date_parts(container: Any) -> str:
    """`{"date-parts": [[2025, 3, 7]]}` -> "2025-03-07" (pad thang/ngay neu thieu)."""
    if not isinstance(container, dict):
        return ""
    parts = container.get("date-parts")
    if not isinstance(parts, list) or not parts:
        return ""
    first = parts[0]
    if not isinstance(first, list) or not first:
        return ""
    numbers: list[int] = []
    for item in first[:3]:
        try:
            numbers.append(int(item))
        except (TypeError, ValueError):
            break
    if not numbers:
        return ""
    year = numbers[0]
    month = numbers[1] if len(numbers) > 1 else 1
    day = numbers[2] if len(numbers) > 2 else 1
    month = min(max(month, 1), 12)
    day = min(max(day, 1), 31)
    return f"{year:04d}-{month:02d}-{day:02d}"


def _parse_published(item: dict) -> str:
    """Uu tien ngay xuat ban som nhat co that; fallback theo do tin cay giam dan."""
    for key in ("published", "published-online", "published-print", "issued", "created"):
        date = _parse_date_parts(item.get(key))
        if date:
            return date
    return ""


def _parse_updated(item: dict) -> str:
    """Timestamp gan nhat source cap nhat record - dung cho freshness signal."""
    for key in ("indexed", "deposited"):
        container = item.get(key)
        if isinstance(container, dict):
            timestamp = _clean_text(container.get("date-time"))
            if timestamp:
                return timestamp
        date = _parse_date_parts(container)
        if date:
            return date
    return _parse_published(item)


def _parse_categories(item: dict) -> list[str]:
    """Subject la field chinh; fallback container-title/type de khong rong hoan toan."""
    categories: list[str] = []
    subjects = item.get("subject")
    if isinstance(subjects, list):
        for subject in subjects:
            text = _clean_text(subject)
            if text and text not in categories:
                categories.append(text)
    if not categories:
        fallback = _first_non_empty([item.get("container-title"), item.get("type")])
        if fallback:
            categories.append(fallback)
    return categories


def _parse_pdf_url(item: dict) -> str:
    """Lay link PDF neu publisher cong bo trong `link`."""
    links = item.get("link")
    if not isinstance(links, list):
        return ""
    for link in links:
        if not isinstance(link, dict):
            continue
        content_type = _clean_text(link.get("content-type")).lower()
        url = _clean_text(link.get("URL"))
        if url and content_type == "application/pdf":
            return url
    for link in links:
        if isinstance(link, dict):
            url = _clean_text(link.get("URL"))
            if url:
                return url
    return ""


def _build_comment(item: dict) -> str:
    """Provenance ngan gon: loai tai lieu, journal, publisher, so trich dan."""
    bits = [
        _clean_text(item.get("type")),
        _first_non_empty([item.get("container-title"), item.get("short-container-title")]),
        _clean_text(item.get("publisher")),
    ]
    referenced = item.get("is-referenced-by-count")
    if isinstance(referenced, int):
        bits.append(f"cited-by={referenced}")
    return " | ".join(bit for bit in bits if bit)


def _paper_id_from_doi(doi: str) -> str:
    """DOI lowercase = stable id, truy vet nguoc ve source duoc ngay."""
    return _clean_text(doi).lower().removeprefix("https://doi.org/").removeprefix("http://dx.doi.org/")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref payload thanh list `PaperRecord` da chuan hoa.

    Record bi bo khi thieu DOI hoac thieu title - hai field nay la dieu kiene
    toi thieu de cleaning va evaluation lam viec ma khong phai doan du lieu.
    Duplicate DOI bi loai ngay tai day nen `paper_id` la unique.
    """
    if not isinstance(payload, dict):
        raise TypeError(f"Crossref payload must be a dict, got {type(payload).__name__}.")

    message = payload.get("message")
    if not isinstance(message, dict):
        raise ValueError("Crossref payload missing 'message' object - raw response co the bi loi.")

    items = message.get("items")
    if not isinstance(items, list):
        raise ValueError("Crossref payload missing 'message.items' list.")

    records: list[PaperRecord] = []
    seen_ids: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            continue

        paper_id = _paper_id_from_doi(item.get("DOI", ""))
        title = _clean_text(item.get("title"))
        if not paper_id or not title:
            continue
        if paper_id in seen_ids:
            continue

        summary = _clean_abstract(item.get("abstract"))
        published = _parse_published(item)
        categories = _parse_categories(item)

        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=summary,
                authors=_parse_author_names(item.get("author")),
                categories=categories,
                primary_category=categories[0] if categories else "",
                published=published,
                updated=_parse_updated(item),
                abs_url=_clean_text(item.get("URL")) or f"https://doi.org/{paper_id}",
                pdf_url=_parse_pdf_url(item),
                comment=_build_comment(item),
            )
        )
        seen_ids.add(paper_id)

    return records


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def _build_request_params(settings: Settings) -> dict[str, Any]:
    params: dict[str, Any] = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
        "sort": "issued",
        "order": "desc",
    }
    # Polite pool cua Crossref: co mailto thi duoc uu tien rate limit.
    mailto = os.getenv("CROSSREF_MAILTO", "").strip()
    if mailto:
        params["mailto"] = mailto
    return params


def _request_with_retry(url: str, params: dict[str, Any]) -> dict:
    """GET voi exponential backoff + jitter cho cac loi tam thoi (429/503/...)."""
    headers = {"User-Agent": "day10-data-observability-lab/0.1 (+https://api.crossref.org)"}
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as error:  # timeout, DNS, connection reset
            last_error = error
        else:
            if response.status_code == 200:
                return response.json()

            if response.status_code not in RETRYABLE_STATUS:
                raise RuntimeError(
                    f"Crossref request failed with status {response.status_code}: {response.text[:200]}"
                )

            last_error = RuntimeError(f"Crossref transient status {response.status_code}")
            retry_after = response.headers.get("Retry-After")
            if retry_after and attempt < MAX_ATTEMPTS:
                try:
                    time.sleep(min(float(retry_after), 30.0))
                    continue
                except ValueError:
                    pass

        if attempt < MAX_ATTEMPTS:
            delay = BACKOFF_BASE_SECONDS ** attempt + random.uniform(0, 0.5)
            print(f"[ingestion] attempt {attempt}/{MAX_ATTEMPTS} failed ({last_error}); retry sau {delay:.1f}s")
            time.sleep(delay)

    raise RuntimeError(f"Crossref request failed after {MAX_ATTEMPTS} attempts: {last_error}")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch tu Crossref, luu raw response truoc khi parse, roi luu raw records.

    Thu tu ghi file la co chu y: raw response duoc persist *truoc* buoc parse
    nen khi parsing sai ta van con snapshot goc de debug va repair.
    """
    params = _build_request_params(settings)
    payload = _request_with_retry(CROSSREF_API_URL, params)

    # 1) Snapshot nguyen ban - khong them/bot field nao.
    write_json(settings.paths.raw_api_response, payload)

    # 2) Parse sang schema noi bo.
    records = parse_crossref_payload(payload)
    if not records:
        raise RuntimeError(
            "Crossref tra ve 0 record hop le. Kiem tra lai source_query/source_filter truoc khi chay tiep."
        )

    # 3) Snapshot records + lineage metadata cho cac role phia sau.
    write_json(
        settings.paths.raw_records_json,
        {
            "source_api": settings.source_api,
            "endpoint": CROSSREF_API_URL,
            "request_params": {key: value for key, value in params.items() if key != "mailto"},
            "fetched_at": now_utc().isoformat(),
            "total_results_reported": payload.get("message", {}).get("total-results"),
            "items_in_response": len(payload.get("message", {}).get("items", []) or []),
            "record_count": len(records),
            "records": [asdict(record) for record in records],
        },
    )

    print(
        f"[ingestion] fetched {len(records)} records -> "
        f"{settings.paths.raw_records_json.name} (raw: {settings.paths.raw_api_response.name})"
    )
    return records


# ---------------------------------------------------------------------------
# Loading snapshot (repair path - khong goi API)
# ---------------------------------------------------------------------------


def _record_from_dict(data: dict) -> PaperRecord | None:
    paper_id = _paper_id_from_doi(data.get("paper_id") or data.get("DOI") or "")
    title = _clean_text(data.get("title"))
    if not paper_id or not title:
        return None

    categories = [_clean_text(value) for value in (data.get("categories") or []) if _clean_text(value)]
    authors = [_clean_text(value) for value in (data.get("authors") or []) if _clean_text(value)]

    return PaperRecord(
        paper_id=paper_id,
        title=title,
        summary=_clean_text(data.get("summary")),
        authors=authors,
        categories=categories,
        primary_category=_clean_text(data.get("primary_category")) or (categories[0] if categories else ""),
        published=_clean_text(data.get("published")),
        updated=_clean_text(data.get("updated")) or _clean_text(data.get("published")),
        abs_url=_clean_text(data.get("abs_url")) or f"https://doi.org/{paper_id}",
        pdf_url=_clean_text(data.get("pdf_url")),
        comment=_clean_text(data.get("comment")),
    )


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Doc raw snapshot tu disk va map ve `PaperRecord`.

    Chap nhan 3 dang file de repair luon chay duoc:
      - `{"records": [...]}` (dang chuan do `fetch_source_records` ghi ra)
      - `[...]` (list record thuan)
      - raw Crossref payload `{"message": {"items": [...]}}`
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Raw snapshot khong ton tai: {path}. Chay fetch_source_records truoc (REFRESH_SOURCE=1)."
        )

    payload = read_json(path)

    if isinstance(payload, dict) and "message" in payload:
        return parse_crossref_payload(payload)

    if isinstance(payload, dict):
        raw_records = payload.get("records")
    else:
        raw_records = payload

    if not isinstance(raw_records, list):
        raise ValueError(f"Raw snapshot {path} khong chua list records nao doc duoc.")

    records: list[PaperRecord] = []
    seen_ids: set[str] = set()
    for entry in raw_records:
        if not isinstance(entry, dict):
            continue
        record = _record_from_dict(entry)
        if record is None or record.paper_id in seen_ids:
            continue
        records.append(record)
        seen_ids.add(record.paper_id)

    if not records:
        raise ValueError(f"Raw snapshot {path} khong co record hop le nao (thieu paper_id/title).")

    return records
