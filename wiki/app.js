/* 会議録ナレッジWiki ホーム — 横断検索 */
(function () {
  var data = [],
      q = document.getElementById('q'),
      form = document.getElementById('searchform'),
      panel = document.getElementById('results-panel'),
      results = document.getElementById('results'),
      count = document.getElementById('result-count'),
      recentPanel = document.getElementById('recent-panel'),
      articlesPanel = document.getElementById('articles-panel');

  fetch('search.json').then(function (r) { return r.json(); }).then(function (j) { data = j; });

  var DOT = {
    '本会議': '#ce0000', '予算特別委員会': '#e25100', '常任委員会': '#264af4',
    '議会運営委員会': '#6f23d0', '特別委員会・協議会': '#1d8b56'
  };
  function esc(s) {
    return (s || '').replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function render() {
    var term = (q.value || '').trim().toLowerCase();
    if (!term) {
      panel.classList.add('hidden');
      recentPanel.classList.remove('hidden');
      articlesPanel.classList.remove('hidden');
      return;
    }
    var words = term.split(/\s+/);
    var hits = data.filter(function (d) {
      var hay = (d.t + ' ' + d.c + ' ' + d.w + ' ' + d.d + ' ' + (d.m || []).join(' ') + ' ' +
                 (d.b || []).join(' ') + ' ' + (d.s || '')).toLowerCase();
      return words.every(function (w) { return hay.indexOf(w) >= 0; });
    });
    count.textContent = hits.length + '件';
    var h = '';
    if (!hits.length) {
      h = '<div class="no-results">該当する会議・記事が見つかりませんでした。キーワードを変えてお試しください。</div>';
    } else {
      hits.forEach(function (d) {
        var dir = d.k === 'a' ? 'a/' : 'm/';
        var badge = d.k === 'a'
          ? '<span class="badge sokuho">議題まとめ</span>'
          : (d.sm ? '<span class="badge official">要約つき</span>' : '<span class="badge sokuho">文字起こし</span>');
        var dot = '<span class="cdot" style="background:' + (DOT[d.c] || '#767676') + ';margin-right:6px;"></span>';
        h += '<a class="result-row" href="' + dir + encodeURI(d.f) + '">' +
             '<span class="date">' + esc((d.d || '').replace(/-/g, '/')) + '</span>' +
             '<span class="body"><span class="title">' + dot + esc(d.t) + '</span>' +
             '<span class="snip">' + snippet(d.s || '', words[0]) + '</span></span>' +
             badge + '</a>';
      });
    }
    results.innerHTML = h;
    panel.classList.remove('hidden');
    recentPanel.classList.add('hidden');
    articlesPanel.classList.add('hidden');
  }

  function snippet(s, w) {
    var i = s.toLowerCase().indexOf(w);
    var start = Math.max(0, i - 26), seg = s.slice(start, start + 130);
    seg = esc(seg);
    try {
      seg = seg.replace(new RegExp('(' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'ig'), '<mark>$1</mark>');
    } catch (e) {}
    return (start > 0 ? '…' : '') + seg + '…';
  }

  q.addEventListener('input', render);
  form.addEventListener('submit', function (e) { e.preventDefault(); render(); });
  document.querySelectorAll('.chip[data-q], .topic[data-q]').forEach(function (b) {
    b.addEventListener('click', function () {
      q.value = b.getAttribute('data-q');
      render();
      q.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  });
})();
