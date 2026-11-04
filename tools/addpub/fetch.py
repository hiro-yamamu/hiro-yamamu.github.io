"""Resolve a URL into a Record using public metadata sources.

Order of attempts
  1. DOI in the URL  -> doi.org CSL-JSON (works for Crossref, JaLC, DataCite)
                        + Crossref REST API for event name / acronym when available
  2. IPSJ digital library (ipsj.ixsq.nii.ac.jp/records/N) -> WEKO3 JSON API, then HTML meta tags
  3. PDF                -> text of the first pages (for the LLM step) + venue/year from VRSJ URL pattern
  4. Any HTML page      -> Highwire "citation_*" meta tags + visible text
"""
from __future__ import annotations

import html as htmllib
import io
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse

import requests

from .model import Record, is_japanese

UA = "addpub/1.0 (+https://hiro-yamamu.github.io/; personal publication list updater)"
TIMEOUT = 40

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>#?]+)", re.I)
DOI_SUFFIXES = ("/full", "/pdf", "/abstract", "/xml", "/epub", "/meta", "/html", "/summary")


class FetchError(Exception):
    pass


def _get(url: str, **kw) -> requests.Response:
    headers = {"User-Agent": UA}
    headers.update(kw.pop("headers", {}))
    r = requests.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=True, **kw)
    r.raise_for_status()
    return r


# --------------------------------------------------------------------------- DOI
def extract_doi(url: str) -> str | None:
    m = DOI_RE.search(unquote(url))
    if not m:
        return None
    doi = m.group(1)
    changed = True
    while changed:
        changed = False
        for suf in DOI_SUFFIXES:
            if doi.lower().endswith(suf):
                doi = doi[: -len(suf)]
                changed = True
        stripped = doi.rstrip(".,;:)]}/")
        if stripped != doi:
            doi, changed = stripped, True
    return doi


def fetch_csl(doi: str) -> dict | None:
    try:
        r = _get(f"https://doi.org/{doi}", headers={"Accept": "application/vnd.citationstyles.csl+json"})
        return r.json()
    except (requests.RequestException, ValueError):
        return None


def fetch_crossref(doi: str) -> dict | None:
    try:
        r = _get(f"https://api.crossref.org/works/{doi}")
        return r.json().get("message")
    except (requests.RequestException, ValueError):
        return None


def _first(v):
    if isinstance(v, list):
        return v[0] if v else None
    return v


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(s)).strip()


def _add_author(rec: Record, given: str | None, family: str | None, literal: str | None) -> None:
    given = _clean(given or "")
    family = _clean(family or "")
    literal = _clean(literal or "")
    if family or given:
        if is_japanese(family + given):
            rec.authors_ja.append(f"{family} {given}".strip())
        else:
            rec.authors_en.append(f"{given} {family}".strip())
    elif literal:
        if is_japanese(literal):
            rec.authors_ja.append(literal)
        else:
            rec.authors_en.append(literal)


def _set_title(rec: Record, title: str | None) -> None:
    if not title:
        return
    title = _clean(title)
    if is_japanese(title):
        rec.title_ja = rec.title_ja or title
    else:
        rec.title_en = rec.title_en or title


def _set_venue(rec: Record, venue: str | None) -> None:
    if not venue:
        return
    venue = _clean(venue)
    if is_japanese(venue):
        rec.venue_ja = rec.venue_ja or venue
    else:
        rec.venue_en = rec.venue_en or venue


def _year_from_dateparts(d) -> int | None:
    try:
        return int(d["date-parts"][0][0])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _strip_event_prefix(name: str) -> str:
    """'SA '24: SIGGRAPH Asia 2024 XR' -> 'SIGGRAPH Asia 2024 XR'"""
    return re.sub(r"^[^:]{2,20}:\s*", "", name)


def apply_csl(rec: Record, csl: dict) -> None:
    rec.sources.append("doi.org CSL-JSON")
    t = (csl.get("type") or "").lower()
    if t in ("journal-article", "article-journal"):
        rec.category = rec.category or "journal"
    elif t in ("proceedings-article", "paper-conference"):
        rec.category = rec.category or "conference"   # refined later by language
    _set_title(rec, _first(csl.get("title")))
    if not rec.authors_en and not rec.authors_ja:
        for a in csl.get("author") or []:
            _add_author(rec, a.get("given"), a.get("family"), a.get("literal") or a.get("name"))
    _set_venue(rec, _first(csl.get("container-title")))
    rec.volume = rec.volume or csl.get("volume")
    rec.issue = rec.issue or csl.get("issue") or csl.get("number")
    rec.pages = rec.pages or csl.get("page")
    rec.article_number = rec.article_number or csl.get("article-number")
    rec.year = rec.year or _year_from_dateparts(csl.get("issued") or {}) or _year_from_dateparts(csl.get("published") or {})
    ev = csl.get("event") or csl.get("event-title")
    if isinstance(ev, str) and not rec.venue_en and not rec.venue_ja:
        _set_venue(rec, _strip_event_prefix(ev))


def apply_crossref(rec: Record, msg: dict) -> None:
    rec.sources.append("Crossref API")
    ev = msg.get("event") or {}
    acro = _clean(ev.get("acronym") or "")
    name = _clean(ev.get("name") or "")
    cont = _first(msg.get("container-title")) or ""
    if not rec.venue_en and not rec.venue_ja:
        _set_venue(rec, cont or _strip_event_prefix(name))
    if acro and rec.venue_en and acro.lower() not in rec.venue_en.lower():
        rec.venue_en = f"{rec.venue_en} ({acro})"
        rec.note(f"Venue acronym '{acro}' comes from Crossref's event record; shorten the venue by hand if you prefer (e.g. \"{acro}\")")
    if not rec.pages and msg.get("page"):
        rec.pages = msg["page"]
    if not rec.article_number and msg.get("article-number"):
        rec.article_number = msg["article-number"]
    for ot in msg.get("original-title") or []:
        _set_title(rec, ot)


# ------------------------------------------------------------------ HTML meta tags
class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: list[tuple[str, str]] = []
        self.text: list[str] = []
        self._skip = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            key = a.get("name") or a.get("property")
            if key and a.get("content") is not None:
                self.meta.append((key.lower(), a["content"]))
        elif tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            s = data.strip()
            if s:
                self.text.append(s)


def parse_html(body: str) -> _MetaParser:
    p = _MetaParser()
    p.feed(body)
    return p


def apply_highwire(rec: Record, meta: list[tuple[str, str]]) -> bool:
    """Google-Scholar style citation_* tags. Returns True if anything useful was found."""
    by: dict[str, list[str]] = {}
    for k, v in meta:
        by.setdefault(k, []).append(v.strip())
    found = False
    if "citation_title" in by:
        for t in by["citation_title"]:
            _set_title(rec, t)
        found = True
    if by.get("citation_author") and not rec.authors_en and not rec.authors_ja:
        for a in by["citation_author"]:
            if not a:
                continue
            if is_japanese(a):
                _add_author(rec, None, None, re.sub(r"[,，]\s*", " ", a))
            elif "," in a:
                fam, giv = [x.strip() for x in a.split(",", 1)]
                _add_author(rec, giv, fam, None)
            else:
                _add_author(rec, None, None, a)
        found = True
    for key in ("citation_journal_title", "citation_conference_title", "citation_conference", "citation_inbook_title"):
        for v in by.get(key, []):
            _set_venue(rec, v)
            if not rec.category:
                rec.category = "journal" if key == "citation_journal_title" else "conference"
    if by.get("citation_volume"):
        rec.volume = rec.volume or by["citation_volume"][0]
    if by.get("citation_issue"):
        rec.issue = rec.issue or by["citation_issue"][0]
    fp = by.get("citation_firstpage", [None])[0]
    lp = by.get("citation_lastpage", [None])[0]
    if fp and lp and not rec.pages:
        rec.pages = f"{fp}-{lp}"
    for key in ("citation_publication_date", "citation_date", "citation_online_date", "citation_year"):
        for v in by.get(key, []):
            m = re.search(r"(19|20)\d{2}", v)
            if m and not rec.year:
                rec.year = int(m.group(0))
    if by.get("citation_doi") and not rec.doi:
        rec.doi = extract_doi(by["citation_doi"][0])
    if found:
        rec.sources.append("HTML citation_* meta tags")
    return found


# -------------------------------------------------------------------------- IPSJ DL
IPSJ_RE = re.compile(r"https?://ipsj\.ixsq\.nii\.ac\.jp/records?/(\d+)", re.I)


def _walk(obj, fn):
    if isinstance(obj, dict):
        fn(obj)
        for v in obj.values():
            _walk(v, fn)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, fn)


def apply_ipsj_json(rec: Record, data: dict) -> bool:
    """Tolerant walk of a WEKO3 record: bilingual titles, creator names, bibliographic info."""
    titles: list[tuple[str, str]] = []
    creators: list[list[tuple[str, str]]] = []
    biblio: dict = {}

    def visit(d: dict):
        if "subitem_title" in d:
            titles.append((str(d.get("subitem_title_language", "")), d["subitem_title"]))
        if isinstance(d.get("creatorNames"), list):
            creators.append([(str(n.get("creatorNameLang", "")), n.get("creatorName", "")) for n in d["creatorNames"] if isinstance(n, dict)])
        if "bibliographic_title" in d:
            biblio.setdefault("titles", []).append((str(d.get("bibliographic_titleLang", "")), d["bibliographic_title"]))
        for k in ("bibliographicVolumeNumber", "bibliographicIssueNumber", "bibliographicPageStart", "bibliographicPageEnd"):
            if k in d:
                biblio[k] = d[k]
        if "bibliographicIssueDate" in d:
            biblio["date"] = d["bibliographicIssueDate"]
        if "subitem_conference_name" in d:
            biblio.setdefault("conf", []).append((str(d.get("subitem_conference_name_language", "")), d["subitem_conference_name"]))

    _walk(data, visit)
    if not titles and not creators:
        return False
    rec.sources.append("IPSJ DL (WEKO3 JSON)")
    for _lang, t in titles:
        _set_title(rec, t)
    if not rec.authors_en and not rec.authors_ja:
        for names in creators:
            ja = next((n for lang, n in names if is_japanese(n)), None)
            en = next((n for lang, n in names if n and not is_japanese(n)), None)
            if ja:
                rec.authors_ja.append(_clean(re.sub(r"[,，]\s*", " ", ja)))
            if en:
                if "," in en:
                    fam, giv = [x.strip() for x in en.split(",", 1)]
                    rec.authors_en.append(_clean(f"{giv} {fam}"))
                else:
                    rec.authors_en.append(_clean(en))
    for _lang, t in biblio.get("titles", []) + biblio.get("conf", []):
        _set_venue(rec, t)
    rec.volume = rec.volume or biblio.get("bibliographicVolumeNumber")
    rec.issue = rec.issue or biblio.get("bibliographicIssueNumber")
    ps, pe = biblio.get("bibliographicPageStart"), biblio.get("bibliographicPageEnd")
    if ps and pe and not rec.pages:
        rec.pages = f"{ps}-{pe}"
    if biblio.get("date") and not rec.year:
        m = re.search(r"(19|20)\d{2}", str(biblio["date"]))
        if m:
            rec.year = int(m.group(0))
    if not rec.category:
        v = rec.venue_ja or rec.venue_en or ""
        rec.category = "journal" if ("論文誌" in v or "Journal" in v or "Transactions" in v) else "domestic"
    return True


# ------------------------------------------------------------------------------ PDF
def pdf_text(content: bytes, pages: int = 2) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(content))
        return "\n".join((p.extract_text() or "") for p in reader.pages[:pages])
    except Exception:  # noqa: BLE001 - any PDF parse failure just means no text
        return ""


VRSJ_RE = re.compile(r"conference\.vrsj\.org/ac(\d{4})/", re.I)


def apply_url_hints(rec: Record, url: str, cfg: dict) -> None:
    m = VRSJ_RE.search(url)
    if m:
        year = int(m.group(1))
        n = year - int(cfg.get("vrsj_first_year", 1996)) + 1
        rec.year = rec.year or year
        rec.venue_ja = rec.venue_ja or f"第{n}回 日本バーチャルリアリティ学会大会"
        rec.category = rec.category or "domestic"
        rec.note(f"Venue inferred from the VRSJ URL: 第{n}回 日本バーチャルリアリティ学会大会 ({year})")


# ------------------------------------------------------------------------ venue table
def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def apply_venue_table(rec: Record, cfg: dict) -> None:
    """Fill the other language of a venue from config['venues']."""
    for v in cfg.get("venues", []):
        matched = False
        if "ja" in v:
            if rec.venue_ja and rec.venue_ja.replace(" ", "") == v["ja"].replace(" ", ""):
                rec.venue_en = rec.venue_en or v["en"]
                matched = True
            elif rec.venue_en and rec.venue_en.lower() == v["en"].lower():
                rec.venue_ja = rec.venue_ja or v["ja"]
                matched = True
        elif "ja_pattern" in v and rec.venue_ja:
            m = re.match(v["ja_pattern"], rec.venue_ja.strip())
            if m:
                groups = m.groups()
                try:
                    n = int(groups[0]) if groups else 0
                except ValueError:
                    n = 0
                rec.venue_en = rec.venue_en or v["en_format"].format(*groups, ordinal=_ordinal(n))
                matched = True
        if matched:
            if rec.category in (None, "conference") and v.get("category"):
                rec.category = v["category"]
            return


JOURNAL_WORDS = re.compile(r"journal|transactions|論文誌|letters|review", re.I)
CONF_WORDS = re.compile(r"conference|symposium|proceedings|workshop|congress|meeting|大会|研究会|シンポジウム|講演会|研究発表会", re.I)


def finalize_category(rec: Record) -> None:
    if rec.category is None:
        venue = f"{rec.venue_en or ''} {rec.venue_ja or ''}"
        if JOURNAL_WORDS.search(venue):
            rec.category = "journal"
        elif CONF_WORDS.search(venue):
            rec.category = "conference"
    if rec.category == "conference":
        rec.category = "domestic" if (rec.title_ja or rec.venue_ja) else "international"
    if rec.category is None and (rec.title_ja or rec.venue_ja):
        rec.category = "domestic"


def normalize_url(url: str) -> str:
    """Accept '10.1234/abc', 'doi:10.1234/abc' or 'https://...' and return a fetchable URL."""
    url = url.strip().strip("<>")
    if re.match(r"^(doi:)?10\.\d{4,9}/", url, re.I):
        return "https://doi.org/" + re.sub(r"^doi:", "", url, flags=re.I)
    if re.match(r"^(www\.|[a-z0-9-]+\.[a-z]{2,})", url, re.I) and "://" not in url:
        return "https://" + url
    return url


def link_label(url: str, cfg: dict) -> str:
    host = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()
    for rule in cfg.get("link_labels", []):
        if "host" in rule and host.endswith(rule["host"]):
            return rule["label"]
        if "suffix" in rule and path.endswith(rule["suffix"]):
            return rule["label"]
    return "Link"


# --------------------------------------------------------------------------- driver
def resolve(url: str, cfg: dict) -> Record:
    url = normalize_url(url)
    rec = Record(source_url=url)
    host = urlparse(url).netloc.lower()
    is_doi_host = host.endswith("doi.org")

    doi = extract_doi(url)
    if doi:
        rec.doi = doi
        csl = fetch_csl(doi)
        if csl and csl.get("title"):
            apply_csl(rec, csl)
        cr = fetch_crossref(doi)
        if cr:
            apply_crossref(rec, cr)

    m = IPSJ_RE.match(url)
    if m:
        try:
            data = _get(f"https://ipsj.ixsq.nii.ac.jp/api/records/{m.group(1)}", headers={"Accept": "application/json"}).json()
            apply_ipsj_json(rec, data)
        except (requests.RequestException, ValueError):
            rec.note("IPSJ DL JSON API unavailable; fell back to the HTML page")

    have_title = bool(rec.title_en or rec.title_ja)
    if not (is_doi_host and have_title):
        try:
            r = _get(url)
            ctype = r.headers.get("Content-Type", "").lower()
            if "pdf" in ctype or url.lower().endswith(".pdf"):
                rec.page_text = pdf_text(r.content)
                rec.sources.append("PDF text")
                if not rec.page_text:
                    rec.note("PDF has no extractable text")
            else:
                # requests assumes ISO-8859-1 for text/* without a charset; sniff instead
                enc = r.encoding if "charset" in ctype else (r.apparent_encoding or "utf-8")
                body = r.content.decode(enc or "utf-8", errors="replace")
                parsed = parse_html(body)
                apply_highwire(rec, parsed.meta)
                if not rec.doi:
                    for k, v in parsed.meta:
                        if k in ("citation_doi", "dc.identifier", "dc.identifier.doi") and extract_doi(v):
                            rec.doi = extract_doi(v)
                            break
                if rec.doi and not (rec.title_en or rec.title_ja):
                    csl = fetch_csl(rec.doi)
                    if csl and csl.get("title"):
                        apply_csl(rec, csl)
                rec.page_text = (parsed.title + "\n" + "\n".join(parsed.text))[:12000]
        except requests.RequestException as e:
            if not have_title:
                raise FetchError(f"Could not fetch {url}: {e}") from e
            rec.note(f"Page fetch failed ({e}); used DOI metadata only")

    apply_url_hints(rec, url, cfg)
    apply_venue_table(rec, cfg)
    finalize_category(rec)

    if rec.doi:
        rec.links.append(("DOI", f"https://doi.org/{rec.doi}"))
    if not is_doi_host:
        label = link_label(url, cfg)
        # A publisher landing page for the same DOI adds nothing over the DOI link
        # unless a config rule gives it a specific label (Full text, PDF, IPSJ DL ...).
        redundant = bool(rec.doi) and label == "Link" and rec.doi.lower() in url.lower()
        if not redundant:
            rec.links.append((label, url))
    return rec
