"""Parse the body of a GitHub issue created from .github/ISSUE_TEMPLATE/add-publication.yml."""
from __future__ import annotations

import re

# "### <label>" headings as rendered by GitHub issue forms -> field names
LABELS = {
    "URL": "url",
    "カテゴリ": "category",
    "日本語タイトル": "title_ja",
    "英語タイトル": "title_en",
    "著者（日本語）": "authors_ja",
    "著者（英語）": "authors_en",
    "発表媒体（日本語）": "venue_ja",
    "発表媒体（英語）": "venue_en",
    "年": "year",
    "発表形式": "presentation",
    "巻 / 号 / ページ": "vip",
    "備考": "note",
}
CATEGORY_WORDS = {
    "自動判定": None,
    "学術論文": "journal",
    "国際会議": "international",
    "国内会議": "domestic",
    "journal": "journal",
    "international": "international",
    "domestic": "domestic",
    "auto": None,
}


def parse_issue_body(body: str) -> dict:
    fields: dict[str, str] = {}
    parts = re.split(r"^###\s+(.+?)\s*$", body.replace("\r\n", "\n"), flags=re.M)
    # parts = [preamble, label1, value1, label2, value2, ...]
    for i in range(1, len(parts) - 1, 2):
        label = parts[i].strip()
        value = parts[i + 1].strip()
        if value in ("_No response_", "None", ""):
            continue
        key = LABELS.get(label)
        if key:
            fields[key] = value
    return normalize(fields)


def normalize(f: dict) -> dict:
    out: dict = {}
    if f.get("url"):
        m = re.search(r"https?://\S+", f["url"])
        out["url"] = m.group(0).rstrip(">)]") if m else f["url"].strip()
    if "category" in f:
        out["category"] = CATEGORY_WORDS.get(f["category"].strip(), None)
    for k in ("title_ja", "title_en", "venue_ja", "venue_en", "presentation", "note"):
        if f.get(k):
            out[k] = f[k].strip()
    for k in ("authors_ja", "authors_en"):
        if f.get(k):
            out[k] = [a.strip() for a in re.split(r"[,、，;\n]+", f[k]) if a.strip()]
    if f.get("year"):
        m = re.search(r"(19|20)\d{2}", f["year"])
        if m:
            out["year"] = int(m.group(0))
    if f.get("vip"):
        v = f["vip"]
        m = re.search(r"vol\.?\s*(\w+)", v, re.I)
        if m:
            out["volume"] = m.group(1)
        m = re.search(r"no\.?\s*(\w+)", v, re.I)
        if m:
            out["issue"] = m.group(1)
        m = re.search(r"pp?\.?\s*(\w+\s*[-–]\s*\w+|\w+)", v, re.I)
        if m:
            out["pages"] = m.group(1).replace(" ", "")
    return out
