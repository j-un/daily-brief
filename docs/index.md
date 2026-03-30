---
title: RSS Digest
---

## ダイジェスト一覧

<ul class="digest-list">
{% assign digests = site.pages | where_exp: "p", "p.name contains 'digest-'" | sort: "name" | reverse %}
{% for digest in digests %}
  <li><a href="{{ digest.url | relative_url }}">{{ digest.name | remove: '.md' }}</a></li>
{% endfor %}
</ul>
