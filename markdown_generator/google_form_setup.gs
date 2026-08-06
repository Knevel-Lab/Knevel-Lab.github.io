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
    ['tjardo_maarseveen', 'Tjardo Maarseveen'],
    ['nils_steinz', 'Nils Steinz'],
    ['ling_qing', 'Ling Qing'],
    ['floor_dijkstra_zegers', 'Floor Dijkstra Zegers'],
    ['georgy_gomon', 'Georgy Gomon'],
    ['daniyal_selani', 'Daniyal Selani'],
    ['jyaysi_desai', 'Jyaysi Desai'],
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
    .setHelpText('Choose one. Publication requires only PubMed ID or DOI.')
    .setRequired(true);

  const publicationPage = form.addPageBreakItem().setTitle('Publication');
  addPublicationSection_(form);

  const talkPage = form.addPageBreakItem().setTitle('Talk / presentation');
  addTalkSection_(form, memberChoices, 'talk');

  const invitedPage = form.addPageBreakItem().setTitle('Invited presentation');
  addTalkSection_(form, memberChoices, 'invited_presentation');

  const outreachPage = form.addPageBreakItem().setTitle('Public outreach');
  addTalkSection_(form, memberChoices, 'public_outreach');

  const awardPage = form.addPageBreakItem().setTitle('Award');
  addAwardSection_(form, memberChoices);

  const applicationPage = form.addPageBreakItem().setTitle('Application');
  addLinkedItemSection_(form, memberChoices, 'application', 'Application name', 'Application URL', true);

  const projectPage = form.addPageBreakItem().setTitle('Project');
  addLinkedItemSection_(form, memberChoices, 'project', 'Project name', 'Project URL', true);

  typeItem.setChoices([
    typeItem.createChoice('publication', publicationPage),
    typeItem.createChoice('talk', talkPage),
    typeItem.createChoice('invited_presentation', invitedPage),
    typeItem.createChoice('public_outreach', outreachPage),
    typeItem.createChoice('award', awardPage),
    typeItem.createChoice('application', applicationPage),
    typeItem.createChoice('project', projectPage),
  ]);

  Logger.log('Form edit URL: ' + form.getEditUrl());
  Logger.log('Form public URL: ' + form.getPublishedUrl());
  Logger.log('Response Sheet URL: ' + sheet.getUrl());
  Logger.log('Manual file upload setup: in the Google Form editor, change award_image, application_image, and project_image question type from Paragraph to File upload if local PC uploads are needed.');
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

function addVisibility_(form, prefix) {
  return form.addListItem()
    .setTitle(prefix + '_visibility')
    .setChoiceValues(['public', 'hidden'])
    .setRequired(true);
}

function addTalkSection_(form, memberChoices, prefix) {
  addMembers_(form, prefix + '_member_ids', memberChoices);
  form.addTextItem()
    .setTitle(prefix + '_title')
    .setHelpText('Title as it should appear on the website.')
    .setRequired(true);
  form.addTextItem()
    .setTitle(prefix + '_date')
    .setHelpText('Use YYYY-MM-DD if possible. YYYY or YYYY Mon is also accepted.')
    .setRequired(true);
  form.addTextItem()
    .setTitle(prefix + '_venue')
    .setHelpText('Meeting, event, or outlet name.')
    .setRequired(true);
  form.addTextItem()
    .setTitle(prefix + '_location')
    .setHelpText('City, country, or online.')
    .setRequired(false);
  form.addTextItem()
    .setTitle(prefix + '_role')
    .setHelpText('Presenter, invited speaker, panelist, etc.')
    .setRequired(false);
  form.addTextItem()
    .setTitle(prefix + '_url')
    .setHelpText('Optional relevant link.')
    .setRequired(false);
  form.addParagraphTextItem()
    .setTitle(prefix + '_abstract_or_description')
    .setHelpText('Optional short description.')
    .setRequired(false);
  addVisibility_(form, prefix);
}

function addAwardSection_(form, memberChoices) {
  const prefix = 'award';
  addMembers_(form, prefix + '_member_ids', memberChoices);
  form.addTextItem()
    .setTitle(prefix + '_title')
    .setHelpText('Award name as it should appear on the website.')
    .setRequired(true);
  form.addTextItem()
    .setTitle(prefix + '_date')
    .setHelpText('Use YYYY-MM-DD if possible. YYYY or YYYY Mon is also accepted.')
    .setRequired(true);
  form.addTextItem()
    .setTitle(prefix + '_role')
    .setHelpText('Awardee and short role, e.g. Awardee: Georgy Gomon.')
    .setRequired(true);
  form.addParagraphTextItem()
    .setTitle(prefix + '_abstract_or_description')
    .setHelpText('Short website text, e.g. what was awarded and why.')
    .setRequired(true);
  form.addTextItem()
    .setTitle(prefix + '_venue')
    .setHelpText('Award body, congress, or event name.')
    .setRequired(false);
  form.addTextItem()
    .setTitle(prefix + '_location')
    .setHelpText('City, country, or online.')
    .setRequired(false);
  form.addTextItem()
    .setTitle(prefix + '_url')
    .setHelpText('Optional information link.')
    .setRequired(false);
  addImageQuestions_(form, prefix);
  addVisibility_(form, prefix);
}

function addLinkedItemSection_(form, memberChoices, prefix, titleHelp, urlHelp, includeImage) {
  addMembers_(form, prefix + '_member_ids', memberChoices);
  form.addTextItem()
    .setTitle(prefix + '_title')
    .setHelpText(titleHelp)
    .setRequired(true);
  form.addTextItem()
    .setTitle(prefix + '_url')
    .setHelpText(urlHelp)
    .setRequired(true);
  form.addParagraphTextItem()
    .setTitle(prefix + '_abstract_or_description')
    .setHelpText('Short text to show on the website.')
    .setRequired(true);
  form.addTextItem()
    .setTitle(prefix + '_role')
    .setHelpText('Developer, collaborator, funder, or role shown below the description.')
    .setRequired(false);
  form.addTextItem()
    .setTitle(prefix + '_date')
    .setHelpText('Optional. Use YYYY-MM-DD if relevant.')
    .setRequired(false);
  form.addTextItem()
    .setTitle(prefix + '_venue')
    .setHelpText('Optional host, funder, or organization.')
    .setRequired(false);
  if (includeImage) {
    addImageQuestions_(form, prefix);
  }
  addVisibility_(form, prefix);
}

function addImageQuestions_(form, prefix) {
  form.addParagraphTextItem()
    .setTitle(prefix + '_image')
    .setHelpText('Optional image. Maintainer setup: if local PC upload is needed, change this question type from Paragraph to File upload in the Google Form editor, keep this exact title, allow 1 file, and restrict file type to image.')
    .setRequired(false);
}
