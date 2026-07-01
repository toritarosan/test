/* 小金井市議会 会議録ナレッジWiki — 検索 & カテゴリ絞り込み */
(function () {
  var data = [],
      q = document.getElementById('q'),
      results = document.getElementById('results'),
      browse = document.getElementById('browse'),
      noresults = document.getElementById('noresults'),
      cat = 'all';

  fetch('search.json').then(function (r) { return r.json(); }).then(function (j) { data = j; });

  var PILL = {
    '本会議': ['#a90000', '#fdeeee'],
    '予算特別委員会': ['#ac3e00', '#ffeee2'],
    '常任委員会': ['#0031d8', '#e8f1fe'],
    '議会運営委員会': ['#5c10be', '#f1eafa'],
    '特別委員会・協議会': ['#197a4b', '#e6f5ec']
  };
  function pill(c) {
    var p = PILL[c] || ['#4d4d4d', '#f2f2f2'];
    return '<span class="cat" style="color:' + p[0] + ';background:' + p[1] + ';">' + esc(c) + '</span>';
  }
  function esc(s) {
    return (s || '').replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  /* --- カテゴリ絞り込み（一覧表示時） --- */
  function applyFilter() {
    document.querySelectorAll('#browse .entry').forEach(function (e) {
      e.classList.toggle('hidden', !(cat === 'all' || e.getAttribute('data-c') === cat));
    });
    document.querySelectorAll('#browse .session').forEach(function (s) {
      var any = s.querySelector('.entry:not(.hidden)');
      s.classList.toggle('hidden', !any);
    });
  }

  /* --- 検索 --- */
  function render() {
    var term = (q.value || '').trim().toLowerCase();
    if (!term) {
      results.classList.add('hidden'); noresults.classList.add('hidden');
      browse.classList.remove('hidden'); applyFilter(); return;
    }
    browse.classList.add('hidden');
    var words = term.split(/\s+/);
    var hits = data.filter(function (d) {
      if (cat !== 'all' && d.c !== cat) return false;
      var hay = (d.t + ' ' + d.c + ' ' + d.w + ' ' + d.d + ' ' + (d.m || []).join(' ') + ' ' +
                 (d.b || []).join(' ') + ' ' + (d.s || '')).toLowerCase();
      return words.every(function (w) { return hay.indexOf(w) >= 0; });
    });
    if (!hits.length) {
      results.classList.add('hidden'); noresults.classList.remove('hidden'); return;
    }
    noresults.classList.add('hidden');
    var h = '<div class="session" style="margin-top:0"><div class="session-head" style="cursor:default">' +
            '<span class="session-name">検索結果</span><span class="session-count">' + hits.length + '</span>' +
            '</div><div class="entries">';
    hits.forEach(function (d) {
      var dir = d.k === 'a' ? 'a/' : 'm/';
      var kind = d.k === 'a' ? '特集記事' : '動画' + d.v + '本';
      h += '<a class="entry" href="' + dir + encodeURI(d.f) + '">' +
           '<span class="date">' + esc((d.d || '').slice(5).replace('-', '.')) + '</span>' +
           pill(d.c) +
           '<span class="name">' + esc(d.t) +
           '<br><span class="sub">' + snippet(d.s || '', words[0]) + '</span></span>' +
           '<span class="sub">' + kind + '</span><span class="chev">→</span></a>';
    });
    h += '</div></div>';
    results.innerHTML = h;
    results.classList.remove('hidden');
  }

  function snippet(s, w) {
    var i = s.toLowerCase().indexOf(w);
    var start = Math.max(0, i - 28), seg = s.slice(start, start + 120);
    seg = esc(seg);
    try {
      seg = seg.replace(new RegExp('(' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'ig'), '<mark>$1</mark>');
    } catch (e) {}
    return (start > 0 ? '…' : '') + seg + '…';
  }

  q.addEventListener('input', render);
  document.querySelectorAll('.facet').forEach(function (b) {
    b.addEventListener('click', function () {
      document.querySelectorAll('.facet').forEach(function (x) { x.classList.remove('is-active'); });
      b.classList.add('is-active');
      cat = b.getAttribute('data-cat');
      render();
    });
  });
})();
