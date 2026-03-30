---
title: Daily Brief
---

## Archive

<ul class="digest-list">
{% assign digests = site.pages | where_exp: "p", "p.name contains 'brief-'" | sort: "name" | reverse %}
{% for digest in digests %}
  <li><a href="{{ digest.url | relative_url }}">{{ digest.name | remove: '.md' | remove: 'brief-' }}</a></li>
{% endfor %}
</ul>
