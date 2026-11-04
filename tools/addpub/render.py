"""Turn a Record into one <li> line matching the conventions used in index.html."""
from __future__ import annotations

import html
import re

from .model import Record


def _esc(s: str) -> str:
    return html.escape(s, quote=False).replace('"', "&quot;")


def _pages(p: str | None) -> str | None:
    if not p:
        return None
    p = p.strip().replace("--", "-").replace("–", "-")
    m = re.match(r"^(\w+)\s*-\s*(\w+)$", p)
    if m:
        return f"pp. {m.group(1)}–{m.group(2)}"
    return f"p. {p}"


def _norm_ja(name: str) -> str:
    return re.sub(r"[\s　]+", "", name)


def _authors(names: list[str], self_names: list[str], ja: bool) -> str:
    if ja:
        selfset = {_norm_ja(n) for n in self_names}
        key = _norm_ja
    else:
        selfset = {n.strip().lower() for n in self_names}
        key = lambda n: n.strip().lower()  # noqa: E731
    out = []
    for n in names:
        e = _esc(n.strip())
        out.append(f"<b>{e}</b>" if key(n) in selfset else e)
    return ", ".join(out)


def presentation_pair(p: str | None, cfg: dict) -> tuple[str | None, str | None]:
    """'Oral' or '口頭' -> ('Oral', '口頭') using config['presentations']; unknown words are used as-is."""
    if not p:
        return None, None
    p = p.strip()
    table = cfg.get("presentations", {})
    for en, ja in table.items():
        if p.lower() == en.lower() or p == ja:
            return en, ja
    return p, p


def _tail(rec: Record, cfg: dict, lang: str = "en") -> list[str]:
    """Bits after the venue: vol/no or presentation/pages, then year."""
    parts: list[str] = []
    if rec.category == "journal":
        if rec.volume:
            parts.append(f"vol. {_esc(str(rec.volume))}")
        if rec.issue:
            parts.append(f"no. {_esc(str(rec.issue))}")
    else:
        p_en, p_ja = presentation_pair(rec.presentation, cfg)
        pres = p_ja if lang == "ja" else p_en
        if pres:
            parts.append(_esc(pres))
        if rec.article_number and rec.category == "international":
            parts.append(f"Article {_esc(str(rec.article_number))}")
        pg = _pages(rec.pages)
        if pg:
            parts.append(_esc(pg))
    if rec.year:
        parts.append(str(rec.year))
    return parts


def _links(rec: Record) -> str:
    seen = set()
    out = []
    for label, url in rec.links:
        if url in seen:
            continue
        seen.add(url)
        out.append(f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener">{_esc(label)}</a>')
    return " ".join(out)


def _citation(authors: str, title: str, venue_html: str, tail: list[str], suffix: str = "") -> str:
    s = f'{authors}, "{_esc(title)}," {venue_html}'
    if tail:
        s += ", " + ", ".join(tail)
    s += "." + suffix
    return s


def render_li(rec: Record, cfg: dict) -> str:
    self_en = cfg["self"]["en"]
    self_ja = cfg["self"]["ja"]
    tail = _tail(rec, cfg, "en")
    links = _links(rec)

    if rec.title_ja:
        # Paper written in Japanese: full Japanese citation + full English citation.
        a_ja = _authors(rec.authors_ja or rec.authors_en, self_ja + self_en, ja=bool(rec.authors_ja))
        a_en = _authors(rec.authors_en or rec.authors_ja, self_en + self_ja, ja=not rec.authors_en)
        v_ja = f"<i>{_esc(rec.venue_ja or rec.venue_en or '')}</i>"
        v_en = f"<i>{_esc(rec.venue_en or rec.venue_ja or '')}</i>"
        ja = _citation(a_ja, rec.title_ja, v_ja, _tail(rec, cfg, "ja"))
        en = _citation(a_en, rec.title_en or rec.title_ja, v_en, tail, " (in Japanese)")
        body = f'<span class="ja">{ja}</span><span class="en">{en}</span>'
    elif rec.venue_ja and rec.venue_en:
        # English title at a Japanese venue: shared citation, venue switches by language.
        a_en = _authors(rec.authors_en or rec.authors_ja, self_en + self_ja, ja=not rec.authors_en)
        venue = f'<span class="ja"><i>{_esc(rec.venue_ja)}</i></span><span class="en"><i>{_esc(rec.venue_en)}</i></span>'
        body = _citation(a_en, rec.title_en or "", venue, tail)
    else:
        a_en = _authors(rec.authors_en or rec.authors_ja, self_en + self_ja, ja=not rec.authors_en)
        venue = f"<i>{_esc(rec.venue_en or rec.venue_ja or '')}</i>"
        body = _citation(a_en, rec.title_en or "", venue, tail)

    return f"<li>{body}{(' ' + links) if links else ''}</li>"


def plain_text(li_html: str) -> str:
    """Rough text preview of an <li> (English half for bilingual entries)."""
    s = re.sub(r'<span class="ja">.*?</span>', "", li_html, flags=re.S)
    s = re.sub(r"<a [^>]*>(.*?)</a>", r"[\1]", s)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(re.sub(r"\s+", " ", s)).strip()
