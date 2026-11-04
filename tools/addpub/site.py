"""Edit index.html / sitemap.xml: insert the new <li> in the right category, newest first."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .model import Record


class DuplicateError(Exception):
    pass


class SiteError(Exception):
    pass


YEAR_IN_LI = re.compile(r",\s*((?:19|20)\d{2})\.")


def read(path: Path) -> str:
    """Text with '\\n' line endings regardless of what the file uses on disk."""
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def eol_of(path: Path) -> str:
    return "\r\n" if b"\r\n" in path.read_bytes() else "\n"


def write(path: Path, text: str, eol: str = "\n") -> None:
    """Write back with the file's original line endings so git sees only the real change."""
    data = text.replace("\r\n", "\n")
    if eol != "\n":
        data = data.replace("\n", eol)
    path.write_bytes(data.encode("utf-8"))


def find_duplicate(html: str, rec: Record) -> str | None:
    hay = html.lower()
    if rec.doi and rec.doi.lower() in hay:
        return f"DOI {rec.doi}"
    if rec.source_url.lower().rstrip("/") in hay:
        return rec.source_url
    for t in (rec.title_en, rec.title_ja):
        if t and len(t) > 20 and t.lower() in hay:
            return f'title "{t}"'
    return None


def _section(html: str, heading_en: str) -> tuple[int, int]:
    """(start, end) offsets of the <ol class="pub-list"> body that follows the given heading."""
    h = re.search(
        r'<h3 class="pub-category">[^\n]*?<span class="en">' + re.escape(heading_en) + r'</span></h3>\s*<ol class="pub-list">\n',
        html,
    )
    if not h:
        raise SiteError(f'Could not find the "{heading_en}" list in index.html')
    start = h.end()
    end = html.find("</ol>", start)
    if end < 0:
        raise SiteError(f'Unterminated list for "{heading_en}"')
    return start, end


def insert_li(html: str, li: str, heading_en: str, year: int | None, indent: str = "        ") -> str:
    start, end = _section(html, heading_en)
    body = html[start:end]
    lines = body.split("\n")
    pos = None
    if year:
        for i, line in enumerate(lines):
            if "<li>" not in line:
                continue
            m = YEAR_IN_LI.search(line)
            if m and int(m.group(1)) <= year:
                pos = i
                break
    if pos is None:
        # newest-first list: no older entry found -> append after the last <li>
        last = max((i for i, l in enumerate(lines) if "<li>" in l), default=-1)
        pos = last + 1
    lines.insert(pos, indent + li)
    return html[:start] + "\n".join(lines) + html[end:]


def touch_dates(html: str, sitemap: str | None, today: dt.date | None = None) -> tuple[str, str | None]:
    d = (today or dt.date.today()).isoformat()
    html = re.sub(r"Last updated: \d{4}-\d{2}-\d{2}", f"Last updated: {d}", html, count=1)
    if sitemap is not None:
        sitemap = re.sub(r"<lastmod>\d{4}-\d{2}-\d{2}</lastmod>", f"<lastmod>{d}</lastmod>", sitemap, count=1)
    return html, sitemap
