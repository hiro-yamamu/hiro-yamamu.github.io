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
