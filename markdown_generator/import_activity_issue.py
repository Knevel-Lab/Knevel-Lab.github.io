#!/usr/bin/env python
"""Import a GitHub Issue Form submission into member_activity_records.csv."""
from __future__ import annotations

import argparse
import csv
import html
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR_DIR = ROOT / "markdown_generator"
ACTIVITIES_CSV = GENERATOR_DIR / "member_activity_records.csv"
MEMBERS_CSV = GENERATOR_DIR / "lab_members.csv"

FIELDS = [
    "record_id", "member_ids", "member_names", "record_type", "title", "date", "date_display", "year",
    "venue", "location", "role", "authors", "citation", "doi", "url", "pubmed_id",
    "abstract_or_description", "image", "visibility", "featured", "source_file", "permalink", "notes_private",
]
LABEL_TO_FIELD = {
    "Type": "record_type",
    "Lab member IDs": "member_ids",
    "Title": "title",
    "Date": "date",
    "Venue / journal / meeting": "venue",
    "Location": "location",
    "Role / awardee / developer": "role",
    "PubMed ID": "pubmed_id",
    "DOI": "doi",
    "URL": "url",
    "Authors": "authors",
    "Citation": "citation",
    "Abstract / description": "abstract_or_description",
    "Image URL or GitHub attachment URL": "image",
    "Visibility": "visibility",
}
REQUIRED_BY_TYPE = {
    "publication": ["title", "date", "venue", "authors", "citation", "pubmed_id"],
    "talk": ["title", "date", "venue"],
    "invited_presentation": ["title", "date", "venue"],
    "public_outreach": ["title", "date", "venue"],
    "award": ["title", "date", "role", "member_ids"],
    "application": ["title", "url", "abstract_or_description"],
    "project": ["title", "url", "abstract_or_description"],
}


def clean_value(value: str) -> str:
    value = (value or "").strip()
    if value in {"_No response_", "No response"}:
        return ""
    return value


def slugify(value: str) -> str:
    value = html.unescape(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-") or "record"


def normalize_date(raw: str) -> tuple[str, str, str]:
    raw = (raw or "").strip()
    if not raw:
        return "", "", ""
    for fmt in ("%Y-%m-%d", "%Y %b %d", "%Y %B %d", "%Y %b", "%Y %B", "%Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            if fmt == "%Y":
                return raw, raw, raw
            if fmt in {"%Y %b", "%Y %B"}:
                return dt.strftime("%Y-%m"), dt.strftime("%Y %b"), dt.strftime("%Y")
            return dt.strftime("%Y-%m-%d"), dt.strftime("%Y %b %d").replace(" 0", " "), dt.strftime("%Y")
        except ValueError:
            continue
    match = re.search(r"(19|20)\d{2}", raw)
    year = match.group(0) if match else ""
    return raw, raw, year


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_issue_body(body: str) -> dict[str, str]:
    values: dict[str, str] = {}
    matches = list(re.finditer(r"^###\s+(.+?)\s*$", body or "", flags=re.M))
    for index, match in enumerate(matches):
        label = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        field = LABEL_TO_FIELD.get(label)
        if field:
            values[field] = clean_value(body[start:end])
    return values


def pubmed_lookup(pmid: str) -> dict[str, str]:
    pmid = re.sub(r"\D", "", pmid or "")
    if not pmid:
        return {}
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + urllib.parse.urlencode({"db": "pubmed", "id": pmid, "retmode": "xml"})
    req = urllib.request.Request(url, headers={"User-Agent": "KnevelLabWebsiteIssueImporter/1.0"})
    with urllib.request.urlopen(req, timeout=20) as response:
        root = ET.fromstring(response.read())
    article = root.find(".//PubmedArticle")
    if article is None:
        raise ValueError(f"No PubMed article found for PMID {pmid}.")
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
    doi = ""
    for article_id in article.findall(".//ArticleIdList/ArticleId"):
        if article_id.attrib.get("IdType") == "doi":
            doi = (article_id.text or "").strip()
            break
    abstract = " ".join(" ".join(node.itertext()).strip() for node in article.findall(".//Abstract/AbstractText"))
    author_text = ", ".join(authors)
    citation = f'{author_text}. ({year_value}) "{title}" <i>{journal}.</i>'
    if doi:
        citation += f" doi: {doi}."
    return {
        "title": title,
        "date": date,
        "date_display": date_display,
        "year": year_value,
        "venue": journal,
        "authors": author_text,
        "citation": citation,
        "doi": doi,
        "url": f"https://doi.org/{doi}" if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "pubmed_id": pmid,
        "abstract_or_description": abstract,
    }

def existing_duplicate(values: dict[str, str], existing: list[dict[str, str]]) -> str:
    record_type = values.get("record_type", "").strip()
    pubmed_id = values.get("pubmed_id", "").strip()
    doi = values.get("doi", "").strip().lower()
    title = values.get("title", "").strip().lower()
    date = values.get("date", "").strip()
    for row in existing:
        if row.get("record_type") != record_type:
            continue
        if pubmed_id and row.get("pubmed_id", "").strip() == pubmed_id:
            return row.get("record_id", "")
        if doi and row.get("doi", "").strip().lower() == doi:
            return row.get("record_id", "")
        if title and date and row.get("title", "").strip().lower() == title and row.get("date", "").strip() == date:
            return row.get("record_id", "")
    return ""

def next_record_id(record_type: str, title: str, existing: list[dict[str, str]]) -> str:
    prefix = {
        "publication": "pub",
        "talk": "talk",
        "invited_presentation": "talk",
        "public_outreach": "outreach",
        "award": "award",
        "application": "application",
        "project": "project",
    }.get(record_type, "record")
    base = f"{prefix}_{slugify(title)}"
    used = {row.get("record_id", "") for row in existing}
    if base not in used:
        return base
    idx = 2
    while f"{base}_{idx}" in used:
        idx += 1
    return f"{base}_{idx}"


def member_names(member_ids: str) -> str:
    members = {row["member_id"]: row["name"] for row in read_rows(MEMBERS_CSV)}
    ids = [value.strip() for value in re.split(r"[;,]\s*", member_ids or "") if value.strip()]
    if not ids or ids == ["lab"]:
        return "Knevel Lab"
    return ";".join(members.get(member_id, member_id) for member_id in ids)


def normalize_image(value: str) -> str:
    value = clean_value(value)
    match = re.search(r"https?://\S+", value)
    return match.group(0).rstrip(")]") if match else value


def build_row(values: dict[str, str], issue_number: str) -> dict[str, str]:
    record_type = values.get("record_type", "").strip()
    if record_type == "Publication":
        record_type = "publication"
    if record_type == "Talk / presentation":
        record_type = "talk"
    values["record_type"] = record_type
    if record_type == "publication" and values.get("pubmed_id"):
        for key, value in pubmed_lookup(values["pubmed_id"]).items():
            values.setdefault(key, value)
            if not values[key]:
                values[key] = value
    date, date_display, year = normalize_date(values.get("date", ""))
    values.setdefault("date_display", date_display)
    values.setdefault("year", year)
    values["date"] = date
    values["image"] = normalize_image(values.get("image", ""))
    values["visibility"] = values.get("visibility", "public") or "public"
    values["member_ids"] = values.get("member_ids", "lab") or "lab"
    values["member_names"] = member_names(values["member_ids"])
    existing = read_rows(ACTIVITIES_CSV)
    duplicate = existing_duplicate(values, existing)
    if duplicate:
        raise ValueError(f"This submission appears to already exist as {duplicate}.")
    record_id = next_record_id(record_type, values.get("title", ""), existing)
    row = {field: "" for field in FIELDS}
    row.update(values)
    row.update({"record_id": record_id, "notes_private": f"Imported from GitHub issue #{issue_number}"})
    missing = [field for field in REQUIRED_BY_TYPE.get(record_type, []) if not row.get(field, "").strip()]
    if missing:
        raise ValueError("Missing required fields: " + ", ".join(missing))
    return row


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue-number", default=os.environ.get("ISSUE_NUMBER", ""))
    parser.add_argument("--issue-body-file")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.issue_body_file:
        body = Path(args.issue_body_file).read_text(encoding="utf-8-sig")
    else:
        body = os.environ.get("ISSUE_BODY", "")
    if not body.strip():
        raise SystemExit("Issue body is empty. Pass --issue-body-file for local testing or set ISSUE_BODY in Actions.")
    values = parse_issue_body(body)
    row = build_row(values, args.issue_number or "local")
    if args.dry_run:
        print(f"Dry run parsed {row['record_id']} from issue #{args.issue_number or 'local'}")
        for field in FIELDS:
            if row.get(field):
                print(f"{field}: {row[field]}")
        return
    rows = [existing for existing in read_rows(ACTIVITIES_CSV) if existing.get("record_id") != row["record_id"]]
    rows.append(row)
    write_rows(ACTIVITIES_CSV, rows)
    print(f"Imported {row['record_id']} from issue #{args.issue_number or 'local'}")


if __name__ == "__main__":
    main()
