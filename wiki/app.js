/* index search + category filter for Koganei Council Wiki */
(function () {
  var data = [], q = document.getElementById('q'),
      results = document.getElementById('results'),
      browse = document.getElementById('browse'),
      cat = 'all', term = '';

  fetch('search.json').then(function (r) { return r.json(); }).then(function (j) {
    data = j; render();
  });

  function applyFilter() {
    document.querySelectorAll('#browse .tile').forEach(function (t) {
      t.style.display = (cat === 'all' || t.getAttribute('data-c') === cat) ? '' : 'none';
    });
    document.querySelectorAll('#browse .grp').forEach(function (g) {
      var grid = g.nextElementSibling, any = false;
      if (grid) grid.querySelectorAll('.tile').forEach(function (t) { if (t.style.display !== 'none') any = true; });
      g.style.display = any ? '' : 'none';
      if (grid) grid.style.display = any ? '' : 'none';
    });
  }

  function render() {
    term = (q.value || '').trim().toLowerCase();
    if (!term) { results.innerHTML = ''; browse.style.display = ''; applyFilter(); return; }
    browse.style.display = 'none';
    var hits = data.filter(function (d) {
      if (cat !== 'all' && d.c !== cat) return false;
      var hay = (d.t + ' ' + d.c + ' ' + d.w + ' ' + d.d + ' ' + (d.m || []).join(' ') + ' ' +
                 (d.b || []).join(' ') + ' ' + (d.s || '')).toLowerCase();
      return term.split(/\s+/).every(function (w) { return hay.indexOf(w) >= 0; });
    });
    var h = '<h2 class="sec">検索結果 <span style="font-family:var(--sans);font-size:.7rem;color:var(--ink-soft)">' +
            hits.length + ' 件</span></h2>';
    if (!hits.length) h += '<p class="src">該当なし。別のキーワードをお試しください。</p>';
    h += '<div class="grid">';
    hits.forEach(function (d) {
      var snip = highlight(d.s || '', term);
      h += '<a class="tile" href="m/' + encodeURI(d.f) + '">' +
           '<span class="num">' + d.d + '</span><h3>' + esc(d.t) + '</h3>' +
           '<p>' + snip + '</p>' +
           '<span class="meta">' + esc(d.c) + ' ・ 動画' + d.v + '本' +
           (d.m && d.m.length ? ' ・ ' + esc(d.m.slice(0, 3).join('・')) : '') + '</span></a>';
    });
    h += '</div>';
    results.innerHTML = h;
  }

  function esc(s) { return (s || '').replace(/[&<>]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]; }); }
  function highlight(s, t) {
    var w = t.split(/\s+/)[0]; if (!w) return esc(s.slice(0, 120));
    var i = s.toLowerCase().indexOf(w);
    var start = Math.max(0, i - 30), seg = s.slice(start, start + 140);
    seg = esc(seg);
    try { seg = seg.replace(new RegExp('(' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'ig'), '<mark>$1</mark>'); } catch (e) {}
    return (start > 0 ? '…' : '') + seg + '…';
  }

  q.addEventListener('input', render);
  document.querySelectorAll('.filt').forEach(function (b) {
    b.addEventListener('click', function () {
      document.querySelectorAll('.filt').forEach(function (x) { x.classList.remove('active'); });
      b.classList.add('active'); cat = b.getAttribute('data-c'); render();
    });
  });
})();
