"""Tiny desktop front end for addpub: paste a URL, click, done.

Double-click this file (Windows runs .pyw without a console). It fetches the
metadata, shows the entry that will be added, and on confirmation writes
index.html, commits, and pushes with your normal git credentials.
"""
from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.addpub.cli import GitError, run  # noqa: E402
from tools.addpub.fetch import FetchError  # noqa: E402
from tools.addpub.site import DuplicateError, SiteError  # noqa: E402

SITE_URL = "https://hiro-yamamu.github.io/"
CATEGORIES = [("自動判定", None), ("学術論文", "journal"), ("国際会議", "international"), ("国内会議", "domestic")]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("業績を追加 — hiro-yamamu.github.io")
        self.geometry("760x520")
        self.minsize(600, 420)
        pad = {"padx": 10, "pady": 4}

        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="論文の URL（DOI / 論文ページ / PDF）").grid(row=0, column=0, sticky="w", **pad)
        self.url = tk.StringVar()
        ent = ttk.Entry(frm, textvariable=self.url)
        ent.grid(row=1, column=0, columnspan=3, sticky="ew", **pad)
        ent.focus()
        ent.bind("<Return>", lambda e: self.preview())

        ttk.Label(frm, text="カテゴリ").grid(row=2, column=0, sticky="w", **pad)
        self.cat = ttk.Combobox(frm, values=[c[0] for c in CATEGORIES], state="readonly", width=12)
        self.cat.current(0)
        self.cat.grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(frm, text="英語タイトル（日本語論文で自動取得できなかったときだけ）").grid(row=3, column=0, columnspan=3, sticky="w", **pad)
        self.title_en = tk.StringVar()
        ttk.Entry(frm, textvariable=self.title_en).grid(row=4, column=0, columnspan=3, sticky="ew", **pad)

        btns = ttk.Frame(frm)
        btns.grid(row=5, column=0, columnspan=3, sticky="w", **pad)
        self.b_prev = ttk.Button(btns, text="1. 内容を確認", command=self.preview)
        self.b_prev.pack(side="left")
        self.b_pub = ttk.Button(btns, text="2. 追加して公開 (commit & push)", command=self.publish, state="disabled")
        self.b_pub.pack(side="left", padx=8)
        self.status = ttk.Label(btns, text="")
        self.status.pack(side="left", padx=8)

        self.out = tk.Text(frm, wrap="word", height=14, font=("Yu Gothic UI", 10))
        self.out.grid(row=6, column=0, columnspan=3, sticky="nsew", **pad)
        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(6, weight=1)
        self._last_ok = False
        self._busy = False
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        if self._busy and not messagebox.askyesno("処理中", "まだ処理中です。閉じると push が途中で止まる可能性があります。閉じますか？"):
            return
        self.destroy()

    # ---------------------------------------------------------------- helpers
    def overrides(self) -> dict:
        ov = {}
        c = CATEGORIES[self.cat.current()][1]
        if c:
            ov["category"] = c
        if self.title_en.get().strip():
            ov["title_en"] = self.title_en.get().strip()
        return ov

    def busy(self, on: bool, msg: str = ""):
        self._busy = on
        state = "disabled" if on else "normal"
        self.b_prev.configure(state=state)
        self.b_pub.configure(state="disabled" if on or not self._last_ok else "normal")
        self.status.configure(text=msg)
        self.configure(cursor="watch" if on else "")
        self.update_idletasks()

    def show(self, text: str):
        self.out.delete("1.0", "end")
        self.out.insert("1.0", text)

    def _work(self, *, dry_run: bool):
        url = self.url.get().strip()
        if not url:
            messagebox.showwarning("URL", "URL を入力してください。")
            return
        self._last_ok = False
        self.busy(True, "取得中…" if dry_run else "公開中…")

        def job():
            try:
                r = run(url, self.overrides(), dry_run=dry_run, use_llm=True, push=not dry_run, commit=not dry_run)
                self.after(0, lambda: self._done(r, dry_run))
            except DuplicateError as e:
                msg = f"すでに掲載されています: {e}"
                self.after(0, lambda m=msg: self._fail(m))
            except GitError as e:
                msg = ("git の操作に失敗しました。サイトは更新されていません。\n\n" + str(e)
                       + "\n\n手元の index.html には追記済みのことがあります。git status で状態を確認してください。")
                self.after(0, lambda m=msg: self._fail(m))
            except (FetchError, SiteError) as e:
                msg = str(e)
                self.after(0, lambda m=msg: self._fail(m))
            except Exception as e:  # noqa: BLE001 - surface anything else in the window
                msg = f"{type(e).__name__}: {e}"
                self.after(0, lambda m=msg: self._fail(m))

        threading.Thread(target=job, daemon=True).start()

    def _done(self, r: dict, dry_run: bool):
        if r["status"] == "ok":
            self._last_ok = dry_run
            if dry_run:
                head = "追加される内容（まだ書き込んでいません）"
            elif r.get("pushed"):
                head = (f"GitHub に push しました（commit {r.get('pushed_sha')}）。\n"
                        f"1〜2 分後に {SITE_URL} に反映されます。")
            else:
                head = f"commit しましたが push はしていません（commit {r.get('commit_sha')}）。"
            notes = "\n".join(f"・{n}" for n in r["record"].get("notes", []))
            self.show(f"{head}\n\n[{r['category_label']}]\n\n{r['preview']}\n\n{notes}\n\nHTML:\n{r['li']}")
            self.busy(False, "確認してから「追加して公開」を押してください" if dry_run else "完了")
        else:
            need = "、".join(r["missing"])
            rec = r["record"]
            self.show(
                f"自動取得だけでは足りません。不足: {need}\n\n"
                f"タイトル: {rec.get('title_ja') or ''} / {rec.get('title_en') or ''}\n"
                f"著者: {', '.join(rec.get('authors_ja') or [])} / {', '.join(rec.get('authors_en') or [])}\n"
                f"媒体: {rec.get('venue_ja') or ''} / {rec.get('venue_en') or ''}\n年: {rec.get('year') or ''}\n\n"
                "英語タイトルだけなら上の欄に入力して再度「内容を確認」。それ以外はコマンドラインで\n"
                "python -m tools.addpub <URL> --authors-en \"...\" --venue-en \"...\" などを指定してください。"
            )
            self.busy(False, "情報不足")

    def _fail(self, msg: str):
        self.show(msg)
        self.busy(False, "エラー")

    def preview(self):
        self._work(dry_run=True)

    def publish(self):
        if messagebox.askyesno("公開", "index.html に追記して commit & push します。よろしいですか？"):
            self._work(dry_run=False)


if __name__ == "__main__":
    os.chdir(ROOT)
    App().mainloop()
