#!/usr/bin/env python
"""Local form server for editing member_activity_records.csv."""
from __future__ import annotations

import csv
import html
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR_DIR = ROOT / "markdown_generator"
ACTIVITIES_CSV = GENERATOR_DIR / "member_activity_records.csv"
MEMBERS_CSV = GENERATOR_DIR / "lab_members.csv"
IMAGES_DIR = ROOT / "images"
BACKUP_DIR = GENERATOR_DIR / "form_backups"
HOST = "127.0.0.1"
PORT = 8765
FIELDS = ["record_id", "member_ids", "member_names", "record_type", "title", "date", "date_display", "year", "venue", "location", "role", "authors", "citation", "doi", "url", "pubmed_id", "abstract_or_description", "image", "visibility", "featured", "source_file", "permalink", "notes_private"]
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
REQUIRED_BY_TYPE = {
    "publication": ["title", "date", "venue", "authors", "citation", "pubmed_id"],
    "talk": ["title", "date", "venue"],
    "invited_presentation": ["title", "date", "venue"],
    "public_outreach": ["title", "date", "venue"],
    "award": ["title", "date", "role", "member_ids", "image_file"],
    "application": ["title", "url", "abstract_or_description", "image_file"],
    "project": ["title", "url", "abstract_or_description", "image_file"],
}


def slugify(value: str) -> str:
    value = html.unescape(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-") or "record"


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def members() -> list[dict[str, str]]:
    return read_rows(MEMBERS_CSV)


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


def next_record_id(record_type: str, title: str, existing: list[dict[str, str]]) -> str:
    prefix = {"publication": "pub", "talk": "talk", "invited_presentation": "talk", "public_outreach": "outreach", "award": "award", "application": "application", "project": "project"}.get(record_type, "record")
    base = f"{prefix}_{slugify(title)}"
    used = {row.get("record_id", "") for row in existing}
    if base not in used:
        return base
    idx = 2
    while f"{base}_{idx}" in used:
        idx += 1
    return f"{base}_{idx}"


def parse_multipart(handler: BaseHTTPRequestHandler) -> tuple[dict[str, list[str]], dict[str, tuple[str, bytes]]]:
    length = int(handler.headers.get("Content-Length", "0"))
    content_type = handler.headers.get("Content-Type", "")
    body = handler.rfile.read(length)
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode("utf-8") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    )
    fields: dict[str, list[str]] = {}
    files: dict[str, tuple[str, bytes]] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename:
            files[name] = (Path(filename).name, payload)
        else:
            charset = part.get_content_charset() or "utf-8"
            fields.setdefault(name, []).append(payload.decode(charset, errors="replace"))
    return fields, files


def first(fields: dict[str, list[str]], key: str, default: str = "") -> str:
    values = fields.get(key)
    return values[0] if values else default


def missing_required_fields(record_type: str, fields: dict[str, list[str]], files: dict[str, tuple[str, bytes]]) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_BY_TYPE.get(record_type, []):
        if field == "image_file":
            file_item = files.get("image_file")
            existing_image = first(fields, "image").strip()
            if not existing_image and (not file_item or not file_item[0] or not file_item[1]):
                missing.append(field)
        elif field == "member_ids":
            if not fields.get("member_ids"):
                missing.append(field)
        elif not first(fields, field).strip():
            missing.append(field)
    return missing


def save_image(file_item: tuple[str, bytes] | None, record_id: str) -> str:
    if not file_item or not file_item[0] or not file_item[1]:
        return ""
    original, payload = file_item
    ext = Path(original).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Image must be jpg, jpeg, png, gif, or webp.")
    filename = f"{record_id}{ext}"
    (IMAGES_DIR / filename).write_bytes(payload)
    return filename


def pubmed_lookup(pmid: str) -> dict[str, str]:
    pmid = re.sub(r"\D", "", pmid or "")
    if not pmid:
        raise ValueError("PMID is required.")
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + urllib.parse.urlencode({"db": "pubmed", "id": pmid, "retmode": "xml"})
    req = urllib.request.Request(url, headers={"User-Agent": "KnevelLabWebsiteForm/1.0"})
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
    return {"title": title, "date": date, "date_display": date_display, "year": year_value, "venue": journal, "authors": author_text, "citation": citation, "doi": doi, "url": f"https://doi.org/{doi}" if doi else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "pubmed_id": pmid, "abstract_or_description": abstract}


class Handler(BaseHTTPRequestHandler):
    def send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.startswith("/api/members"):
            self.send_json(200, {"members": members()})
            return
        if self.path.startswith("/api/pubmed"):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                self.send_json(200, {"ok": True, "article": pubmed_lookup(params.get("pmid", [""])[0])})
            except Exception as exc:
                self.send_json(400, {"ok": False, "error": str(exc)})
            return
        body = (GENERATOR_DIR / "activity_form.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/api/save":
            self.send_json(404, {"ok": False, "error": "Not found"})
            return
        fields, files = parse_multipart(self)
        rows = read_rows(ACTIVITIES_CSV)
        record_type = first(fields, "record_type").strip()
        title = first(fields, "title").strip()
        if not record_type or not title:
            self.send_json(400, {"ok": False, "error": "Type and title are required."})
            return
        missing = missing_required_fields(record_type, fields, files)
        if missing:
            self.send_json(400, {"ok": False, "error": "Missing required fields: " + ", ".join(missing)})
            return
        record_id = first(fields, "record_id").strip() or next_record_id(record_type, title, rows)
        date, date_display, year = normalize_date(first(fields, "date").strip())
        selected_members = fields.get("member_ids", [])
        names_by_id = {row["member_id"]: row["name"] for row in members()}
        try:
            image_name = save_image(files.get("image_file"), record_id)
        except Exception as exc:
            self.send_json(400, {"ok": False, "error": str(exc)})
            return
        row = {field: first(fields, field).strip() for field in FIELDS}
        row.update({
            "record_id": record_id,
            "member_ids": ";".join(selected_members) or "lab",
            "member_names": ";".join(names_by_id.get(member_id, member_id) for member_id in selected_members) or "Knevel Lab",
            "date": date,
            "date_display": first(fields, "date_display").strip() or date_display,
            "year": first(fields, "year").strip() or year,
            "image": image_name or first(fields, "image").strip(),
            "visibility": first(fields, "visibility", "public").strip() or "public",
        })
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ACTIVITIES_CSV, BACKUP_DIR / f"member_activity_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        rows = [existing for existing in rows if existing.get("record_id") != record_id]
        rows.append(row)
        write_rows(ACTIVITIES_CSV, rows)
        result = subprocess.run([sys.executable, str(GENERATOR_DIR / "generate_site_content.py"), "--check", "--generate-site"], cwd=ROOT, text=True, capture_output=True)
        if result.returncode != 0:
            self.send_json(500, {"ok": False, "error": result.stderr or result.stdout})
            return
        self.send_json(200, {"ok": True, "record_id": record_id, "image": row["image"], "output": result.stdout})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Open http://{HOST}:{PORT}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
