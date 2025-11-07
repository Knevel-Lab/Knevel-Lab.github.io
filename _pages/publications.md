---
layout: archive
title: "Publications"
permalink: /publications/
author_profile: true
---

**Highlighted publications**


You can also find our articles on <u><a href="https://pubmed.ncbi.nlm.nih.gov/?term=%28Knevel+R%5BAuthor%5D%29+NOT+%28%28oral%5BAll+Fields%5D%29+OR+%28dental%5BAll+Fields%5D%29%29&sort=pubdate">PubMed</a>.</u>


{% include base_path %}

{% for post in site.publications reversed %}
  {% include archive-single.html %}
{% endfor %}
