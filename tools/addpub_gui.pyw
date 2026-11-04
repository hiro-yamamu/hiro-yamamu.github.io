"""Desktop front end for addpub: paste a URL, preview, publish.

Started by start.bat. Checks the repository state on launch and offers a one-click repair
for the situations that have broken publishing before (unpushed commits, half-finished
rebase, a commit that this PC's token is not allowed to push, GitHub ahead of this PC).
"""
from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.addpub.cli import UnhealthyRepo, run  # noqa: E402
from tools.addpub.fetch import FetchError  # noqa: E402
from tools.addpub.repo import GitError, diagnose, format_health, repair  # noqa: E402
from tools.addpub.site import DuplicateError, SiteError  # noqa: E402

SITE_URL = "https://hiro-yamamu.github.io/"
CATEGORIES = [("自動判定", None), ("学術論文", "journal"), ("国際会議", "international"), ("国内会議", "domestic")]

COLORS = {
    "ok": ("#e6f4ea", "#1e6b35"),
    "warn": ("#fff4e0", "#8a5a00"),
    "error": ("#fdecea", "#a12622"),
    "info": ("#e8f0fe", "#1b4f9c"),
    "busy": ("#eeeeee", "#444444"),
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("業績を追加 — hiro-yamamu.github.io")
        self.geometry("860x640")
        self.minsize(720, 520)
        self._busy = False
        self._preview_ok = False
        self._health = None

        base = tkfont.nametofont("TkDefaultFont")
        base.configure(family="Yu Gothic UI", size=11)
        self.option_add("*Font", base)
        self.f_small = tkfont.Font(family="Yu Gothic UI", size=9)
        self.f_bold = tkfont.Font(family="Yu Gothic UI", size=11, weight="bold")
        self.f_big = tkfont.Font(family="Yu Gothic UI", size=13, weight="bold")
        self.f_mono = tkfont.Font(family="Consolas", size=9)

        style = ttk.Style(self)
        style.configure("TButton", padding=(14, 6))
        style.configure("Primary.TButton", font=self.f_bold, padding=(16, 8))
        style.configure("TLabelframe.Label", font=self.f_bold)

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self.check_health)

    # ------------------------------------------------------------------ layout
    def _build(self):
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        # -- status bar: repository health
        bar = tk.Frame(outer, bd=0, highlightthickness=1, highlightbackground="#cccccc")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        bar.columnconfigure(0, weight=1)
        self.health_lbl = tk.Label(bar, text="状態を確認しています…", anchor="w", padx=12, pady=8, font=self.f_bold)
        self.health_lbl.grid(row=0, column=0, sticky="ew")
        self.b_check = ttk.Button(bar, text="再確認", command=self.check_health, width=8)
        self.b_check.grid(row=0, column=1, padx=(6, 4), pady=6)
        self.b_repair = ttk.Button(bar, text="修復", command=self.do_repair, width=8, state="disabled")
        self.b_repair.grid(row=0, column=2, padx=(0, 8), pady=6)
        self.bar = bar

        # -- input
        inp = ttk.LabelFrame(outer, text=" 1. 論文の URL を貼る ", padding=(12, 8, 12, 12))
        inp.grid(row=1, column=0, sticky="ew")
        inp.columnconfigure(1, weight=1)
        self.url = tk.StringVar()
        ent = ttk.Entry(inp, textvariable=self.url, font=("Yu Gothic UI", 12))
        ent.grid(row=0, column=0, columnspan=4, sticky="ew", ipady=4)
        ent.focus()
        ent.bind("<Return>", lambda e: self.preview())
        ttk.Label(inp, text="DOI / 論文ページ / PDF のどれでも可", font=self.f_small, foreground="#666").grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(2, 8))

        ttk.Label(inp, text="カテゴリ").grid(row=2, column=0, sticky="w", padx=(0, 8))
        self.cat = ttk.Combobox(inp, values=[c[0] for c in CATEGORIES], state="readonly", width=12)
        self.cat.current(0)
        self.cat.grid(row=2, column=1, sticky="w")
        ttk.Label(inp, text="英語タイトル（日本語論文で取れなかった時だけ）").grid(row=2, column=2, sticky="e", padx=(16, 8))
        self.title_en = tk.StringVar()
        ttk.Entry(inp, textvariable=self.title_en, width=34).grid(row=2, column=3, sticky="ew")
        inp.columnconfigure(3, weight=2)

        # -- actions
        act = ttk.Frame(outer)
        act.grid(row=2, column=0, sticky="ew", pady=12)
        self.b_prev = ttk.Button(act, text="2. 内容を確認", command=self.preview, style="Primary.TButton")
        self.b_prev.pack(side="left")
        self.b_pub = ttk.Button(act, text="3. 追加して公開", command=self.publish, style="Primary.TButton", state="disabled")
        self.b_pub.pack(side="left", padx=10)
        self.b_site = ttk.Button(act, text="サイトを開く", command=lambda: webbrowser.open(SITE_URL))
        self.b_site.pack(side="right")

        # -- result
        res = ttk.LabelFrame(outer, text=" 結果 ", padding=(12, 8, 12, 12))
        res.grid(row=3, column=0, sticky="nsew")
        res.columnconfigure(0, weight=1)
        res.rowconfigure(1, weight=1)
        self.banner = tk.Label(res, text="URL を貼って「内容を確認」を押してください。", anchor="w", justify="left",
                               padx=12, pady=10, font=self.f_big, wraplength=760)
        self.banner.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self._paint(self.banner, "info")

        self.out = tk.Text(res, wrap="word", font=("Yu Gothic UI", 11), relief="flat", padx=10, pady=8,
                           bg="#fafafa", state="disabled", height=10)
        self.out.grid(row=1, column=0, sticky="nsew")
        self.out.tag_configure("h", font=self.f_bold, spacing3=4)
        self.out.tag_configure("mono", font=self.f_mono, foreground="#555")
        self.out.tag_configure("note", foreground="#8a5a00")
        sb = ttk.Scrollbar(res, orient="vertical", command=self.out.yview)
        sb.grid(row=1, column=1, sticky="ns")
        self.out.configure(yscrollcommand=sb.set)

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _paint(widget, kind: str):
        bg, fg = COLORS[kind]
        widget.configure(bg=bg, fg=fg)

    def write(self, parts):
        """parts: list of (text, tag|None)."""
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        for text, tag in parts:
            self.out.insert("end", text, tag or ())
        self.out.configure(state="disabled")

    def text(self) -> str:
        return self.out.get("1.0", "end").strip()

    def busy(self, on: bool, msg: str | None = None):
        self._busy = on
        st = "disabled" if on else "normal"
        for b in (self.b_prev, self.b_check):
            b.configure(state=st)
        self.b_pub.configure(state="disabled" if on or not self._preview_ok else "normal")
        self.b_repair.configure(state="disabled" if on or not (self._health and self._health.fixable) else "normal")
        self.configure(cursor="watch" if on else "")
        if msg is not None:
            self.banner.configure(text=msg)
            self._paint(self.banner, "busy")
        self.update_idletasks()

    def _on_close(self):
        if self._busy and not messagebox.askyesno("処理中", "まだ処理中です。閉じると push が途中で止まる可能性があります。閉じますか？"):
            return
        self.destroy()

    def _bg(self, job, done):
        """Run job() in a thread, then done(result_or_exception) on the UI thread."""
        def wrap():
            try:
                r = job()
            except Exception as e:  # noqa: BLE001 - every failure is shown in the window
                r = e
            self.after(0, lambda: done(r))
        threading.Thread(target=wrap, daemon=True).start()

    def overrides(self) -> dict:
        ov = {}
        c = CATEGORIES[self.cat.current()][1]
        if c:
            ov["category"] = c
        if self.title_en.get().strip():
            ov["title_en"] = self.title_en.get().strip()
        return ov

    # ------------------------------------------------------------------ health
    def check_health(self):
        self.busy(True)
        self.health_lbl.configure(text="GitHub と照合しています…")
        self._paint(self.health_lbl, "busy")
        self.bar.configure(bg=COLORS["busy"][0])
        self._bg(lambda: diagnose(fetch=True), self._health_done)

    def _health_done(self, h):
        if isinstance(h, Exception):
            self._health = None
            self.health_lbl.configure(text=f"状態を確認できませんでした: {h}")
            self._paint(self.health_lbl, "error")
            self.busy(False)
            return
        self._health = h
        kind = "ok" if h.ok else ("error" if any(i.severity == "error" for i in h.issues) else "warn")
        text = ("✔ " if h.ok else "⚠ ") + h.summary()
        if not h.ok and h.fixable:
            text += "　→「修復」を押してください"
        self.health_lbl.configure(text=text)
        self._paint(self.health_lbl, kind)
        self.bar.configure(bg=COLORS[kind][0])
        self.busy(False)
        if not h.ok:
            self.banner.configure(text="先にリポジトリの状態を直してください。")
            self._paint(self.banner, kind)
            self.write([(format_health(h), None)])

    def do_repair(self):
        h = self._health
        if not h:
            return
        dirty = next((i for i in h.issues if i.code == "dirty"), None)
        policy = "ask"
        if dirty:
            ans = messagebox.askyesnocancel(
                "未コミットの変更",
                "index.html に未コミットの変更があります。\n\n"
                "「はい」= その変更を公開する\n「いいえ」= その変更を取り消す\n「キャンセル」= そのままにする")
            policy = "publish" if ans else ("discard" if ans is False else "keep")
        self.busy(True, "修復しています…")

        def job():
            return repair(h, local_changes="ask" if policy == "keep" else policy, decide=lambda f: None)

        def done(r):
            if isinstance(r, Exception):
                self.banner.configure(text="修復に失敗しました。")
                self._paint(self.banner, "error")
                self.write([(str(r), None)])
            else:
                self.banner.configure(text="修復しました。")
                self._paint(self.banner, "ok")
                self.write([("\n".join(r), None)])
            self.busy(False)
            self.check_health()

        self._bg(job, done)

    # ------------------------------------------------------------- main actions
    def preview(self):
        self._start(dry_run=True)

    def publish(self):
        if messagebox.askyesno("公開", "index.html に追記して GitHub に push します。よろしいですか？"):
            self._start(dry_run=False)

    def _start(self, *, dry_run: bool):
        url = self.url.get().strip()
        if not url:
            messagebox.showwarning("URL", "URL を入力してください。")
            return
        self._preview_ok = False
        self.busy(True, "書誌情報を取得しています…" if dry_run else "追記して GitHub に push しています…")
        self._bg(lambda: run(url, self.overrides(), dry_run=dry_run, use_llm=True, push=not dry_run, commit=not dry_run),
                 lambda r: self._finish(r, dry_run))

    def _finish(self, r, dry_run: bool):
        if isinstance(r, DuplicateError):
            self.banner.configure(text=f"すでに掲載されています（{r}）。何もしていません。")
            self._paint(self.banner, "info")
            self.write([])
        elif isinstance(r, UnhealthyRepo):
            self.banner.configure(text="公開を中止しました。先にリポジトリの状態を直してください（上の「修復」）。")
            self._paint(self.banner, "error")
            self.write([(format_health(r.health), None)])
            self.busy(False)
            self._health_done(r.health)
            return
        elif isinstance(r, GitError):
            self.banner.configure(text="git の操作に失敗しました。サイトは更新されていません。")
            self._paint(self.banner, "error")
            self.write([(str(r), None), ("\n\n「再確認」→「修復」で状態を整えてから、もう一度お試しください。", "note")])
        elif isinstance(r, (FetchError, SiteError)):
            self.banner.configure(text="取得できませんでした。")
            self._paint(self.banner, "error")
            self.write([(str(r), None)])
        elif isinstance(r, Exception):
            self.banner.configure(text=f"予期しないエラー: {type(r).__name__}")
            self._paint(self.banner, "error")
            self.write([(str(r), None)])
        elif r["status"] == "ok":
            rec = r["record"]
            if dry_run:
                self._preview_ok = True
                self.banner.configure(text=f"[{r['category_label']}] に次の1件を追加します。よければ「追加して公開」を押してください。")
                self._paint(self.banner, "info")
            else:
                self.banner.configure(text=f"GitHub に push しました（commit {r.get('pushed_sha')}）。1〜2 分後に {SITE_URL} に反映されます。")
                self._paint(self.banner, "ok")
            parts = [("掲載内容\n", "h"), (r["preview"] + "\n\n", None)]
            if rec.get("notes"):
                parts += [("確認事項\n", "h")] + [("・" + n + "\n", "note") for n in rec["notes"]] + [("\n", None)]
            parts += [("HTML\n", "h"), (r["li"], "mono")]
            self.write(parts)
        else:  # incomplete
            rec = r["record"]
            self.banner.configure(text="自動取得だけでは情報が足りません。")
            self._paint(self.banner, "warn")
            self.write([
                ("不足: " + "、".join(r["missing"]) + "\n\n", "note"),
                ("取得できた内容\n", "h"),
                (f"タイトル: {rec.get('title_ja') or ''} / {rec.get('title_en') or ''}\n"
                 f"著者: {', '.join(rec.get('authors_ja') or [])} / {', '.join(rec.get('authors_en') or [])}\n"
                 f"媒体: {rec.get('venue_ja') or ''} / {rec.get('venue_en') or ''}\n年: {rec.get('year') or ''}\n\n", None),
                ("英語タイトルだけなら上の欄に入れて「内容を確認」をもう一度。それ以外はコマンドラインで\n"
                 "python -m tools.addpub <URL> --authors-en \"...\" --venue-en \"...\" のように指定してください。", None),
            ])
        self.busy(False)
        if not dry_run and not isinstance(r, Exception):
            self.check_health()


if __name__ == "__main__":
    os.chdir(ROOT)
    App().mainloop()
