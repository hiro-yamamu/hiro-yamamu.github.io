"""Author-name dictionary (Japanese <-> English) learned from index.html plus config overrides.

Every bilingual entry on the site lists the same authors in the same order in its
<span class="ja"> and <span class="en"> halves, so the pairs can be read off directly.
"""
from __future__ import annotations

import re

TAG = re.compile(r"<[^>]+>")
PAIR = re.compile(r'<span class="ja">(.*?)</span>\s*<span class="en">(.*?)</span>', re.S)


def _norm_ja(name: str) -> str:
    return re.sub(r"[\s　]+", "", name)


def _authors_before_title(fragment: str) -> list[str] | None:
    """'A, B, "Title," ...' -> ['A', 'B'] ; None if there is no quoted title."""
    text = TAG.sub("", fragment)
    if '"' not in text:
        return None
    head = text.split('"', 1)[0].strip().rstrip(",").strip()
    if not head:
        return None
    parts = [p.strip() for p in head.split(",") if p.strip()]
    return parts or None


class NameBook:
    def __init__(self, html: str = "", overrides: dict[str, str] | None = None):
        self.ja2en: dict[str, str] = {}
        self.en2ja: dict[str, str] = {}
        for ja, en in PAIR.findall(html):
            a_ja = _authors_before_title(ja)
            a_en = _authors_before_title(en)
            if a_ja and a_en and len(a_ja) == len(a_en):
                for j, e in zip(a_ja, a_en):
                    self.add(j, e)
        for j, e in (overrides or {}).items():
            self.add(j, e)

    def add(self, ja: str, en: str) -> None:
        ja = ja.strip()
        en = en.strip()
        if not ja or not en:
            return
        self.ja2en.setdefault(_norm_ja(ja), en)
        self.en2ja.setdefault(en.lower(), ja)

    def to_en(self, ja: str) -> str | None:
        return self.ja2en.get(_norm_ja(ja))

    def to_ja(self, en: str) -> str | None:
        return self.en2ja.get(en.strip().lower())

    def glossary(self) -> list[tuple[str, str]]:
        seen = set()
        out = []
        for ja_key, en in self.ja2en.items():
            if en not in seen:
                seen.add(en)
                out.append((self.en2ja.get(en.lower(), ja_key), en))
        return out
