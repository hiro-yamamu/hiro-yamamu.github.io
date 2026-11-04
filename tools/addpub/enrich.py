"""Optional LLM step: fill the gaps public metadata leaves (English titles of Japanese papers,
author readings, venues, papers that only exist as a PDF).

Runs only when ANTHROPIC_API_KEY is set (locally or as a GitHub Actions secret) and the
``anthropic`` package is installed. Known fields are never overwritten.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from .model import Record, is_japanese
from .names import NameBook

MODEL = "claude-opus-5-5"


def available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        import pydantic  # noqa: F401
    except ImportError:
        return False
    return True


def _schema():
    from pydantic import BaseModel, Field

    class Extracted(BaseModel):
        title_ja: Optional[str] = Field(None, description="Japanese title, only if the paper has one")
        title_en: Optional[str] = Field(None, description="English title (official if given, else a faithful translation)")
        authors_ja: list[str] = Field(default_factory=list, description="Authors in Japanese, '姓 名', in paper order")
        authors_en: list[str] = Field(default_factory=list, description="Authors in English, 'Given Family', same order")
        venue_ja: Optional[str] = None
        venue_en: Optional[str] = None
        year: Optional[int] = None
        category: Optional[str] = Field(None, description="journal | international | domestic")
        presentation: Optional[str] = Field(None, description="e.g. Poster, Oral, Demo, Short paper; null if unknown")
        volume: Optional[str] = None
        issue: Optional[str] = None
        pages: Optional[str] = Field(None, description="e.g. 13-22")
        confidence: str = Field("medium", description="low | medium | high")
        remarks: Optional[str] = Field(None, description="anything the human should double-check")

    return Extracted


SYSTEM = """You complete bibliographic records for a researcher's personal publication list.
You receive the fields already known (from DOI / library metadata), a glossary of co-author names
(Japanese <-> English) that are known to be correct, and raw text from the paper's web page or PDF.

Rules
- Never change a field that is already filled; only fill empty ones. Copy known fields through unchanged.
- authors_ja / authors_en must list the SAME people in the SAME order. Use the glossary for any name it
  covers. For names not in the glossary, give the most standard Hepburn romanization ('Given Family').
- Japanese papers need an English title: use the official English title if the page/PDF has one,
  otherwise translate faithfully (sentence case, no trailing period).
- venue: full name of the journal / conference. For Japanese venues give both languages, e.g.
  '第31回 日本バーチャルリアリティ学会大会' / '31st Annual Conference of the Virtual Reality Society of Japan',
  '情報処理学会 エンタテインメントコンピューティング2025' / 'IPSJ Entertainment Computing Symposium 2025 (EC2025)'.
- category: 'journal' for journal articles; 'international' for conference papers written in English at
  international venues; 'domestic' for Japanese conference papers.
- Leave a field null/empty if the text does not support it. Do not invent page numbers or volumes.
"""


def enrich(rec: Record, book: NameBook) -> Record:
    import anthropic

    Extracted = _schema()
    known = rec.to_dict()
    known.pop("links", None)
    known.pop("notes", None)
    known.pop("sources", None)
    glossary = "\n".join(f"{ja} = {en}" for ja, en in book.glossary())
    user = (
        "Known fields (JSON):\n" + json.dumps(known, ensure_ascii=False, indent=1)
        + "\n\nGlossary of known author names:\n" + (glossary or "(none)")
        + "\n\nPage / PDF text:\n" + (rec.page_text or "(none)")[:12000]
    )

    client = anthropic.Anthropic()
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM,
        messages=[{"role": "user", "content": user}],
        output_format=Extracted,
    )
    if resp.stop_reason == "refusal":
        rec.note("LLM enrichment declined the request; metadata left as fetched")
        return rec
    ex = resp.parsed_output
    if ex is None:
        rec.note("LLM enrichment returned no structured output")
        return rec

    rec.sources.append(f"LLM enrichment ({MODEL})")
    if not rec.title_ja and ex.title_ja and is_japanese(ex.title_ja):
        rec.title_ja = ex.title_ja
    if not rec.title_en and ex.title_en:
        rec.title_en = ex.title_en
    if not rec.authors_ja and ex.authors_ja:
        rec.authors_ja = ex.authors_ja
    if not rec.authors_en and ex.authors_en:
        rec.authors_en = ex.authors_en
    if rec.authors_ja and rec.authors_en and len(rec.authors_ja) != len(rec.authors_en):
        rec.note("Author lists differ in length between Japanese and English; please check")
    if not rec.venue_ja and ex.venue_ja:
        rec.venue_ja = ex.venue_ja
    if not rec.venue_en and ex.venue_en:
        rec.venue_en = ex.venue_en
    if not rec.year and ex.year:
        rec.year = ex.year
    if rec.category in (None, "conference") and ex.category in ("journal", "international", "domestic"):
        rec.category = ex.category
    if not rec.presentation and ex.presentation:
        rec.presentation = ex.presentation
    if not rec.volume and ex.volume:
        rec.volume = ex.volume
    if not rec.issue and ex.issue:
        rec.issue = ex.issue
    if not rec.pages and ex.pages:
        rec.pages = ex.pages
    if ex.remarks:
        rec.note(f"LLM remark: {ex.remarks}")
    if ex.confidence == "low":
        rec.note("LLM confidence: low — please double-check this entry")
    return rec
