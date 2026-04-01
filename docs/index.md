---
title: Daily Brief
---

## Archive

<ul class="brief-list">
{% assign briefs = site.pages | where_exp: "p", "p.name contains 'brief-'" | sort: "name" | reverse %}
{% for brief in briefs %}
  <li><a href="{{ brief.url | relative_url }}">{{ brief.name | remove: '.md' | remove: 'brief-' }}</a></li>
{% endfor %}
</ul>
