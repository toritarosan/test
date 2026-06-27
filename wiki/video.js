/* ===========================================================
   video.js — YouTube link + popup (lightbox) for the wiki
   静的サイト用。サーバー不要。

   使い方（HTML側）:
   <button class="watch" data-yt="VIDEO_ID" data-t="125"
           data-title="議題タイトル">録画を見る</button>

   - data-yt : YouTube の動画ID。未設定/"DEMO" のときはプレースホルダー表示
   - data-t  : 開始秒数（頭出し）。任意
   - data-title : モーダル見出し。任意
   =========================================================== */
(function () {
  var overlay;

  function buildOverlay() {
    overlay = document.createElement('div');
    overlay.className = 'vm-overlay';
    overlay.innerHTML =
      '<div class="vm-box" role="dialog" aria-modal="true">' +
        '<div class="vm-head">' +
          '<div class="t"></div>' +
          '<button class="x" aria-label="閉じる">&times;</button>' +
        '</div>' +
        '<div class="vm-frame"></div>' +
        '<div class="vm-foot">' +
          '<span>議会録画（デモ）</span>' +
          '<a class="yt" target="_blank" rel="noopener">YouTubeで開く ↗</a>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);

    overlay.addEventListener('click', function (e) {
      if (e.target === overlay || e.target.classList.contains('x')) close();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') close();
    });
  }

  function open(opts) {
    if (!overlay) buildOverlay();
    var id = (opts.yt || '').trim();
    var t = parseInt(opts.t || '0', 10) || 0;
    var title = opts.title || '議会録画';

    overlay.querySelector('.t').textContent = title;
    var frame = overlay.querySelector('.vm-frame');
    var ytLink = overlay.querySelector('.yt');

    if (!id || id.toUpperCase() === 'DEMO') {
      // まだ実際のURLが無い → プレースホルダー
      frame.innerHTML =
        '<div class="vm-placeholder">' +
          '<div class="big">▶ ここに議会録画が再生されます</div>' +
          '<div class="sub">これはポップアップ再生のデモ表示です。実際のYouTube動画ID（と頭出し秒数）を設定すると、' +
          'この枠内でその場で再生されます。発言ごとに「該当シーンから再生」も可能です。</div>' +
        '</div>';
      ytLink.style.display = 'none';
    } else {
      var src = 'https://www.youtube-nocookie.com/embed/' + encodeURIComponent(id) +
                '?autoplay=1&rel=0' + (t ? '&start=' + t : '');
      frame.innerHTML = '<iframe src="' + src + '" allow="autoplay; encrypted-media; fullscreen" allowfullscreen></iframe>';
      ytLink.style.display = '';
      ytLink.href = 'https://www.youtube.com/watch?v=' + encodeURIComponent(id) + (t ? '&t=' + t + 's' : '');
    }
    overlay.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function close() {
    if (!overlay) return;
    overlay.classList.remove('open');
    overlay.querySelector('.vm-frame').innerHTML = ''; // 再生停止
    document.body.style.overflow = '';
  }

  // data-yt を持つ要素のクリックを拾う（イベント委譲）
  document.addEventListener('click', function (e) {
    var el = e.target.closest('[data-yt]');
    if (!el) return;
    e.preventDefault();
    open({ yt: el.getAttribute('data-yt'), t: el.getAttribute('data-t'), title: el.getAttribute('data-title') });
  });
})();
