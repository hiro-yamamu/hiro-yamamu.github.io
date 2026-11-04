"""Command line / CI entry point.

  python -m tools.addpub <URL> [--category journal|international|domestic] [--dry-run] [--push]
  python -m tools.addpub --from-env --json        # used by the GitHub Actions workflow

Exit codes: 0 added, 2 duplicate, 3 metadata insufficient (needs manual fields), 1 other error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from . import enrich as enrich_mod
from .fetch import FetchError, resolve
from .issue import parse_issue_body
from .model import Record
from .names import NameBook
from .render import plain_text, render_li
from .site import DuplicateError, SiteError, eol_of, find_duplicate, insert_li, read, touch_dates, write

ROOT = Path(__file__).resolve().parents[2]
CFG_PATH = Path(__file__).with_name("config.json")

FIELD_LABELS_JA = {
    "title": "タイトル", "title_en": "英語タイトル", "authors": "著者", "authors_en": "著者（英語）",
    "venue": "発表媒体", "venue_en": "発表媒体（英語）", "year": "年", "category": "カテゴリ",
}


def load_cfg() -> dict:
    return json.loads(CFG_PATH.read_text(encoding="utf-8"))


def apply_overrides(rec: Record, ov: dict) -> None:
    for k in ("category", "title_ja", "title_en", "venue_ja", "venue_en", "presentation", "volume", "issue", "pages", "year"):
        if ov.get(k) not in (None, ""):
            setattr(rec, k, ov[k])
    for k in ("authors_ja", "authors_en"):
        if ov.get(k):
            setattr(rec, k, list(ov[k]))


def fill_names(rec: Record, book: NameBook) -> None:
    """Translate author lists through the dictionary when one side is missing."""
    if rec.authors_ja and not rec.authors_en:
        en = [book.to_en(a) for a in rec.authors_ja]
        if all(en):
            rec.authors_en = en  # type: ignore[assignment]
        else:
            unknown = [a for a, e in zip(rec.authors_ja, en) if not e]
            rec.note("No English reading on file for: " + ", ".join(unknown))
    elif rec.authors_en and not rec.authors_ja and rec.title_ja:
        ja = [book.to_ja(a) for a in rec.authors_en]
        if all(ja):
            rec.authors_ja = ja  # type: ignore[assignment]


def run(url: str, overrides: dict, *, dry_run: bool, use_llm: bool, push: bool, commit: bool, ignore_duplicate: bool = False) -> dict:
    cfg = load_cfg()
    index_path = ROOT / "index.html"
    sitemap_path = ROOT / "sitemap.xml"
    html = read(index_path)
    book = NameBook(html, cfg.get("author_names"))

    rec = resolve(url, cfg)
    apply_overrides(rec, overrides)
    fill_names(rec, book)

    if rec.missing() and use_llm and enrich_mod.available():
        rec = enrich_mod.enrich(rec, book)
        apply_overrides(rec, overrides)   # human input always wins
        fill_names(rec, book)
    elif rec.missing() and use_llm and not enrich_mod.available():
        rec.note("LLM enrichment skipped (ANTHROPIC_API_KEY not set)")

    dup = None if ignore_duplicate else find_duplicate(html, rec)
    if dup:
        raise DuplicateError(dup)

    missing = rec.missing()
    li = render_li(rec, cfg) if not missing or set(missing) <= {"title_en", "venue_en", "authors_en"} else None
    result = {
        "status": "ok",
        "record": rec.to_dict(),
        "li": li,
        "preview": plain_text(li) if li else None,
        "missing": missing,
        "category_label": cfg["categories"].get(rec.category or "", {}).get("label_ja"),
    }
    if missing:
        result["status"] = "incomplete"
        return result

    heading = cfg["categories"][rec.category]["heading_en"]
    new_html = insert_li(html, li, heading, rec.year)
    sitemap = read(sitemap_path) if sitemap_path.exists() else None
    new_html, sitemap = touch_dates(new_html, sitemap)
    if not dry_run:
        write(index_path, new_html, eol_of(index_path))
        if sitemap is not None:
            write(sitemap_path, sitemap, eol_of(sitemap_path))
        if commit or push:
            msg = f'Publications: add "{short_title(rec.title_en or rec.title_ja or "")}"'
            files = ["index.html"] + (["sitemap.xml"] if sitemap is not None else [])
            git("add", *files)
            git("commit", "-q", "-m", msg)
            result["commit"] = msg
            result["commit_sha"] = git("rev-parse", "--short", "HEAD")
            if push:
                result["pushed_sha"] = push_main()
                result["pushed"] = True
    return result


class GitError(Exception):
    pass


def git(*args: str, check: bool = True) -> str:
    """Run git in the repo without a console window; return stdout, raise GitError with stderr."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", creationflags=flags, stdin=subprocess.DEVNULL)
    if check and p.returncode != 0:
        detail = (p.stderr or p.stdout or "").strip()
        raise GitError(f"git {args[0]} failed (exit {p.returncode}):\n{detail}")
    return p.stdout.strip()


def push_main() -> str:
    """Push HEAD to origin/main and prove it landed. Returns the pushed short SHA."""
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    git("fetch", "-q", "origin", branch)
    local = git("rev-parse", "HEAD")
    remote = git("rev-parse", f"origin/{branch}")
    base = git("merge-base", "HEAD", f"origin/{branch}")
    if remote != base:
        # origin moved since we started: replay our commit on top of it
        p = subprocess.run(["git", "rebase", "-q", f"origin/{branch}"], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if p.returncode != 0:
            git("rebase", "--abort", check=False)
            raise GitError("GitHub 側の index.html と衝突しました。手元で git pull してから、もう一度試してください。\n" + (p.stderr or "").strip())
        local = git("rev-parse", "HEAD")
    git("push", "-q", "origin", f"HEAD:{branch}")
    git("fetch", "-q", "origin", branch)
    if git("rev-parse", f"origin/{branch}") != local:
        raise GitError("push は完了しましたが、GitHub 上の main が更新されていません。git status を確認してください。")
    return local[:7]


def short_title(title: str, limit: int = 72) -> str:
    """Commit-subject friendly title: cut at a word boundary, mark the cut with an ellipsis."""
    title = " ".join(title.split())
    if len(title) <= limit:
        return title
    cut = title[:limit].rsplit(" ", 1)[0] if " " in title[:limit] else title[:limit]
    return cut.rstrip(" ,:;-–") + "…"


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    class Parser(argparse.ArgumentParser):
        def error(self, message):  # usage errors exit 1, keeping 2/3 for duplicate/incomplete
            self.print_usage(sys.stderr)
            sys.stderr.write(f"{self.prog}: error: {message}\n")
            sys.exit(1)

    p = Parser(prog="addpub", description="Add a publication to index.html from a URL.")
    p.add_argument("url", nargs="?", help="DOI / publisher page / IPSJ DL / PDF URL")
    p.add_argument("--category", choices=["journal", "international", "domestic"])
    p.add_argument("--title-ja"); p.add_argument("--title-en")
    p.add_argument("--authors-ja", help="comma separated, 姓 名"); p.add_argument("--authors-en", help="comma separated, Given Family")
    p.add_argument("--venue-ja"); p.add_argument("--venue-en")
    p.add_argument("--year", type=int); p.add_argument("--presentation")
    p.add_argument("--volume"); p.add_argument("--issue"); p.add_argument("--pages")
    p.add_argument("--dry-run", action="store_true", help="show the entry, do not write")
    p.add_argument("--no-llm", action="store_true", help="never call the Claude API")
    p.add_argument("--commit", action="store_true", help="git commit after writing")
    p.add_argument("--push", action="store_true", help="git commit and push after writing")
    p.add_argument("--json", action="store_true", help="machine readable output")
    p.add_argument("--ignore-duplicate", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--from-env", action="store_true", help="read ISSUE_BODY / INPUT_URL / INPUT_CATEGORY env vars (CI)")
    p.add_argument("--comment-file", help="also write a Markdown summary (for the issue comment) to this path")
    a = p.parse_args(argv)

    overrides: dict = {}
    url = a.url
    if a.from_env:
        body = os.environ.get("ISSUE_BODY", "")
        if body.strip():
            overrides = parse_issue_body(body)
            url = overrides.pop("url", None) or url
        url = os.environ.get("INPUT_URL") or url
        cat = os.environ.get("INPUT_CATEGORY")
        if cat and cat != "auto":
            overrides["category"] = cat
    def split(v):
        return [x.strip() for x in re.split(r"[,、，;]+", v) if x.strip()] if v else None
    cli_ov = {
        "category": a.category, "title_ja": a.title_ja, "title_en": a.title_en,
        "authors_ja": split(a.authors_ja), "authors_en": split(a.authors_en),
        "venue_ja": a.venue_ja, "venue_en": a.venue_en, "year": a.year, "presentation": a.presentation,
        "volume": a.volume, "issue": a.issue, "pages": a.pages,
    }
    overrides.update({k: v for k, v in cli_ov.items() if v not in (None, "", [])})

    if not url:
        p.error("a URL is required (argument, ISSUE_BODY or INPUT_URL)")

    try:
        result = run(url, overrides, dry_run=a.dry_run, use_llm=not a.no_llm, push=a.push, commit=a.commit, ignore_duplicate=a.ignore_duplicate)
        code = 0 if result["status"] == "ok" else 3
    except DuplicateError as e:
        result = {"status": "duplicate", "message": f"Already listed: {e}"}
        code = 2
    except (FetchError, SiteError, GitError) as e:
        result = {"status": "error", "message": str(e)}
        code = 1

    if a.comment_file:
        Path(a.comment_file).write_text(markdown(result, os.environ.get("SITE_URL", "")), encoding="utf-8")
    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(human(result, a.dry_run))
    return code


def human(r: dict, dry_run: bool) -> str:
    if r["status"] == "ok":
        head = "DRY RUN — would add" if dry_run else "Added"
        lines = [f"{head} to [{r.get('category_label')}]:", "", r["preview"], "", r["li"]]
        if r["record"].get("notes"):
            lines += ["", "Notes:"] + [f"  - {n}" for n in r["record"]["notes"]]
        if r.get("commit"):
            lines.append(f"\nCommitted: {r['commit']}" + (" (pushed)" if r.get("pushed") else ""))
        return "\n".join(lines)
    if r["status"] == "incomplete":
        need = ", ".join(FIELD_LABELS_JA.get(m, m) for m in r["missing"])
        lines = [f"Metadata incomplete — missing: {need}", "", "Fetched so far:", json.dumps(r["record"], ensure_ascii=False, indent=1)]
        if r.get("li"):
            lines += ["", "Best effort entry:", r["li"]]
        return "\n".join(lines)
    return f"{r['status'].upper()}: {r.get('message')}"


def markdown(r: dict, site_url: str) -> str:
    """Japanese Markdown summary posted back to the issue."""
    if r["status"] == "ok":
        rec = r["record"]
        lines = [
            f"✅ **[{r.get('category_label')}] に追加しました。**",
            "",
            f"> {r['preview']}",
            "",
            f"数分後に {site_url or 'サイト'} に反映されます。" if site_url else "数分後にサイトに反映されます。",
            "",
            "<details><summary>HTML</summary>",
            "",
            "```html",
            r["li"],
            "```",
            "",
            "</details>",
        ]
        if rec.get("notes"):
            lines += ["", "**確認事項**"] + [f"- {n}" for n in rec["notes"]]
        lines += ["", "_取得元: " + ", ".join(rec.get("sources") or []) + "_"]
        return "\n".join(lines)
    if r["status"] == "incomplete":
        need = "、".join(FIELD_LABELS_JA.get(m, m) for m in r["missing"])
        rec = r["record"]
        lines = [
            f"⚠️ **自動取得だけでは情報が足りません。** 不足: {need}",
            "",
            "この Issue を **編集** して該当欄を埋めると、自動で再実行されます。",
            "",
            "取得できた内容:",
            "",
            f"- タイトル: {rec.get('title_ja') or ''} / {rec.get('title_en') or ''}",
            f"- 著者: {', '.join(rec.get('authors_ja') or [])} / {', '.join(rec.get('authors_en') or [])}",
            f"- 発表媒体: {rec.get('venue_ja') or ''} / {rec.get('venue_en') or ''}",
            f"- 年: {rec.get('year') or ''}　カテゴリ: {r.get('category_label') or '未判定'}",
        ]
        if rec.get("notes"):
            lines += ["", "**メモ**"] + [f"- {n}" for n in rec["notes"]]
        return "\n".join(lines)
    if r["status"] == "duplicate":
        return f"ℹ️ **この業績はすでに掲載されています。** ({r.get('message')})\n\n内容を直したい場合は index.html を直接編集してください。"
    return f"❌ **追加できませんでした。** {r.get('message')}\n\nURL を確認するか、Issue を編集して各項目を手入力してください。"


if __name__ == "__main__":
    sys.exit(main())
