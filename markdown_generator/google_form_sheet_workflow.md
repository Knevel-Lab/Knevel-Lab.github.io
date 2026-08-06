# Google Form / Google Sheet Website Workflow

This is the preferred lab-member submission workflow. It does not require the maintainer's local checkout for routine updates.

## Scope

The Google Form uses section branching. Lab members first choose the item type, then see only the questions needed for that type. Publication submissions show only PubMed ID and DOI fields; all other publication metadata is filled from PubMed by the importer. Lab members submit these website items:

- `talk`
- `invited_presentation`
- `public_outreach`
- `award`
- `application`
- `project`

Publication is included in the Google Form, but only with two fields: `publication_pubmed_id` and `publication_doi`. PubMed ID is preferred. If PubMed ID is blank, the importer tries to resolve the DOI in PubMed. Lab members should not enter publication title, authors, journal, DOI metadata, or citation manually.

## One-time Google setup

1. Open <https://script.google.com/> with the Google account that should own the form and response sheet.
2. Create a new Apps Script project.
3. Paste the contents of `markdown_generator/google_form_setup.gs`.
4. Run `createKnevelWebsiteActivityForm()`.
5. Approve the Google permissions.
6. Copy the logged Form public URL and Response Sheet URL.
7. Share the Response Sheet with the GitHub Actions service account email if the workflow will use private Google access.

A plain CSV template is also available at:

- `markdown_generator/google_sheet_activity_template.csv`

## GitHub setup

The maintainer-triggered GitHub Actions workflow is stored disabled at:

- `.github/workflows/google-sheet-activity-import.yml.disabled`

It is disabled by default because it needs repository write permissions to create PRs. To enable after maintainer approval, rename it to:

- `.github/workflows/google-sheet-activity-import.yml`

Required repository configuration:

- Repository variable `GOOGLE_SHEET_ID`: the raw spreadsheet ID from the response sheet URL.
- Repository secret `GOOGLE_SERVICE_ACCOUNT_JSON`: JSON key for a Google service account with read access to the response sheet and uploaded image files.

The workflow uses Google Drive read-only scope and creates a PR; it does not push directly to `master`.

## Routine operation

1. Lab member submits the Google Form.
2. Maintainer opens GitHub Actions.
3. Run `Import Google Sheet website activities` manually.
4. The workflow downloads the response sheet as CSV.
5. `markdown_generator/import_activity_sheet.py` imports new rows into `markdown_generator/member_activity_records.csv`.
6. `markdown_generator/generate_site_content.py --check --generate-site` regenerates website files.
7. The workflow opens a PR.
8. Maintainer reviews and merges the PR.

## Images

For Awards, Applications, and Projects, the relevant section supports one image. Talk, invited presentation, and outreach sections do not show image questions.

Google Forms can accept local PC uploads through a File upload question, but Apps Script and the Google Forms API cannot create that question automatically. After running `createKnevelWebsiteActivityForm()`, open the Form edit URL and manually change these existing Paragraph questions to File upload questions:

- Award section: `award_image`
- Application section: `application_image`
- Project section: `project_image`

For each converted File upload question:

- keep the exact question title unchanged;
- allow 1 file;
- restrict file type to image;
- leave it optional unless every submission of that type must include an image.

Respondents will then see the normal local PC file picker. The importer already recognizes these exact column names and can download the uploaded Drive files when the GitHub workflow is configured with Google credentials.

Fallback option:

- Keep the question as Paragraph and paste a public image URL into the `*_image` field. The generated site can render HTTP(S) image URLs directly.

If using Google Form file upload, respondents may need to sign in depending on the Google Workspace settings.

## Local dry-run commands

These are for development only; routine operation should use GitHub Actions.

```sh
python markdown_generator/import_activity_sheet.py --sheet-csv markdown_generator/google_sheet_activity_template.csv --dry-run
python markdown_generator/generate_site_content.py --check --generate-site
```

## Type-specific required fields

The branched Google Form uses different required fields per section:

- Publication: PubMed ID or DOI. PubMed ID is preferred; DOI is fallback. No title/authors/journal/citation fields are shown.
- Talk / invited presentation / public outreach: member IDs, title, date, venue.
- Award: member IDs, title, date, awardee/role, description; optional venue, location, URL, and one image.
- Application / project: member IDs, title, URL, description; optional role, date, venue, and one image.

Note: Google Form submissions no longer ask lab members for visibility. The importer defaults new submissions to public; maintainers can edit member_activity_records.csv manually if a row should be hidden.
