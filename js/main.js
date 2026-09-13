// ---------- Language toggle (ja / en) ----------
(function () {
  var STORAGE_KEY = 'site-lang';
  var body = document.body;
  var toggle = document.getElementById('lang-toggle');
  var opts = toggle ? toggle.querySelectorAll('.lang-opt') : [];

  function detectDefault() {
    try {
      var saved = localStorage.getItem(STORAGE_KEY);
      if (saved === 'ja' || saved === 'en') return saved;
    } catch (e) { /* ignore */ }
    var nav = (navigator.language || 'ja').toLowerCase();
    return nav.indexOf('ja') === 0 ? 'ja' : 'en';
  }

  function setLang(lang) {
    body.classList.remove('lang-ja', 'lang-en');
    body.classList.add('lang-' + lang);
    document.documentElement.setAttribute('lang', lang);
    for (var i = 0; i < opts.length; i++) {
      opts[i].classList.toggle('active', opts[i].getAttribute('data-lang') === lang);
    }
    try { localStorage.setItem(STORAGE_KEY, lang); } catch (e) { /* ignore */ }
  }

  var current = detectDefault();
  setLang(current);

  if (toggle) {
    toggle.addEventListener('click', function () {
      current = current === 'ja' ? 'en' : 'ja';
      setLang(current);
    });
  }
})();

// ---------- Footer year ----------
(function () {
  var y = document.getElementById('year');
  if (y) y.textContent = new Date().getFullYear();
})();

// ---------- YouTube click-to-load embeds ----------
// <div class="video" data-yt="VIDEO_ID" data-title="optional caption"></div>
(function () {
  var slots = document.querySelectorAll('.video[data-yt]');
  for (var i = 0; i < slots.length; i++) {
    (function (slot) {
      var id = slot.getAttribute('data-yt');
      var title = slot.getAttribute('data-title') || 'Video';
      var thumb = document.createElement('img');
      thumb.src = 'https://i.ytimg.com/vi/' + id + '/hqdefault.jpg';
      thumb.alt = title;
      thumb.loading = 'lazy';
      var btn = document.createElement('button');
      btn.className = 'video-play';
      btn.type = 'button';
      btn.setAttribute('aria-label', 'Play ' + title);
      var cap = document.createElement('span');
      cap.className = 'video-title';
      cap.textContent = title;
      slot.appendChild(thumb);
      slot.appendChild(btn);
      slot.appendChild(cap);
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
