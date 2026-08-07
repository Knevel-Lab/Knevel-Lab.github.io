#!/usr/bin/env python
"""Generate website content from lab-member-maintained CSV files.

This script intentionally uses only the Python standard library so the workflow
can run in GitHub Actions without extra dependency setup.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_DIR = ROOT / "markdown_generator"
ACTIVITIES_CSV = GENERATOR_DIR / "member_activity_records.csv"
MEMBERS_CSV = GENERATOR_DIR / "lab_members.csv"
PREVIEW_DIR = GENERATOR_DIR / "generated_preview"
BACKUP_DIR = GENERATOR_DIR / "hardcoded_backup"

ACTIVITY_FIELDS = [
    "record_id",
    "member_ids",
    "member_names",
    "record_type",
    "title",
    "date",
    "date_display",
    "year",
    "venue",
    "location",
    "role",
    "authors",
    "citation",
    "doi",
    "url",
    "pubmed_id",
    "abstract_or_description",
    "image",
    "visibility",
    "featured",
    "source_file",
    "permalink",
    "notes_private",
]

MEMBER_FIELDS = [
    "member_id",
    "name",
    "status",
    "bio",
    "image",
    "linkedin",
    "github",
    "pubmed",
    "orcid",
    "google_scholar",
    "researchgate",
    "blog",
    "source_file",
]

TYPE_TO_COLLECTION = {
    "publication": "publications",
    "talk": "talks",
    "invited_presentation": "talks",
    "public_outreach": "talks",
}


@dataclass
class FrontMatterDoc:
    frontmatter: dict[str, str]
    body: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def slugify(value: str) -> str:
    value = html.unescape(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "record"


def strip_wrapping_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


def parse_frontmatter(path: Path) -> FrontMatterDoc:
    text = read_text(path)
    if not text.startswith("---"):
        return FrontMatterDoc({}, text)
    parts = text.split("---", 2)
    if len(parts) < 3:
        return FrontMatterDoc({}, text)
    raw_fm = parts[1]
    body = parts[2].lstrip("\r\n")
    data: dict[str, str] = {}
    for line in raw_fm.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = strip_wrapping_quotes(value.strip())
    return FrontMatterDoc(data, body)


def yaml_scalar(value: str) -> str:
    escaped = (value or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def frontmatter_block(values: dict[str, str]) -> str:
    lines = ["---"]
    for key, value in values.items():
        if value == "":
            continue
        if key in {"collection", "date"}:
            lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


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
            return dt.strftime("%Y-%m-%d"), dt.strftime("%Y %b %-d").replace(" 0", " "), dt.strftime("%Y")
        except ValueError:
            continue
    match = re.search(r"(19|20)\d{2}", raw)
    year = match.group(0) if match else ""
    return raw, raw, year


def jekyll_date_value(row: dict[str, str]) -> str:
    normalized, _display, year = normalize_date(row.get("date") or row.get("date_display") or row.get("year", ""))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        return normalized
    if re.fullmatch(r"\d{4}-\d{2}", normalized):
        return f"{normalized}-01"
    if re.fullmatch(r"\d{4}", normalized):
        return f"{normalized}-01-01"
    if year:
        return f"{year}-01-01"
    return ""


def date_display_value(row: dict[str, str]) -> str:
    raw_date = (row.get("date") or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date):
        return ""
    raw = row.get("date_display") or row.get("date") or row.get("year", "")
    normalized, display, _year = normalize_date(raw)
    if re.fullmatch(r"\d{4}(-\d{2})?$", normalized):
        return display
    return ""


def first_markdown_link(body: str) -> str:
    match = re.search(r"\[[^\]]+\]\(([^)]+)\)", body or "")
    return match.group(1).strip() if match else ""


def first_html_link(body: str) -> str:
    match = re.search(r"<a\s+href=['\"]([^'\"]+)['\"]", body or "", re.I)
    return match.group(1).strip() if match else ""


def clean_body_description(body: str) -> str:
    body = re.sub(r"Recommended citation:.*", "", body or "", flags=re.S).strip()
    body = re.sub(r"<a\s+href=['\"][^'\"]+['\"]>.*?</a>", "", body, flags=re.I | re.S)
    body = re.sub(r"\[[^\]]+\]\([^)]+\)", "", body)
    return re.sub(r"\s+", " ", body).strip()


def doi_from_url(url: str) -> str:
    match = re.search(r"10\.\d{4,9}/\S+", url or "")
    if not match:
        return ""
    return match.group(0).rstrip(").,;")


def split_semicolon(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def extract_group_members() -> list[dict[str, str]]:
    path = ROOT / "_pages" / "group.html"
    if not path.exists():
        return []
    text = read_text(path)
    members: list[dict[str, str]] = []
    current_status = "current"
    chunks = re.split(r"(?=<h3>|<div style=\"height: 150px;\">)", text)
    for chunk in chunks:
        if "<h3>Affiliated Members</h3>" in chunk:
            current_status = "affiliated"
            continue
        if "<h3>Alumni</h3>" in chunk:
            current_status = "alumni"
            continue
        if "<h2>" not in chunk:
            continue
        name_match = re.search(r"<h2>(.*?)</h2>", chunk, re.S)
        img_match = re.search(r"<img src=\"/images/([^\"]+)\"", chunk)
        alt_match = re.search(r"alt=\"([^\"]+)\"", chunk)
        if not name_match:
            continue
        name = html.unescape(re.sub(r"<.*?>", "", name_match.group(1)).strip())
        member_id = slugify(name).replace("-", "_")
        image = img_match.group(1).strip() if img_match else ""
        bio_part = chunk.split("</h2>", 1)[1] if "</h2>" in chunk else ""
        bio_part = bio_part.split("<br>", 1)[0]
        bio = html.unescape(re.sub(r"<.*?>", "", bio_part).strip())
        links = {
            "linkedin": "",
            "github": "",
            "pubmed": "",
            "orcid": "",
            "google_scholar": "",
            "researchgate": "",
            "blog": "",
        }
        for href, label in re.findall(r"<a href=\"([^\"]+)\">.*?</i>\s*([^<]+)</a>", chunk, re.S):
            key = label.strip().lower().replace(" ", "_")
            if key == "google_scholar":
                links["google_scholar"] = href
            elif key == "researchgate":
                links["researchgate"] = href
            elif key == "blog":
                links["blog"] = href
            elif key in links:
                links[key] = href
        members.append(
            {
                "member_id": member_id,
                "name": alt_match.group(1).strip() if alt_match else name,
                "status": current_status,
                "bio": bio,
                "image": image,
                "linkedin": links["linkedin"],
                "github": links["github"],
                "pubmed": links["pubmed"],
                "orcid": links["orcid"],
                "google_scholar": links["google_scholar"],
                "researchgate": links["researchgate"],
                "blog": links["blog"],
                "source_file": "_pages/group.html",
            }
        )
    return dedupe_members(members)


def dedupe_members(members: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for member in members:
        if member["member_id"] in seen:
            continue
        seen.add(member["member_id"])
        result.append(member)
    return result


def member_aliases(members: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    aliases: dict[str, dict[str, str]] = {}
    for member in members:
        name = member["name"]
        aliases[name.lower()] = member
        parts = re.split(r"\s+", name)
        if len(parts) >= 2:
            first = parts[0]
            last = parts[-1]
            aliases[f"{last} {first[0]}".lower()] = member
            aliases[f"{last}, {first}".lower()] = member
            aliases[f"{first} {last}".lower()] = member
    aliases["ling qing"] = next((m for m in members if m["name"].lower() == "ling qing"), {})
    aliases["qin l"] = aliases.get("ling qing", {})
    return {k: v for k, v in aliases.items() if v}


def infer_members(text: str, members: list[dict[str, str]]) -> tuple[str, str]:
    haystack = html.unescape(text or "").lower()
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for alias, member in member_aliases(members).items():
        if alias and alias in haystack and member["member_id"] not in seen:
            found.append(member)
            seen.add(member["member_id"])
    return ";".join(m["member_id"] for m in found), ";".join(m["name"] for m in found)


def publication_records(members: list[dict[str, str]]) -> list[dict[str, str]]:
    records = []
    for path in sorted((ROOT / "_publications").glob("*.md")):
        doc = parse_frontmatter(path)
        fm = doc.frontmatter
        title = fm.get("title", "")
        date, date_display, year = normalize_date(fm.get("date", ""))
        url = fm.get("paperurl", "") or first_html_link(doc.body)
        citation = fm.get("citation", "")
        member_ids, member_names = infer_members(" ".join([title, citation]), members)
        record_id = f"pub_{slugify(path.stem)}"
        records.append(
            activity_template(
                record_id=record_id,
                record_type="publication",
                title=title,
                date=date,
                date_display=date_display,
                year=year,
                venue=fm.get("venue", ""),
                role="author",
                authors="",
                citation=citation,
                doi=doi_from_url(url),
                url=url,
                abstract_or_description=fm.get("excerpt", "") or clean_body_description(doc.body),
                visibility="public",
                source_file=str(path.relative_to(ROOT)).replace("\\", "/"),
                permalink=fm.get("permalink", ""),
                member_ids=member_ids or "lab",
                member_names=member_names or "Knevel Lab",
            )
        )
    return records


def talk_records(members: list[dict[str, str]]) -> list[dict[str, str]]:
    records = []
    for path in sorted((ROOT / "_talks").glob("*.md")):
        doc = parse_frontmatter(path)
        fm = doc.frontmatter
        title = fm.get("title", "")
        date, date_display, year = normalize_date(fm.get("date", ""))
        role = fm.get("type", "")
        url = first_markdown_link(doc.body) or first_html_link(doc.body)
        member_ids, member_names = infer_members(" ".join([title, role, doc.body]), members)
        record_type = "invited_presentation" if "invited" in role.lower() else "talk"
        records.append(
            activity_template(
                record_id=f"talk_{slugify(path.stem)}",
                record_type=record_type,
                title=title,
                date=date,
                date_display=date_display,
                year=year,
                venue=fm.get("venue", ""),
                location=fm.get("location", ""),
                role=role,
                url=url,
                abstract_or_description=clean_body_description(doc.body),
                visibility="public",
                source_file=str(path.relative_to(ROOT)).replace("\\", "/"),
                permalink=fm.get("permalink", ""),
                member_ids=member_ids or "lab",
                member_names=member_names or "Knevel Lab",
            )
        )
    return records


def award_records(members: list[dict[str, str]]) -> list[dict[str, str]]:
    path = ROOT / "_pages" / "awards.html"
    if not path.exists():
        return []
    text = read_text(path)
    blocks = re.findall(r"<div style=\"height: auto;\">(.*?)</div>", text, re.S)
    records = []
    for idx, block in enumerate(blocks, start=1):
        title_match = re.search(r"<h2>(.*?)</h2>", block, re.S)
        if not title_match:
            continue
        title = html.unescape(re.sub(r"<.*?>", "", title_match.group(1)).strip())
        img_match = re.search(r"<img src=\"/images/([^\"]+)\"", block)
        link_match = re.search(r"<a href=\"([^\"]+)\"", block)
        body = html.unescape(re.sub(r"<.*?>", " ", block.split("</h2>", 1)[-1]))
        body = re.sub(r"\s+", " ", body).strip()
        date_match = re.search(r"\b(20\d{2})\b", title + " " + body)
        year = date_match.group(1) if date_match else ""
        member_ids, member_names = infer_members(title + " " + body, members)
        records.append(
            activity_template(
                record_id=f"award_{idx}_{slugify(title)}",
                record_type="award",
                title=title,
                date=year,
                date_display=year,
                year=year,
                venue="",
                role="awardee",
                url=link_match.group(1) if link_match else "",
                abstract_or_description=body,
                image=img_match.group(1) if img_match else "",
                visibility="public",
                source_file=str(path.relative_to(ROOT)).replace("\\", "/"),
                member_ids=member_ids or "lab",
                member_names=member_names or "Knevel Lab",
            )
        )
    return records


def linked_item_records(page_name: str, record_type: str, title_tag: str, default_role: str = "") -> list[dict[str, str]]:
    path = ROOT / "_pages" / page_name
    if not path.exists():
        return []
    text = read_text(path)
    pattern = rf"<{title_tag}>(.*?)</{title_tag}>\s*<div style=\"height: 200px;\">(.*?)</div>"
    records: list[dict[str, str]] = []
    for idx, (raw_title, block) in enumerate(re.findall(pattern, text, re.S), start=1):
        title = html.unescape(re.sub(r"<.*?>", "", raw_title).strip())
        link_match = re.search(r"<a href=\"([^\"]+)\"", block)
        img_match = re.search(r"<img src=\"/images/([^\"]+)\"[^>]*alt=\"([^\"]*)\"", block)
        paragraphs = re.findall(r"<p>(.*?)</p>", block, re.S)
        description_parts: list[str] = []
        role = default_role
        for paragraph in paragraphs:
            clean = html.unescape(re.sub(r"<.*?>", " ", paragraph))
            clean = re.sub(r"\s+", " ", clean).strip()
            if clean.lower().startswith("developed by"):
                role = clean
            elif clean:
                description_parts.append(clean)
        records.append(
            activity_template(
                record_id=f"{record_type}_{idx}_{slugify(title)}",
                record_type=record_type,
                title=title,
                date="",
                date_display="",
                year="",
                venue="",
                location="",
                role=role,
                url=link_match.group(1) if link_match else "",
                abstract_or_description=" ".join(description_parts),
                image=img_match.group(1) if img_match else "",
                visibility="public",
                source_file=str(path.relative_to(ROOT)).replace("\\", "/"),
                member_ids="lab",
                member_names="Knevel Lab",
            )
        )
    return records


def application_records() -> list[dict[str, str]]:
    return linked_item_records("applications.html", "application", "h4")


def project_records() -> list[dict[str, str]]:
    return linked_item_records("projects.html", "project", "h2")
def activity_template(**kwargs: str) -> dict[str, str]:
    row = {field: "" for field in ACTIVITY_FIELDS}
    row.update({key: value or "" for key, value in kwargs.items() if key in row})
    row.setdefault("visibility", "public")
    return row


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def copy_tree_or_file(source: Path, destination: Path) -> None:
    if source.is_dir():
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
    elif source.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def backup_hardcoded_site(force: bool = False) -> None:
    if BACKUP_DIR.exists() and not force:
        return
    if BACKUP_DIR.exists():
        shutil.rmtree(BACKUP_DIR)
    targets = [
        ROOT / "_publications",
        ROOT / "_talks",
        ROOT / "_pages" / "group.html",
        ROOT / "_pages" / "awards.html",
        ROOT / "_pages" / "applications.html",
        ROOT / "_pages" / "projects.html",
    ]
    for target in targets:
        if target.is_dir():
            copy_tree_or_file(target, BACKUP_DIR / target.name)
        elif target.exists():
            copy_tree_or_file(target, BACKUP_DIR / "_pages" / target.name)
    write_text(
        BACKUP_DIR / "README.md",
        "# Hardcoded website backup\n\n"
        "This directory stores the pre-pipeline hardcoded website content.\n"
        "It is kept so generated output can be compared or restored manually.\n\n"
        "Backed up paths:\n\n"
        "- `_publications/`\n"
        "- `_talks/`\n"
        "- `_pages/group.html`\n"
        "- `_pages/awards.html`\n",
    )

def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def bootstrap(force: bool) -> None:
    if not force:
        existing = [p for p in (ACTIVITIES_CSV, MEMBERS_CSV) if p.exists()]
        if existing:
            names = ", ".join(str(p.relative_to(ROOT)) for p in existing)
            raise SystemExit(f"Refusing to overwrite existing file(s): {names}. Use --force.")
    members = extract_group_members()
    records = publication_records(members) + talk_records(members) + award_records(members) + application_records() + project_records()
    write_csv(MEMBERS_CSV, members, MEMBER_FIELDS)
    write_csv(ACTIVITIES_CSV, records, ACTIVITY_FIELDS)
    print(f"Wrote {MEMBERS_CSV.relative_to(ROOT)} with {len(members)} members")
    print(f"Wrote {ACTIVITIES_CSV.relative_to(ROOT)} with {len(records)} activity records")


def required_for(row: dict[str, str]) -> list[str]:
    record_type = row.get("record_type", "")
    base = ["record_id", "record_type", "title", "visibility"]
    if record_type == "publication":
        return base + ["venue", "citation", "url"]
    if record_type in {"talk", "invited_presentation", "public_outreach"}:
        return base + ["date", "venue"]
    if record_type == "award":
        return base + ["year"]
    return base


def validate(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_permalinks: set[str] = set()
    for idx, row in enumerate(rows, start=2):
        record_id = row.get("record_id", "")
        if record_id in seen_ids:
            errors.append(f"row {idx}: duplicate record_id {record_id}")
        seen_ids.add(record_id)
        if row.get("visibility", "public") == "hidden":
            continue
        for field in required_for(row):
            if not row.get(field, "").strip():
                errors.append(f"row {idx} ({record_id}): missing {field}")
        permalink = row.get("permalink", "").strip()
        if permalink:
            if permalink in seen_permalinks:
                errors.append(f"row {idx} ({record_id}): duplicate permalink {permalink}")
            seen_permalinks.add(permalink)
    return errors


def generate_publication_md(row: dict[str, str]) -> tuple[str, str]:
    date_part = row.get("date_display") or row.get("date") or row.get("year") or "undated"
    slug = slugify(row.get("permalink") or row["title"])
    filename = f"{date_part}-{slug}.md".replace("/", "-")
    permalink = row.get("permalink") or f"/publication/{filename[:-3]}"
    fm = {
        "title": row["title"],
        "collection": "publications",
        "permalink": permalink,
        "excerpt": row.get("abstract_or_description", ""),
        "date": jekyll_date_value(row),
        "date_display": date_display_value(row),
        "venue": row.get("venue", ""),
        "paperurl": row.get("url", ""),
        "citation": row.get("citation", ""),
    }
    body = ""
    if row.get("url"):
        body += f"\n\n<a href='{row['url']}'>Download paper here</a>\n"
    if row.get("abstract_or_description"):
        body += "\n" + row["abstract_or_description"].strip() + "\n"
    if row.get("citation"):
        body += "\nRecommended citation: " + row["citation"].strip() + "\n"
    return filename, frontmatter_block(fm) + body


def display_activity_type(row: dict[str, str]) -> str:
    explicit_role = (row.get("role") or "").strip()
    if explicit_role:
        return explicit_role
    labels = {
        "talk": "Talk",
        "invited_presentation": "Invited presentation",
        "public_outreach": "Public outreach",
    }
    label = labels.get(row.get("record_type", ""), row.get("record_type", "").replace("_", " ").title())
    member_names = (row.get("member_names") or "").replace(";", ", ").strip()
    if member_names and member_names != "Knevel Lab":
        return f"{label} by {member_names}"
    return label


def generate_talk_md(row: dict[str, str]) -> tuple[str, str]:
    date = row.get("date") or row.get("year") or "undated"
    slug = slugify(row.get("permalink") or row["title"])
    filename = f"{date}-{slug}.md".replace("/", "-")
    permalink = row.get("permalink") or f"/talks/{filename[:-3]}"
    fm = {
        "title": row["title"],
        "collection": "talks",
        "type": display_activity_type(row),
        "permalink": permalink,
        "venue": row.get("venue", ""),
        "date": jekyll_date_value(row),
        "date_display": date_display_value(row),
        "location": row.get("location", ""),
    }
    body = ""
    if row.get("url"):
        body += f"\n\n[More information here]({row['url']})\n"
    if row.get("abstract_or_description"):
        body += "\n" + row["abstract_or_description"].strip() + "\n"
    return filename, frontmatter_block(fm) + body


def generate_member_page(member: dict[str, str], activities: list[dict[str, str]]) -> tuple[str, str]:
    member_id = member["member_id"]
    filename = f"{member_id.replace('_', '-')}.md"
    permalink = f"/members/{member_id.replace('_', '-')}/"
    fm = frontmatter_block(
        {
            "layout": "archive",
            "title": member["name"],
            "permalink": permalink,
            "author_profile": "true",
        }
    )
    lines = [fm, ""]
    if member.get("image"):
        lines.append(f'<img src="{html.escape(image_src(member["image"]), quote=True)}" alt="{html.escape(member["name"], quote=True)}" class="biopic">')
    if member.get("bio"):
        lines.append("")
        lines.append(member["bio"])
    links = []
    for key, label in [
        ("linkedin", "LinkedIn"),
        ("github", "Github"),
        ("pubmed", "PubMed"),
        ("orcid", "ORCID"),
        ("google_scholar", "Google Scholar"),
    ]:
        if member.get(key):
            links.append(f'[{label}]({member[key]})')
    if links:
        lines.append("")
        lines.append(" | ".join(links))
    member_activities = [
        row
        for row in activities
        if member_id in split_semicolon(row.get("member_ids", "")) and row.get("visibility", "public") == "public"
    ]
    for heading, types in [
        ("Publications", {"publication"}),
        ("Talks and presentations", {"talk", "invited_presentation", "public_outreach"}),
        ("Awards", {"award"}),
    ]:
        subset = [row for row in member_activities if row.get("record_type") in types]
        if not subset:
            continue
        lines.append("")
        lines.append(f"## {heading}")
        for row in sorted(subset, key=lambda r: r.get("date") or r.get("year"), reverse=True):
            date = row.get("date_display") or row.get("date") or row.get("year")
            venue = f", {row['venue']}" if row.get("venue") else ""
            url = row.get("url")
            title = f"[{row['title']}]({url})" if url else row["title"]
            lines.append(f"- {date}: {title}{venue}")
    lines.append("")
    return filename, "\n".join(lines)


def source_filename(row: dict[str, str], collection_dir: str, fallback: str) -> str:
    source_file = row.get("source_file", "").strip().replace("\\", "/")
    prefix = f"{collection_dir}/"
    if source_file.startswith(prefix) and source_file.endswith(".md"):
        return Path(source_file).name
    return fallback


def member_links_html(member: dict[str, str]) -> str:
    links = []
    link_specs = [
        ("linkedin", "fab fa-fw fa-linkedin", "LinkedIn"),
        ("github", "fab fa-fw fa-github", "Github"),
        ("pubmed", "ai ai-pubmed-square ai-fw", "PubMed"),
        ("orcid", "ai ai-orcid-square ai-fw", "ORCID"),
        ("google_scholar", "ai ai-google-scholar ai-fw", "Google Scholar"),
        ("researchgate", "fab fa-fw fa-researchgate", "ResearchGate"),
        ("blog", "fa fa-code", "Blog"),
    ]
    for key, icon_class, label in link_specs:
        href = member.get(key, "").strip()
        if href:
            links.append(f'<a href="{html.escape(href, quote=True)}"><i class="{icon_class}" aria-hidden="true"></i> {label}</a>')
    return "\n".join(links)

def image_src(image: str) -> str:
    image = (image or "").strip()
    if not image:
        return ""
    if re.match(r"https?://", image) or image.startswith("/"):
        return image
    return f"/images/{image}"

def render_member_block(member: dict[str, str]) -> str:
    name = member.get("name", "").strip()
    image = member.get("image", "").strip() or "Profile.jpg"
    bio = member.get("bio", "").strip()
    links = member_links_html(member)
    lines = [
        '<div style="height: 150px;">',
        f'<img src="{html.escape(image_src(image), quote=True)}" alt="{html.escape(name, quote=True)}" class="biopic">',
        f'<h2>{html.escape(name)}</h2>',
    ]
    if bio:
        lines.append(html.escape(bio))
    lines.append("<br>")
    if links:
        lines.append(links)
    lines.append("</div>")
    lines.append("<hr>")
    return "\n".join(lines)


def generate_group_html(members: list[dict[str, str]]) -> str:
    header = """---
layout: archive
title: "Group"
permalink: /group/
author_profile: true
redirect_from: 
  - /group
---
"""
    sections = [header]
    for status, heading in [("current", ""), ("affiliated", "Affiliated Members"), ("alumni", "Alumni")]:
        subset = [member for member in members if member.get("status", "current") == status]
        if not subset:
            continue
        if heading:
            sections.append(f"\n\n<h3>{heading}</h3>\n")
        sections.extend(render_member_block(member) for member in subset)
    return "\n\n".join(sections).rstrip() + "\n"


def render_linked_item_block(row: dict[str, str], title_tag: str) -> str:
    title = row.get("title", "").strip()
    image = row.get("image", "").strip()
    url = row.get("url", "").strip()
    description = row.get("abstract_or_description", "").strip()
    role = row.get("role", "").strip()
    lines = [f"<{title_tag}>{html.escape(title)}</{title_tag}>", '<div style="height: 200px;">']
    if url:
        lines.append(f'<a href="{html.escape(url, quote=True)}">')
    if image:
        lines.append(f'<img src="{html.escape(image_src(image), quote=True)}" alt="{html.escape(title, quote=True)}" class="applink">')
    if url:
        lines.append("</a>")
    if description:
        lines.append(f"<p>{html.escape(description)}</p>")
    if role:
        lines.append(f"<p>{html.escape(role)}</p>")
    lines.append("</div>")
    lines.append("<hr>")
    return "\n".join(lines)


def generate_applications_html(applications: list[dict[str, str]]) -> str:
    header = """---
layout: archive
title: "Applications"
permalink: /applications/
author_profile: true
redirect_from:
  - /applications
---
"""
    visible = [row for row in applications if row.get("visibility", "public") == "public"]
    visible = sorted(visible, key=lambda row: row.get("date") or row.get("year"), reverse=True)
    return header + "\n" + "\n\n".join(render_linked_item_block(row, "h4") for row in visible).rstrip() + "\n"


def generate_projects_html(projects: list[dict[str, str]]) -> str:
    header = """---
layout: archive
title: "Projects"
permalink: /projects/
author_profile: true
redirect_from:
  - /projects
---

<h4>An overview of our (international) projects and collaborations</h4>
"""
    visible = [row for row in projects if row.get("visibility", "public") == "public"]
    visible = sorted(visible, key=lambda row: row.get("date") or row.get("year"), reverse=True)
    return header + "\n" + "\n\n".join(render_linked_item_block(row, "h2") for row in visible).rstrip() + "\n"
def render_award_block(row: dict[str, str]) -> str:
    title = row.get("title", "").strip()
    image = row.get("image", "").strip()
    description = row.get("abstract_or_description", "").strip()
    url = row.get("url", "").strip()
    lines = ['<div style="height: auto;">']
    if image:
        lines.append(f'<img src="{html.escape(image_src(image), quote=True)}" alt="{html.escape(title, quote=True)}" class="biopic">')
    lines.append(f'<h2>{html.escape(title)}</h2>')
    if description:
        lines.append(html.escape(description))
    if url:
        lines.append("<br><br>")
        lines.append("For more information:<br>")
        lines.append(f'<a href="{html.escape(url, quote=True)}">{html.escape(url)}</a>')
    lines.append("</div>")
    lines.append("<hr>")
    return "\n".join(lines)


def generate_awards_html(awards: list[dict[str, str]]) -> str:
    header = """---
layout: archive
title: "Awards won by members of the Knevel group"
permalink: /awards/
author_profile: true
redirect_from: 
  - /awards
---
"""
    visible_awards = [row for row in awards if row.get("visibility", "public") == "public"]
    visible_awards = sorted(visible_awards, key=lambda row: row.get("date") or row.get("year"), reverse=True)
    return header + "\n" + "\n\n".join(render_award_block(row) for row in visible_awards).rstrip() + "\n"


def clear_markdown_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for item in path.glob("*.md"):
        item.unlink()


def generate_site(force_backup: bool = False) -> None:
    activities = read_csv_rows(ACTIVITIES_CSV)
    members = read_csv_rows(MEMBERS_CSV) if MEMBERS_CSV.exists() else []
    errors = validate(activities)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)

    backup_hardcoded_site(force=force_backup)

    publications = [r for r in activities if r.get("visibility", "public") == "public" and r.get("record_type") == "publication"]
    talks = [
        r
        for r in activities
        if r.get("visibility", "public") == "public"
        and r.get("record_type") in {"talk", "invited_presentation", "public_outreach"}
    ]
    awards = [r for r in activities if r.get("visibility", "public") == "public" and r.get("record_type") == "award"]
    applications = [r for r in activities if r.get("visibility", "public") == "public" and r.get("record_type") == "application"]
    projects = [r for r in activities if r.get("visibility", "public") == "public" and r.get("record_type") == "project"]

    clear_markdown_dir(ROOT / "_publications")
    clear_markdown_dir(ROOT / "_talks")

    for row in publications:
        filename, content = generate_publication_md(row)
        write_text(ROOT / "_publications" / source_filename(row, "_publications", filename), content)
    for row in talks:
        filename, content = generate_talk_md(row)
        write_text(ROOT / "_talks" / source_filename(row, "_talks", filename), content)

    write_text(ROOT / "_pages" / "group.html", generate_group_html(members))
    write_text(ROOT / "_pages" / "awards.html", generate_awards_html(awards))
    write_text(ROOT / "_pages" / "applications.html", generate_applications_html(applications))
    write_text(ROOT / "_pages" / "projects.html", generate_projects_html(projects))
    write_tsv(GENERATOR_DIR / "publications.tsv", publications_to_tsv_rows(publications), [
        "pub_date",
        "title",
        "venue",
        "excerpt",
        "citation",
        "url_slug",
        "paper_url",
    ])
    write_tsv(GENERATOR_DIR / "talks.tsv", talks_to_tsv_rows(talks), [
        "title",
        "type",
        "url_slug",
        "venue",
        "date",
        "location",
        "talk_url",
        "description",
    ])
    print(f"Generated site publications: {len(publications)}")
    print(f"Generated site talks/presentations/outreach: {len(talks)}")
    print(f"Generated site awards: {len(awards)}")
    print(f"Generated site applications: {len(applications)}")
    print(f"Generated site projects: {len(projects)}")
    print(f"Generated group members: {len(members)}")
def generate_preview() -> None:
    activities = read_csv_rows(ACTIVITIES_CSV)
    members = read_csv_rows(MEMBERS_CSV) if MEMBERS_CSV.exists() else []
    errors = validate(activities)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)
    if PREVIEW_DIR.exists():
        shutil.rmtree(PREVIEW_DIR)
    publications = [r for r in activities if r.get("visibility", "public") == "public" and r.get("record_type") == "publication"]
    talks = [
        r
        for r in activities
        if r.get("visibility", "public") == "public"
        and r.get("record_type") in {"talk", "invited_presentation", "public_outreach"}
    ]
    awards = [r for r in activities if r.get("visibility", "public") == "public" and r.get("record_type") == "award"]
    applications = [r for r in activities if r.get("visibility", "public") == "public" and r.get("record_type") == "application"]
    projects = [r for r in activities if r.get("visibility", "public") == "public" and r.get("record_type") == "project"]

    for row in publications:
        filename, text = generate_publication_md(row)
        write_text(PREVIEW_DIR / "_publications" / filename, text)
    for row in talks:
        filename, text = generate_talk_md(row)
        write_text(PREVIEW_DIR / "_talks" / filename, text)
    for member in members:
        filename, text = generate_member_page(member, activities)
        write_text(PREVIEW_DIR / "_members" / filename, text)

    write_tsv(PREVIEW_DIR / "markdown_generator" / "publications.tsv", publications_to_tsv_rows(publications), [
        "pub_date",
        "title",
        "venue",
        "excerpt",
        "citation",
        "url_slug",
        "paper_url",
    ])
    write_tsv(PREVIEW_DIR / "markdown_generator" / "talks.tsv", talks_to_tsv_rows(talks), [
        "title",
        "type",
        "url_slug",
        "venue",
        "date",
        "location",
        "talk_url",
        "description",
    ])
    write_text(PREVIEW_DIR / "_data" / "members.json", json.dumps(members, ensure_ascii=False, indent=2))
    write_text(PREVIEW_DIR / "_data" / "member_activities.json", json.dumps(activities, ensure_ascii=False, indent=2))
    write_text(PREVIEW_DIR / "_data" / "awards.json", json.dumps(awards, ensure_ascii=False, indent=2))
    print(f"Generated preview publications: {len(publications)}")
    print(f"Generated preview talks/presentations/outreach: {len(talks)}")
    print(f"Generated preview awards: {len(awards)}")
    print(f"Generated preview member pages: {len(members)}")


def publications_to_tsv_rows(publications: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = []
    for row in publications:
        rows.append(
            {
                "pub_date": row.get("date") or row.get("date_display") or row.get("year"),
                "title": row.get("title", ""),
                "venue": row.get("venue", ""),
                "excerpt": row.get("abstract_or_description", ""),
                "citation": row.get("citation", ""),
                "url_slug": slugify(row.get("title", "")),
                "paper_url": row.get("url", ""),
            }
        )
    return rows


def talks_to_tsv_rows(talks: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = []
    for row in talks:
        rows.append(
            {
                "title": row.get("title", ""),
                "type": row.get("role", ""),
                "url_slug": slugify(row.get("title", "")),
                "venue": row.get("venue", ""),
                "date": row.get("date", ""),
                "location": row.get("location", ""),
                "talk_url": row.get("url", ""),
                "description": row.get("abstract_or_description", ""),
            }
        )
    return rows


def check() -> None:
    activities = read_csv_rows(ACTIVITIES_CSV)
    errors = validate(activities)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)
    print(f"Validated {len(activities)} activity records")


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap-current", action="store_true", help="Create source CSVs from current site files.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing source CSVs during bootstrap.")
    parser.add_argument("--generate-preview", action="store_true", help="Generate preview files from source CSVs.")
    parser.add_argument("--generate-site", action="store_true", help="Replace site content files from source CSVs after backing up hardcoded files.")
    parser.add_argument("--force-backup", action="store_true", help="Overwrite markdown_generator/hardcoded_backup during --generate-site.")
    parser.add_argument("--check", action="store_true", help="Validate source CSVs.")
    args = parser.parse_args(argv)

    if args.bootstrap_current:
        bootstrap(force=args.force)
    if args.check:
        check()
    if args.generate_preview:
        generate_preview()
    if args.generate_site:
        generate_site(force_backup=args.force_backup)
    if not (args.bootstrap_current or args.check or args.generate_preview or args.generate_site):
        parser.print_help()


if __name__ == "__main__":
    main()
