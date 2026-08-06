#!/usr/bin/env python
"""Import lab-member activity rows exported from Google Sheets.

Publication rows contain only PubMed ID and/or DOI; this importer fetches PubMed
metadata after submission. Other activity types are imported from type-specific
Google Form sections.
"""
from __future__ import annotations

import argparse
import csv
import html
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR_DIR = ROOT / "markdown_generator"
ACTIVITIES_CSV = GENERATOR_DIR / "member_activity_records.csv"
MEMBERS_CSV = GENERATOR_DIR / "lab_members.csv"
IMAGES_DIR = ROOT / "images"

FIELDS = [
    "record_id", "member_ids", "member_names", "record_type", "title", "date", "date_display", "year",
    "venue", "location", "role", "authors", "citation", "doi", "url", "pubmed_id",
    "abstract_or_description", "image", "visibility", "featured", "source_file", "permalink", "notes_private",
]
ALLOWED_TYPES = {"publication", "talk", "invited_presentation", "public_outreach", "award", "application", "project"}
REQUIRED_BY_TYPE = {
    "publication": [],
    "talk": ["member_ids", "title", "date", "venue"],
    "invited_presentation": ["member_ids", "title", "date", "venue"],
    "public_outreach": ["member_ids", "title", "date", "venue"],
    "award": ["member_ids", "title", "date", "venue"],
    "application": ["member_ids", "title", "date", "venue"],
    "project": ["member_ids", "title", "date", "venue"],
}
COLUMN_ALIASES = {
    "timestamp": "timestamp",
    "submission id": "submission_id",
    "submission_id": "submission_id",
    "type": "record_type",
    "record_type": "record_type",
    "activity type": "record_type",
    "lab member ids": "member_ids",
    "member_ids": "member_ids",
    "member id(s)": "member_ids",
    "title": "title",
    "date": "date",
    "venue / journal / meeting": "venue",
    "venue": "venue",
    "meeting": "venue",
    "location": "location",
    "role / awardee / developer": "role",
    "role": "role",
    "awardee": "role",
    "developer": "role",
    "url": "url",
    "link": "url",
    "abstract / description": "abstract_or_description",
    "description": "abstract_or_description",
    "image": "image",
    "image url": "image",
    "image upload": "image",
    "image_upload": "image_upload",
    "image url or google drive upload": "image",
    "visibility": "visibility",
}
TYPE_ALIASES = {
    "talk / presentation": "talk",
    "talk": "talk",
    "presentation": "talk",
    "invited presentation": "invited_presentation",
    "invited_presentation": "invited_presentation",
    "public outreach": "public_outreach",
    "public_outreach": "public_outreach",
    "outreach": "public_outreach",
    "award": "award",
    "application": "application",
    "project": "project",
    "publication": "publication",
    "pubmed": "publication",
}
TYPE_PREFIXES = ("publication", "talk", "invited_presentation", "public_outreach", "award", "application", "project")
COMMON_SUFFIXES = ("member_ids", "title", "date", "venue", "location", "role", "url", "abstract_or_description", "image", "image_upload", "visibility", "pubmed_id", "doi", "authors", "citation")
EXTRA_MEMBER_NAMES = {"erik_van_den_akker": "Erik van den Akker"}
IMAGE_EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def clean(value: str) -> str:
    value = (value or "").strip()
    if value.lower() in {"_no response_", "no response", "nan", "none"}:
        return ""
    return value


def slugify(value: str) -> str:
    value = html.unescape(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-") or "record"


def normalize_header(header: str) -> str:
    key = re.sub(r"\s+", " ", (header or "").strip().lower())
    return COLUMN_ALIASES.get(key, key.replace(" ", "_"))


def normalize_type(value: str) -> str:
    key = clean(value).lower().replace("-", " ")
    key = re.sub(r"\s+", " ", key)
    return TYPE_ALIASES.get(key, key.replace(" ", "_"))

def value_for_type(sheet_row: dict[str, str], record_type: str, field: str, default: str = "") -> str:
    candidates = [f"{record_type}_{field}"]
    if record_type in {"talk", "invited_presentation", "public_outreach"}:
        candidates.append(f"talk_{field}")
    candidates.append(field)
    for key in candidates:
        value = sheet_row.get(key, "")
        if value:
            return value
    return default


def collapse_branch_row(sheet_row: dict[str, str]) -> dict[str, str]:
    record_type = normalize_type(sheet_row.get("record_type", ""))
    if not record_type:
        for prefix in TYPE_PREFIXES:
            if any(sheet_row.get(f"{prefix}_{suffix}", "") for suffix in COMMON_SUFFIXES):
                record_type = prefix
                break
    collapsed = dict(sheet_row)
    collapsed["record_type"] = record_type
    if record_type:
        for field in COMMON_SUFFIXES:
            collapsed[field] = value_for_type(sheet_row, record_type, field, collapsed.get(field, ""))
    image_upload = value_for_type(sheet_row, record_type, "image_upload", "") if record_type else ""
    if image_upload and not collapsed.get("image"):
        collapsed["image"] = image_upload
    return collapsed

def normalize_date(raw: str) -> tuple[str, str, str]:
    raw = clean(raw)
    if not raw:
        return "", "", ""
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%d %b %Y", "%d %B %Y", "%b %Y", "%B %Y", "%Y %b %d", "%Y %B %d", "%Y %b", "%Y %B", "%Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            if fmt == "%Y":
                return raw, raw, raw
            if fmt in {"%Y %b", "%Y %B", "%b %Y", "%B %Y"}:
                return dt.strftime("%Y-%m"), dt.strftime("%Y %b"), dt.strftime("%Y")
            return dt.strftime("%Y-%m-%d"), dt.strftime("%Y %b %d").replace(" 0", " "), dt.strftime("%Y")
        except ValueError:
            continue
    match = re.search(r"(19|20)\d{2}", raw)
    year = match.group(0) if match else ""
    return raw, raw, year


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_sheet_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for raw in reader:
            row = {normalize_header(key): clean(value) for key, value in raw.items() if key is not None}
            row = collapse_branch_row(row)
            if any(row.values()):
                rows.append(row)
        return rows

def normalize_member_ids(value: str) -> str:
    raw_parts = [part.strip() for part in re.split(r"[;,]", value or "") if part.strip()]
    ids = []
    for part in raw_parts:
        member_id = part.split("=", 1)[0].strip()
        member_id = member_id.strip("` ")
        if member_id:
            ids.append(member_id)
    return ";".join(ids) if ids else "lab"

def member_names(member_ids: str) -> str:
    members = {row["member_id"]: row["name"] for row in read_csv(MEMBERS_CSV)}
    members.update(EXTRA_MEMBER_NAMES)
    ids = [value.strip() for value in re.split(r"[;,]\s*", member_ids or "") if value.strip()]
    if not ids or ids == ["lab"]:
        return "Knevel Lab"
    return ";".join(members.get(member_id, member_id) for member_id in ids)


def next_record_id(record_type: str, title: str, existing: list[dict[str, str]]) -> str:
    prefix = {
        "talk": "talk",
        "invited_presentation": "talk",
        "public_outreach": "outreach",
        "award": "award",
        "application": "application",
        "project": "project",
        "publication": "pub",
    }.get(record_type, "record")
    base = f"{prefix}_{slugify(title)}"
    used = {row.get("record_id", "") for row in existing}
    if base not in used:
        return base
    idx = 2
    while f"{base}_{idx}" in used:
        idx += 1
    return f"{base}_{idx}"


def duplicate_record_id(values: dict[str, str], existing: list[dict[str, str]]) -> str:
    source_submission_id = values.get("submission_id", "").strip()
    title = values.get("title", "").strip().lower()
    date = values.get("date", "").strip()
    record_type = values.get("record_type", "")
    for row in existing:
        if source_submission_id and f"Google Sheet submission {source_submission_id}" in row.get("notes_private", ""):
            return row.get("record_id", "")
        if record_type and title and date and row.get("record_type") == record_type and row.get("title", "").strip().lower() == title and row.get("date", "").strip() == date:
            return row.get("record_id", "")
    return ""


def extract_drive_file_id(value: str) -> str:
    value = clean(value)
    patterns = [
        r"drive\.google\.com/file/d/([A-Za-z0-9_-]+)",
        r"drive\.google\.com/open\?id=([A-Za-z0-9_-]+)",
        r"drive\.google\.com/uc\?id=([A-Za-z0-9_-]+)",
        r"[?&]id=([A-Za-z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return ""


def first_url(value: str) -> str:
    match = re.search(r"https?://\S+", clean(value))
    return match.group(0).rstrip(")]>") if match else clean(value)


def request_json(url: str, token: str) -> dict:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        import json

        return json.loads(response.read().decode("utf-8"))


def download_drive_image(image_value: str, record_id: str, token: str) -> str:
    file_id = extract_drive_file_id(image_value)
    if not file_id or not token:
        return first_url(image_value)
    metadata_url = "https://www.googleapis.com/drive/v3/files/" + urllib.parse.quote(file_id) + "?fields=name,mimeType"
    metadata = request_json(metadata_url, token)
    mime_type = metadata.get("mimeType", "")
    original_name = metadata.get("name", "")
    ext = IMAGE_EXT_BY_MIME.get(mime_type) or Path(original_name).suffix.lower() or mimetypes.guess_extension(mime_type) or ".img"
    if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        raise ValueError(f"Google Drive file {file_id} is not a supported image: {mime_type or original_name}")
    filename = f"{record_id}{ext}"
    url = "https://www.googleapis.com/drive/v3/files/" + urllib.parse.quote(file_id) + "?alt=media"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(request, timeout=60) as response:
        (IMAGES_DIR / filename).write_bytes(response.read())
    return filename

def doi_to_pubmed_id(doi: str) -> str:
    doi = clean(doi)
    if not doi:
        return ""
    query = urllib.parse.urlencode({"db": "pubmed", "term": f"{doi}[AID]", "retmode": "xml"})
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + query
    request = urllib.request.Request(url, headers={"User-Agent": "KnevelLabWebsiteSheetImporter/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        root = ET.fromstring(response.read())
    return root.findtext(".//IdList/Id", default="").strip()


def pubmed_lookup(pubmed_id: str = "", doi: str = "") -> dict[str, str]:
    pubmed_id = re.sub(r"\D", "", pubmed_id or "")
    doi = clean(doi)
    if not pubmed_id and doi:
        pubmed_id = doi_to_pubmed_id(doi)
    if not pubmed_id:
        raise ValueError("Publication requires either PubMed ID or DOI that can be resolved in PubMed.")
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + urllib.parse.urlencode({"db": "pubmed", "id": pubmed_id, "retmode": "xml"})
    request = urllib.request.Request(url, headers={"User-Agent": "KnevelLabWebsiteSheetImporter/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        root = ET.fromstring(response.read())
    article = root.find(".//PubmedArticle")
    if article is None:
        raise ValueError(f"No PubMed article found for PMID {pubmed_id}.")
    title = " ".join("".join(article.findtext(".//ArticleTitle", default="").splitlines()).split())
    journal = article.findtext(".//Journal/ISOAbbreviation") or article.findtext(".//Journal/Title") or ""
    year = article.findtext(".//JournalIssue/PubDate/Year") or ""
    month = article.findtext(".//JournalIssue/PubDate/Month") or ""
    day = article.findtext(".//JournalIssue/PubDate/Day") or ""
    date, date_display, year_value = normalize_date(" ".join(part for part in (year, month, day) if part) or year)
    authors = []
    for author in article.findall(".//AuthorList/Author"):
        collective = author.findtext("CollectiveName")
        last = author.findtext("LastName")
        initials = author.findtext("Initials")
        if collective:
            authors.append(collective)
        elif last:
            authors.append(f"{last} {initials or ''}".strip())
    found_doi = ""
    for article_id in article.findall(".//ArticleIdList/ArticleId"):
        if article_id.attrib.get("IdType") == "doi":
            found_doi = (article_id.text or "").strip()
            break
    abstract = " ".join(" ".join(node.itertext()).strip() for node in article.findall(".//Abstract/AbstractText"))
    author_text = ", ".join(authors)
    citation = f'{author_text}. ({year_value}) "{title}" <i>{journal}.</i>'
    if found_doi:
        citation += f" doi: {found_doi}."
    return {
        "title": title,
        "date": date,
        "date_display": date_display,
        "year": year_value,
        "venue": journal,
        "authors": author_text,
        "citation": citation,
        "doi": found_doi or doi,
        "url": f"https://doi.org/{found_doi or doi}" if (found_doi or doi) else f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/",
        "pubmed_id": pubmed_id,
        "abstract_or_description": abstract,
    }


def infer_publication_member_ids(authors: str) -> str:
    author_text = " " + re.sub(r"[^a-z0-9]+", " ", (authors or "").lower()) + " "
    matched = []
    for member in read_csv(MEMBERS_CSV):
        name = member.get("name", "")
        parts = [part for part in re.split(r"\s+", name.lower()) if part]
        if len(parts) < 2:
            continue
        last = parts[-1]
        first_initial = parts[0][0]
        patterns = [
            f" {last} {first_initial} ",
            f" {last} {first_initial.upper().lower()}",
            f" {name.lower()} ",
        ]
        if any(pattern in author_text for pattern in patterns):
            matched.append(member.get("member_id", ""))
    return ";".join([member_id for member_id in matched if member_id]) or "lab"

def build_activity_row(sheet_row: dict[str, str], existing: list[dict[str, str]], token: str, download_images: bool) -> dict[str, str] | None:
    record_type = normalize_type(sheet_row.get("record_type", ""))
    if not record_type:
        return None
    if record_type not in ALLOWED_TYPES:
        raise ValueError(f"Unsupported record_type: {record_type}")
    values = {field: "" for field in FIELDS}
    if record_type == "publication":
        pubmed_id = sheet_row.get("pubmed_id", "")
        doi = sheet_row.get("doi", "")
        if not pubmed_id and not doi:
            raise ValueError("Publication requires PubMed ID or DOI.")
        values.update(pubmed_lookup(pubmed_id=pubmed_id, doi=doi))
        inferred_member_ids = infer_publication_member_ids(values.get("authors", ""))
        values.update({
            "record_type": "publication",
            "member_ids": inferred_member_ids,
            "member_names": member_names(inferred_member_ids),
            "visibility": sheet_row.get("visibility", "public") or "public",
        })
    else:
        date, date_display, year = normalize_date(sheet_row.get("date", ""))
        normalized_member_ids = normalize_member_ids(sheet_row.get("member_ids", "lab") or "lab")
        values.update({
            "record_type": record_type,
            "member_ids": normalized_member_ids,
            "member_names": member_names(normalized_member_ids),
            "title": sheet_row.get("title", ""),
            "date": date,
            "date_display": date_display,
            "year": year,
            "venue": sheet_row.get("venue", ""),
            "location": sheet_row.get("location", ""),
            "role": sheet_row.get("role", ""),
            "url": sheet_row.get("url", ""),
            "abstract_or_description": sheet_row.get("abstract_or_description", ""),
            "visibility": sheet_row.get("visibility", "public") or "public",
        })
    missing = [field for field in REQUIRED_BY_TYPE.get(record_type, []) if not values.get(field, "").strip()]
    if missing:
        raise ValueError(f"Missing required fields for {record_type}: " + ", ".join(missing))
    duplicate = duplicate_record_id({**sheet_row, **values}, existing)
    if duplicate:
        print(f"Skipping duplicate submission for {values['title']}: {duplicate}")
        return None
    record_id = next_record_id(record_type, values["title"], existing)
    values["record_id"] = record_id
    values["notes_private"] = "Google Sheet submission " + (sheet_row.get("submission_id") or sheet_row.get("timestamp") or record_id)
    image_value = sheet_row.get("image", "")
    if image_value:
        values["image"] = download_drive_image(image_value, record_id, token) if download_images else first_url(image_value)
    return values

def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheet-csv", required=True, help="CSV exported from the Google Sheet responses tab.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print rows without changing member_activity_records.csv.")
    parser.add_argument("--download-images", action="store_true", help="Download Google Drive image uploads into images/ when GOOGLE_ACCESS_TOKEN is available.")
    args = parser.parse_args()
    token = os.environ.get("GOOGLE_ACCESS_TOKEN", "")
    existing = read_csv(ACTIVITIES_CSV)
    additions = []
    for sheet_row in read_sheet_rows(Path(args.sheet_csv)):
        row = build_activity_row(sheet_row, existing + additions, token, args.download_images)
        if row:
            additions.append(row)
    if args.dry_run:
        print(f"Dry run: {len(additions)} new rows would be imported")
        for row in additions:
            print(f"- {row['record_id']} [{row['record_type']}]: {row['title']}")
        return
    if not additions:
        print("No new Google Sheet rows to import.")
        return
    write_csv(ACTIVITIES_CSV, existing + additions)
    print(f"Imported {len(additions)} Google Sheet rows into {ACTIVITIES_CSV}")


if __name__ == "__main__":
    main()
