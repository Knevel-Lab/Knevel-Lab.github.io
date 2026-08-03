# Member Activity Workflow

This repository now has a CSV-driven pipeline for lab-member activity content.

## Source files edited by lab members

- `markdown_generator/lab_members.csv`: lab member profile metadata used for the Group page.
- `markdown_generator/member_activity_records.csv`: one row per publication, talk/presentation/outreach item, or award.

Lab members should update these CSV files instead of editing generated website files directly.

## Generated website files

The pipeline writes these site files from the CSV sources:

- `_publications/*.md`
- `_talks/*.md`
- `_pages/group.html`
- `_pages/awards.html`
- `markdown_generator/publications.tsv`
- `markdown_generator/talks.tsv`

The generated files are committed so GitHub Pages can build the website normally.

## Backup of old hardcoded content

The pre-pipeline hardcoded content is stored in:

- `markdown_generator/hardcoded_backup/_publications/`
- `markdown_generator/hardcoded_backup/_talks/`
- `markdown_generator/hardcoded_backup/_pages/group.html`
- `markdown_generator/hardcoded_backup/_pages/awards.html`

This backup is for comparison and emergency manual restore only. Do not edit it as source data.

## Normal update command

After editing the CSV files, run:

```sh
python markdown_generator/generate_site_content.py --check --generate-site
```

This validates the CSV and regenerates the website files.

## Preview-only command

To inspect generated output without touching the live site files:

```sh
python markdown_generator/generate_site_content.py --check --generate-preview
```

Preview files are written under `markdown_generator/generated_preview/`, which is ignored by Git.

## Rebuilding CSVs from backup/current site files

Only use this when intentionally re-bootstraping from existing hardcoded site files:

```sh
python markdown_generator/generate_site_content.py --bootstrap-current --force
```

After bootstrapping, regenerate the site:

```sh
python markdown_generator/generate_site_content.py --check --generate-site
```

## Current counts

The current CSV-driven generation reproduces the existing content counts:

- 38 publications
- 41 talks/presentations/outreach items
- 3 awards
- 29 group members