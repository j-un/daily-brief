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
    var lastVisible = null;
    items.forEach(function (item, i) {
      var visible = i >= start && i < start + PER_PAGE;
      item.style.display = visible ? '' : 'none';
      item.classList.remove('last-visible');
      if (visible) lastVisible = item;
    });
    if (lastVisible) lastVisible.classList.add('last-visible');
    renderNav();
  }

  function btn(label, disabled, onClick) {
    var b = document.createElement('button');
    b.textContent = label;
    b.disabled = disabled;
    if (!disabled) b.addEventListener('click', onClick);
    return b;
  }

  function renderNav() {
    var old = document.querySelector('.pagination');
    if (old) old.remove();
    var nav = document.createElement('nav');
    nav.className = 'pagination';
    nav.appendChild(btn('«', current === 1, function () { showPage(1); }));
    nav.appendChild(btn('‹', current === 1, function () { showPage(current - 1); }));
    var info = document.createElement('span');
    info.textContent = current + ' / ' + totalPages;
    nav.appendChild(info);
    nav.appendChild(btn('›', current === totalPages, function () { showPage(current + 1); }));
    nav.appendChild(btn('»', current === totalPages, function () { showPage(totalPages); }));
    list.parentNode.insertBefore(nav, list.nextSibling);
  }

  showPage(1);
})();
</script>
