/**
 * Create the Knevel Lab website activity Google Form and linked Google Sheet.
 *
 * Run once from https://script.google.com/ with the Google account that should
 * own the form and response sheet. Publication submissions use only PubMed ID
 * or DOI; metadata is completed by the GitHub Actions importer.
 */
function createKnevelWebsiteActivityForm() {
  const members = [
    ['rachel_knevel', 'Rachel Knevel'],
    ['nils_steinz', 'Nils Steinz'],
    ['ling_qing', 'Ling Qing'],
    ['floor_dijkstra_zegers', 'Floor Dijkstra Zegers'],
    ['georgy_gomon', 'Georgy Gomon'],
    ['daniyal_selani', 'Daniyal Selani'],
    ['suguru_honda', 'Suguru Honda'],
    ['inez_den_hond', 'Inez den Hond'],
    ['bahar_sedaghatikhayat', 'Bahar Sedaghatikhayat'],
    ['mick_blikman', 'Mick Blikman'],
    ['qingshuang_xie', 'Qingshuang Xie'],
    ['david_steeman', 'David Steeman'],
    ['erik_van_den_akker', 'Erik van den Akker'],
    ['lab', 'Lab-wide item'],
  ];
  const memberChoices = members.map(([id, name]) => `${id} = ${name}`);

  const sheet = SpreadsheetApp.create('Knevel Lab website activity submissions');
  const form = FormApp.create('Knevel Lab website activity submission');
  form.setDescription('Submit publications, talks, outreach, awards, applications, and projects for the Knevel Lab website. For publications, enter only PubMed ID or DOI; metadata is filled later from PubMed.');
  form.setCollectEmail(true);
  form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());

  const typeItem = form.addMultipleChoiceItem()
    .setTitle('record_type')
    .setHelpText('Choose one. Publication requires only PubMed ID or DOI. All other types use the shared activity details page.')
    .setRequired(true);

  const publicationPage = form.addPageBreakItem().setTitle('Publication');
  addPublicationSection_(form);

  const activityPage = form.addPageBreakItem().setTitle('Website activity details');
  addActivitySection_(form, memberChoices);

  [publicationPage, activityPage].forEach((page) =>
    page.setGoToPage(FormApp.PageNavigationType.SUBMIT)
  );

  typeItem.setChoices([
    typeItem.createChoice('publication', publicationPage),
    typeItem.createChoice('talk', activityPage),
    typeItem.createChoice('invited_presentation', activityPage),
    typeItem.createChoice('public_outreach', activityPage),
    typeItem.createChoice('award', activityPage),
    typeItem.createChoice('application', activityPage),
    typeItem.createChoice('project', activityPage),
  ]);

  Logger.log('Form edit URL: ' + form.getEditUrl());
  Logger.log('Form public URL: ' + form.getPublishedUrl());
  Logger.log('Response Sheet URL: ' + sheet.getUrl());
  Logger.log('Manual file upload setup: in the Google Form editor, change the image question type from Paragraph to File upload if local PC uploads are needed. Keep the exact title image, allow 1 file, and restrict file type to image.');
}

function addPublicationSection_(form) {
  form.addTextItem()
    .setTitle('publication_pubmed_id')
    .setHelpText('Preferred. Enter PubMed ID only, e.g. 42498579.')
    .setRequired(false);
  form.addTextItem()
    .setTitle('publication_doi')
    .setHelpText('Use only when PubMed ID is unknown. The importer will resolve DOI to PubMed when possible.')
    .setRequired(false);
}

function addMembers_(form, title, choices) {
  return form.addCheckboxItem()
    .setTitle(title)
    .setHelpText('Select all relevant lab members, or lab for a lab-wide item.')
    .setChoiceValues(choices)
    .setRequired(true);
}

function addActivitySection_(form, memberChoices) {
  addMembers_(form, 'member_ids', memberChoices);
  form.addTextItem()
    .setTitle('title')
    .setHelpText('Title as it should appear on the website.')
    .setRequired(true);
  form.addTextItem()
    .setTitle('date')
    .setHelpText('Use DD-MM-YYYY if possible. YYYY or Mon YYYY is also accepted.')
    .setRequired(true);
  form.addTextItem()
    .setTitle('venue')
    .setHelpText('Meeting, event, award body, organization, host, funder, or outlet name.')
    .setRequired(true);
  form.addTextItem()
    .setTitle('location')
    .setHelpText('Optional city, country, or online.')
    .setRequired(false);
  form.addTextItem()
    .setTitle('role')
    .setHelpText('Optional presenter, invited speaker, awardee, developer, collaborator, funder, or other role.')
    .setRequired(false);
  form.addTextItem()
    .setTitle('url')
    .setHelpText('Optional relevant link.')
    .setRequired(false);
  form.addParagraphTextItem()
    .setTitle('abstract_or_description')
    .setHelpText('Optional short website text or description.')
    .setRequired(false);
  addImageQuestions_(form);
}

function addImageQuestions_(form) {
  form.addParagraphTextItem()
    .setTitle('image')
    .setHelpText('Optional image. Maintainer setup: if local PC upload is needed, change this question type from Paragraph to File upload in the Google Form editor, keep this exact title, allow 1 file, and restrict file type to image.')
    .setRequired(false);
}
