/**
 * Create the Knevel Lab website activity Google Form and linked Google Sheet.
 *
 * Run once from https://script.google.com/ with the Google account that should
 * own the form and response sheet. Publication is intentionally excluded;
 * publication updates should come from the separate PubMed automation.
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
    ['lab', 'Lab-wide item'],
  ];

  const sheet = SpreadsheetApp.create('Knevel Lab website activity submissions');
  const form = FormApp.create('Knevel Lab website activity submission');
  form.setDescription('Submit talks, outreach, awards, applications, and projects for the Knevel Lab website. Publications are handled separately from PubMed and should not be submitted here.');
  form.setCollectEmail(true);
  form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());

  form.addListItem()
    .setTitle('record_type')
    .setHelpText('Publication is intentionally excluded.')
    .setChoiceValues(['talk', 'invited_presentation', 'public_outreach', 'award', 'application', 'project'])
    .setRequired(true);

  form.addCheckboxItem()
    .setTitle('member_ids')
    .setHelpText('Select all relevant lab members, or lab for a lab-wide item.')
    .setChoiceValues(members.map(([id, name]) => `${id} = ${name}`))
    .setRequired(true);

  form.addTextItem()
    .setTitle('title')
    .setHelpText('Required for every item.')
    .setRequired(true);

  form.addTextItem()
    .setTitle('date')
    .setHelpText('Use YYYY-MM-DD if possible. YYYY or YYYY Mon is also accepted.')
    .setRequired(true);

  form.addTextItem()
    .setTitle('venue')
    .setHelpText('Meeting, event, award body, project funder, or application host.')
    .setRequired(false);

  form.addTextItem()
    .setTitle('location')
    .setHelpText('City, country, or online.')
    .setRequired(false);

  form.addTextItem()
    .setTitle('role')
    .setHelpText('Invited speaker, awardee, developer, presenter, etc.')
    .setRequired(false);

  form.addTextItem()
    .setTitle('url')
    .setHelpText('Optional relevant link.')
    .setRequired(false);

  form.addParagraphTextItem()
    .setTitle('abstract_or_description')
    .setHelpText('Short text to show on the website.')
    .setRequired(false);

  form.addParagraphTextItem()
    .setTitle('image')
    .setHelpText('Optional image URL. If file upload is not available for your account, paste a shareable Drive or web image URL here.')
    .setRequired(false);

  try {
    form.addFileUploadItem()
      .setTitle('image_upload')
      .setHelpText('Optional, one image for awards, applications, or projects. Google may require respondents to sign in.')
      .setMaxFiles(1)
      .setRequired(false);
  } catch (error) {
    Logger.log('File upload item could not be added for this account: ' + error);
  }

  form.addListItem()
    .setTitle('visibility')
    .setChoiceValues(['public', 'hidden'])
    .setRequired(true);

  Logger.log('Form edit URL: ' + form.getEditUrl());
  Logger.log('Form public URL: ' + form.getPublishedUrl());
  Logger.log('Response Sheet URL: ' + sheet.getUrl());
}
