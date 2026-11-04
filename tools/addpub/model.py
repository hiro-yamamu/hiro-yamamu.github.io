from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]")


def is_japanese(text: str | None) -> bool:
    return bool(text) and bool(CJK.search(text))


@dataclass
class Record:
    source_url: str
    doi: str | None = None
    category: str | None = None            # journal | international | domestic
    title_en: str | None = None
    title_ja: str | None = None
    authors_en: list[str] = field(default_factory=list)   # "Given Family"
    authors_ja: list[str] = field(default_factory=list)   # "姓 名"
    venue_en: str | None = None
    venue_ja: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None               # "1-2"
    article_number: str | None = None
    presentation: str | None = None        # "Poster", "Oral", "Short paper", ...
    year: int | None = None
    links: list[tuple[str, str]] = field(default_factory=list)   # (label, url)
    notes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    page_text: str | None = None           # raw text for LLM enrichment, never rendered

    # ----- derived -----
    @property
    def japanese_paper(self) -> bool:
        """A paper written in Japanese: gets a ja span and an en span with '(in Japanese)'."""
        return bool(self.title_ja)

    def missing(self) -> list[str]:
        """Fields that must be present before the entry can be rendered well."""
        m = []
        if not (self.title_en or self.title_ja):
            m.append("title")
        if not (self.authors_en or self.authors_ja):
            m.append("authors")
        if not (self.venue_en or self.venue_ja):
            m.append("venue")
        if not self.year:
            m.append("year")
        if not self.category:
            m.append("category")
        if self.japanese_paper and not self.title_en:
            m.append("title_en")
        if self.japanese_paper and not self.venue_en:
            m.append("venue_en")
        if self.authors_ja and not self.authors_en:
            m.append("authors_en")
        return m

    def note(self, msg: str) -> None:
        if msg not in self.notes:
            self.notes.append(msg)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("page_text", None)
        d["links"] = [list(x) for x in self.links]
        return d
