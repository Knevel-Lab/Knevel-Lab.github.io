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
## Local input form

A local browser form is available for people who should not edit the CSV manually:

```sh
python markdown_generator/activity_form_server.py
```

Open:

```text
http://127.0.0.1:8765/
```

The form supports:

- Publications, with PubMed ID auto-fill for title, journal, DOI, authors, citation, URL, abstract, and date.
- Talks / presentations / invited presentations / public outreach.
- Awards, with one image upload.
- Applications, with one image upload.
- Projects, with one image upload.

When the form is saved it:

- automatically creates `record_id`, `member_ids`, and `member_names`;
- copies one uploaded image to `images/` and stores the filename in the CSV `image` column;
- backs up the previous CSV under `markdown_generator/form_backups/`;
- runs `python markdown_generator/generate_site_content.py --check --generate-site`.

## GitHub Issue Form workflow

A repository issue form is available at:

- `.github/ISSUE_TEMPLATE/website_activity.yml`

Lab members can open a new issue using the "Website activity submission" form. The form is intended for one activity record at a time.

Recommended usage:

- For publications, provide `Type=publication`, lab member IDs, visibility, and a PubMed ID. The importer can fill title, date, journal, authors, citation, DOI, URL, and abstract from PubMed.
- For talks, invited presentations, and outreach, provide title, date, venue, and optional URL/description.
- For awards, applications, and projects, paste one image URL or drag one image into the issue image field and keep the GitHub attachment URL.

The importer script is:

```sh
python markdown_generator/import_activity_issue.py --issue-body-file path/to/issue_body.md --issue-number 123
python markdown_generator/generate_site_content.py --check --generate-site
```

A dry run that does not edit the CSV is available:

```sh
python markdown_generator/import_activity_issue.py --issue-body-file path/to/issue_body.md --issue-number 123 --dry-run
```

### Disabled automatic PR workflow

A draft workflow is stored at:

- `.github/workflows/website-activity-issue.yml.disabled`

It is intentionally disabled because an issue-triggered workflow that creates pull requests needs `contents: write` and `pull-requests: write`. That means anyone who can create a `website-activity` issue can cause the GitHub Actions bot to create a branch and PR with generated CSV/site changes.

To enable it after maintainer approval:

1. Rename `.github/workflows/website-activity-issue.yml.disabled` to `.github/workflows/website-activity-issue.yml`.
2. Ensure branch protection requires review before merging into the production branch.
3. Keep the workflow limited to issues with the `website-activity` label.
4. Review every generated PR before merge.

The workflow does not push directly to `master`; it creates a reviewable PR branch.