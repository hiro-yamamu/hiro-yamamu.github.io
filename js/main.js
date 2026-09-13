// ---------- Language switching (ja / en) ----------
// The HTML ships with <body class="lang-ja"> so the page reads fine without JS.
(function () {
  var KEY = 'site-lang';
  var body = document.body;
  var buttons = document.querySelectorAll('.lang-btn');

  function initial() {
    var q = /[?&]lang=(ja|en)/.exec(location.search);
    if (q) return q[1];
    try {
      var saved = localStorage.getItem(KEY);
      if (saved === 'ja' || saved === 'en') return saved;
    } catch (e) { /* ignore */ }
    var nav = (navigator.language || 'ja').toLowerCase();
    return nav.indexOf('ja') === 0 ? 'ja' : 'en';
  }

  function setLang(lang) {
    body.classList.remove('lang-ja', 'lang-en');
    body.classList.add('lang-' + lang);
    document.documentElement.setAttribute('lang', lang);
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].setAttribute('aria-pressed', buttons[i].getAttribute('data-lang') === lang ? 'true' : 'false');
    }
    try { localStorage.setItem(KEY, lang); } catch (e) { /* ignore */ }
  }

  setLang(initial());

  for (var i = 0; i < buttons.length; i++) {
    buttons[i].addEventListener('click', function () {
      setLang(this.getAttribute('data-lang'));
    });
  }
})();

// ---------- Footer year ----------
(function () {
  var y = document.getElementById('year');
  if (y) y.textContent = new Date().getFullYear();
})();

// ---------- YouTube click-to-load embeds ----------
// <div class="video" data-yt="VIDEO_ID" data-title="caption"></div>
(function () {
  var slots = document.querySelectorAll('.video[data-yt]');
  for (var i = 0; i < slots.length; i++) {
    (function (slot) {
      var id = slot.getAttribute('data-yt');
      var title = slot.getAttribute('data-title') || 'Video';

      var poster = slot.getAttribute('data-poster');
      var thumb = document.createElement('img');
      thumb.alt = '';
      if (poster) {
        thumb.src = poster;
      } else {
        thumb.src = 'https://i.ytimg.com/vi/' + id + '/maxresdefault.jpg';
        thumb.onload = function () {
          // YouTube returns a 120x90 placeholder when maxres does not exist
          if (thumb.naturalWidth < 200) thumb.src = 'https://i.ytimg.com/vi/' + id + '/hqdefault.jpg';
        };
        thumb.onerror = function () { thumb.src = 'https://i.ytimg.com/vi/' + id + '/hqdefault.jpg'; };
      }

      var btn = document.createElement('button');
      btn.className = 'video-play';
      btn.type = 'button';
      btn.setAttribute('aria-label', 'Play: ' + title);

      slot.appendChild(thumb);
      slot.appendChild(btn);

      btn.addEventListener('click', function () {
        var iframe = document.createElement('iframe');
        iframe.src = 'https://www.youtube-nocookie.com/embed/' + id + '?autoplay=1&rel=0';
        iframe.title = title;
        iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';
        iframe.allowFullscreen = true;
        slot.innerHTML = '';
        slot.appendChild(iframe);
      });
    })(slots[i]);
  }
})();
