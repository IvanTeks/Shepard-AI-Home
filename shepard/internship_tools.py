from __future__ import annotations

import html
import json
import re
import ssl
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


REMOTIVE_API = "https://remotive.com/api/remote-jobs"
SIMPLIFY_LISTINGS = (
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/"
    "dev/.github/scripts/listings.json"
)
MAX_RESUME_BYTES = 5 * 1024 * 1024
INTERNSHIP_WORDS = re.compile(
    r"\b(intern(?:ship)?|co[ -]?op|student (?:role|position|program)|summer analyst)\b",
    re.IGNORECASE,
)
TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.\-]{1,30}")
STOP_WORDS = {
    "about", "after", "also", "and", "are", "been", "before", "being", "but",
    "can", "from", "have", "into", "more", "our", "that", "the", "their", "them",
    "they", "this", "through", "using", "was", "were", "will", "with", "work", "your",
    "experience", "skills", "education", "university", "college", "student",
}


def _trusted_ssl_context() -> ssl.SSLContext:
    candidates = [
        ssl.get_default_verify_paths().cafile,
        "/etc/ssl/cert.pem",
        "/opt/homebrew/etc/openssl@3/cert.pem",
        "/usr/local/etc/openssl@3/cert.pem",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return ssl.create_default_context(cafile=candidate)
    return ssl.create_default_context()


def _clean_text(value: str) -> str:
    value = value.replace("\x00", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def extract_resume_text(filename: str, payload: bytes) -> str:
    """Extract owner-readable text from a small local DOCX/TXT/MD résumé."""
    if not payload:
        raise ValueError("The résumé file is empty")
    if len(payload) > MAX_RESUME_BYTES:
        raise ValueError("Résumé uploads are limited to 5 MB")
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix in {".txt", ".md"}:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            text = payload.decode("utf-8-sig")
    elif suffix == ".docx":
        try:
            with zipfile.ZipFile(BytesIO(payload)) as archive:
                xml = archive.read("word/document.xml")
        except (KeyError, zipfile.BadZipFile) as exc:
            raise ValueError("That file is not a readable DOCX résumé") from exc
        try:
            root = ElementTree.fromstring(xml)
        except ElementTree.ParseError as exc:
            raise ValueError("The DOCX document text could not be read") from exc
        paragraphs: list[str] = []
        for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
            parts = [
                node.text or ""
                for node in paragraph.iter(
                    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
                )
            ]
            joined = "".join(parts).strip()
            if joined:
                paragraphs.append(joined)
        text = "\n".join(paragraphs)
    else:
        raise ValueError("Upload a DOCX, TXT, or Markdown résumé")
    text = _clean_text(text)
    if len(text) < 80:
        raise ValueError("The résumé did not contain enough readable text")
    return text[:50_000]


def split_labels(value: str, *, limit: int = 12) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for raw in re.split(r"[,;|]", value):
        item = raw.strip().strip("-•")
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            items.append(item[:100])
        if len(items) >= limit:
            break
    return items


def fallback_search_terms(resume_text: str, *, limit: int = 8) -> list[str]:
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for token in TOKEN_PATTERN.findall(resume_text):
        key = token.casefold().strip(".-")
        if len(key) < 3 or key in STOP_WORDS or key.isdigit():
            continue
        counts[key] = counts.get(key, 0) + 1
        labels.setdefault(key, token)
    ordered = sorted(counts, key=lambda item: (-counts[item], item))
    return [labels[item] for item in ordered[:limit]]


class _HTMLTextParser:
    @staticmethod
    def extract(value: str) -> str:
        value = re.sub(r"(?is)<(?:script|style).*?>.*?</(?:script|style)>", " ", value)
        value = re.sub(r"(?s)<[^>]+>", " ", value)
        return _clean_text(html.unescape(value))


def fetch_remotive_jobs(query: str, *, timeout: int = 30) -> list[dict[str, Any]]:
    url = REMOTIVE_API + "?" + urllib.parse.urlencode({"search": query, "limit": 50})
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "Shepard-Local/0.1 (+owner-controlled internship search)",
        },
    )
    with urllib.request.urlopen(
        request, timeout=timeout, context=_trusted_ssl_context()
    ) as response:
        payload = json.loads(response.read().decode("utf-8"))
    raw_jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    if not isinstance(raw_jobs, list):
        raise ValueError("Remotive returned an unexpected response")
    jobs: list[dict[str, Any]] = []
    for item in raw_jobs:
        if not isinstance(item, dict):
            continue
        url_value = str(item.get("url", "")).strip()
        title = str(item.get("title", "")).strip()
        if not url_value.startswith("https://") or not title:
            continue
        description = _HTMLTextParser.extract(str(item.get("description", "")))[:30_000]
        jobs.append({
            "url": url_value,
            "title": title[:300],
            "company": str(item.get("company_name", "Company not identified")).strip()[:200],
            "location": str(item.get("candidate_required_location", "Remote")).strip()[:200],
            "description": description,
            "publication_date": str(item.get("publication_date", "")).strip()[:50],
            "salary": str(item.get("salary", "")).strip()[:200],
            "job_type": str(item.get("job_type", "")).strip()[:80],
            "source": "Remotive",
        })
    return jobs


def fetch_simplify_internships(*, timeout: int = 30, limit: int = 750) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        SIMPLIFY_LISTINGS,
        headers={
            "Accept": "application/json",
            "User-Agent": "Shepard-Local/0.1 (+owner-controlled internship search)",
        },
    )
    with urllib.request.urlopen(
        request, timeout=timeout, context=_trusted_ssl_context()
    ) as response:
        raw = response.read(64_000_001)
    if len(raw) > 64_000_000:
        raise ValueError("The SimplifyJobs internship feed was unexpectedly large")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("SimplifyJobs returned an unexpected response")
    active = [
        item for item in payload
        if isinstance(item, dict)
        and item.get("active") is True
        and item.get("is_visible", True) is True
        and str(item.get("url", "")).startswith("https://")
    ]
    active.sort(
        key=lambda item: int(item.get("date_updated") or item.get("date_posted") or 0),
        reverse=True,
    )
    jobs: list[dict[str, Any]] = []
    for item in active[:limit]:
        title = str(item.get("title", "")).strip()
        company = str(item.get("company_name", "Company not identified")).strip()
        locations = item.get("locations", [])
        location = ", ".join(str(value) for value in locations) if isinstance(locations, list) else str(locations)
        if not title:
            continue
        jobs.append({
            "url": str(item["url"]),
            "title": title[:300],
            "company": company[:200],
            "location": location[:200],
            "description": f"{title} internship opportunity at {company}. Locations: {location}",
            "publication_date": str(item.get("date_posted", "")),
            "salary": "",
            "job_type": "internship",
            "source": "SimplifyJobs / Pitt CSC",
        })
    return jobs


def score_internship(
    job: dict[str, Any],
    *,
    resume_text: str,
    search_terms: list[str],
    location: str = "",
) -> tuple[int, str] | None:
    title = str(job.get("title", ""))
    description = str(job.get("description", ""))
    combined = f"{title}\n{description}".casefold()
    source = str(job.get("source", ""))
    if not INTERNSHIP_WORDS.search(combined) and "SimplifyJobs" not in source:
        return None
    terms = search_terms or fallback_search_terms(resume_text)
    matched = [term for term in terms if term.casefold() in combined]
    title_matches = [term for term in matched if term.casefold() in title.casefold()]
    resume_tokens = {
        token.casefold().strip(".-") for token in TOKEN_PATTERN.findall(resume_text)
        if len(token) >= 3 and token.casefold().strip(".-") not in STOP_WORDS
    }
    job_tokens = {
        token.casefold().strip(".-") for token in TOKEN_PATTERN.findall(combined)
        if len(token) >= 3 and token.casefold().strip(".-") not in STOP_WORDS
    }
    overlap = len(resume_tokens & job_tokens)
    score = 38 + min(28, len(matched) * 5) + min(12, len(title_matches) * 4) + min(12, overlap // 2)
    if "SimplifyJobs" in source:
        score += 10
    if location and location.casefold() in str(job.get("location", "")).casefold():
        score += 6
    score = max(0, min(100, score))
    evidence = ", ".join(matched[:6]) or "general résumé vocabulary"
    summary = (
        f"Active Scout preliminary score: {score}/100. Matched signals: {evidence}. "
        f"This is a local keyword ranking, not the full five-Sheep review. Source: {source or 'public job feed'}."
    )
    return score, summary
