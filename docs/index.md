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

<script>
(function () {
  var PER_PAGE = 10;
  var list = document.querySelector('.brief-list');
  if (!list) return;
  var items = Array.from(list.querySelectorAll('li'));
  var totalPages = Math.ceil(items.length / PER_PAGE);
  if (totalPages <= 1) return;
  var current = 1;

  function showPage(page) {
    current = page;
    var start = (page - 1) * PER_PAGE;
    items.forEach(function (item, i) {
      item.style.display = (i >= start && i < start + PER_PAGE) ? '' : 'none';
    });
    renderNav();
  }

  function renderNav() {
    var old = document.querySelector('.pagination');
    if (old) old.remove();
    var nav = document.createElement('nav');
    nav.className = 'pagination';
    var prev = document.createElement('button');
    prev.textContent = '← 前へ';
    prev.disabled = current === 1;
    prev.addEventListener('click', function () { showPage(current - 1); });
    var info = document.createElement('span');
    info.textContent = current + ' / ' + totalPages;
    var next = document.createElement('button');
    next.textContent = '次へ →';
    next.disabled = current === totalPages;
    next.addEventListener('click', function () { showPage(current + 1); });
    nav.appendChild(prev);
    nav.appendChild(info);
    nav.appendChild(next);
    list.parentNode.insertBefore(nav, list.nextSibling);
  }

  showPage(1);
})();
</script>
