# Member activity workflow

This is the first implementation of the member-maintained website data flow.

## Source files

- `lab_members.csv`: lab member metadata extracted from `_pages/group.html`.
- `member_activity_records.csv`: one row per activity or achievement.

Lab members should eventually edit only their own rows in `member_activity_records.csv`, or a future Excel workbook generated from the same schema.

## Generated derivatives

The current safe command writes only to `generated_preview/`:

```sh
python markdown_generator/generate_site_content.py --check --generate-preview
```

Preview outputs include:

- `generated_preview/_publications/*.md`
- `generated_preview/_talks/*.md`
- `generated_preview/_members/*.md`
- `generated_preview/_data/members.json`
- `generated_preview/_data/member_activities.json`
- `generated_preview/_data/awards.json`
- `generated_preview/markdown_generator/publications.tsv`
- `generated_preview/markdown_generator/talks.tsv`

`generated_preview/` is ignored by Git.

## Rebuilding the initial CSVs

To recreate the CSVs from the current hardcoded site files:

```sh
python markdown_generator/generate_site_content.py --bootstrap-current --force
```

This parses:

- `_publications/*.md`
- `_talks/*.md`
- `_pages/group.html`
- `_pages/awards.html`

## Important rule

Do not replace `_publications/`, `_talks/`, or member pages from generated output until the preview has been reviewed.

The generated preview currently reproduces the existing counts:

- 38 publications
- 41 talks/presentations
- 3 awards
- 29 member pages
