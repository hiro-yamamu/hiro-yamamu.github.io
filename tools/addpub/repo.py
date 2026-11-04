"""Repository health: detect the states that made publishing fail before, and repair them.

Used by the GUI (status bar + 修復 button) and by `python -m tools.addpub --doctor / --repair`.

Detected problems
  in_progress   a rebase / merge / cherry-pick was left half-done
  wrong_branch  HEAD is not on main
  offline       GitHub cannot be reached (network or credentials)
  dirty         index.html / sitemap.xml edited but not committed
  ahead         local commits that never reached GitHub (optionally containing a workflow
                file that this PC's token is not allowed to push)
  behind        GitHub has newer commits than this PC
  identity      git user.name / user.email missing
"""
from __future__ import annotations

import datetime as dt
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRANCH = "main"
SITE_FILES = ("index.html", "sitemap.xml")
WORKFLOW_DIR = ".github/workflows/"


class GitError(Exception):
    pass


class ConflictError(GitError):
    """Our commit cannot be replayed on top of GitHub's main."""


def git(*args: str, check: bool = True, cwd: Path | None = None, raw: bool = False) -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.run(["git", *args], cwd=cwd or ROOT, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", creationflags=flags, stdin=subprocess.DEVNULL)
    if check and p.returncode != 0:
        detail = (p.stderr or p.stdout or "").strip()
        raise GitError(f"git {args[0]} failed (exit {p.returncode}):\n{detail}")
    return p.stdout if raw else p.stdout.strip()


@dataclass
class Issue:
    code: str
    severity: str            # "error" | "warn" | "info"
    message: str             # Japanese, shown to the user
    fix: str | None = None   # what 修復 will do, or None if the user must act
    data: dict = field(default_factory=dict)


@dataclass
class Health:
    issues: list[Issue] = field(default_factory=list)
    ahead: list[str] = field(default_factory=list)    # short SHAs
    behind: int = 0
    online: bool = True

    @property
    def ok(self) -> bool:
        return not any(i.severity in ("error", "warn") for i in self.issues)

    @property
    def fixable(self) -> bool:
        return any(i.fix for i in self.issues)

    def summary(self) -> str:
        if self.ok:
            return "GitHub と同期済み。公開できます。"
        worst = [i for i in self.issues if i.severity == "error"] or [i for i in self.issues if i.severity == "warn"]
        return worst[0].message


# ------------------------------------------------------------------ detection
def _in_progress() -> str | None:
    g = ROOT / ".git"
    for name, label in (("rebase-merge", "rebase"), ("rebase-apply", "rebase"), ("MERGE_HEAD", "merge"),
                        ("CHERRY_PICK_HEAD", "cherry-pick"), ("REVERT_HEAD", "revert")):
        if (g / name).exists():
            return label
    return None


def _touches_workflow(sha: str) -> bool:
    files = git("show", "--pretty=", "--name-only", sha)
    return any(f.startswith(WORKFLOW_DIR) for f in files.splitlines())


def diagnose(fetch: bool = True) -> Health:
    h = Health()
    if not (ROOT / ".git").exists():
        h.issues.append(Issue("no_repo", "error", "git リポジトリではありません。git clone し直してください。"))
        return h

    op = _in_progress()
    if op:
        h.issues.append(Issue("in_progress", "error", f"途中で止まった {op} があります。", fix=f"{op} を中断して元の状態に戻す"))
        return h   # everything else is unreliable until this is cleared

    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch != BRANCH:
        h.issues.append(Issue("wrong_branch", "error", f"ブランチが {branch} になっています（{BRANCH} であるべき）。",
                              fix=f"{BRANCH} に切り替える", data={"branch": branch}))

    if not git("config", "user.name", check=False) or not git("config", "user.email", check=False):
        h.issues.append(Issue("identity", "error", "git の名前またはメールが未設定です。setup.bat を実行してください。"))

    if fetch:
        try:
            git("fetch", "-q", "origin", BRANCH)
        except GitError as e:
            h.online = False
            h.issues.append(Issue("offline", "error", "GitHub に接続できません（ネットワークまたは認証）。", data={"detail": str(e)}))

    porcelain = git("status", "--porcelain", "-z", "--", *SITE_FILES, raw=True)   # NUL separated: "XY path"
    dirty = [entry[3:] for entry in porcelain.split("\0") if len(entry) > 3]
    if dirty:
        h.issues.append(Issue("dirty", "warn", f"コミットされていない変更があります: {', '.join(dirty)}",
                              fix="内容を確認して、公開するか取り消すかを選ぶ", data={"files": dirty}))

    if branch == BRANCH and git("rev-parse", "--verify", "-q", f"origin/{BRANCH}", check=False):
        ahead = git("rev-list", f"origin/{BRANCH}..HEAD").split()
        behind = git("rev-list", f"HEAD..origin/{BRANCH}").split()
        h.ahead = [s[:7] for s in ahead]
        h.behind = len(behind)
        if ahead:
            wf = [s[:7] for s in ahead if _touches_workflow(s)]
            subjects = [git("log", "-1", "--pretty=%s", s) for s in ahead[:5]]
            if wf:
                msg = (f"GitHub に届いていないコミットが {len(ahead)} 件あり、うち {len(wf)} 件はワークフローファイルを含むため"
                       "この PC からは push できません。")
                fix = "ワークフローのコミットを別ブランチ workflow-pending に退避し、残りを push する"
            else:
                msg = f"GitHub に届いていないコミットが {len(ahead)} 件あります（{subjects[0]}）。"
                fix = "GitHub に push する"
            h.issues.append(Issue("ahead", "warn", msg, fix=fix, data={"shas": ahead, "workflow": wf, "subjects": subjects}))
        if behind and not ahead:
            h.issues.append(Issue("behind", "warn", f"GitHub の方が {len(behind)} 件新しいです。", fix="最新を取り込む (git pull)"))
        elif behind and ahead:
            h.issues[-1].fix = (h.issues[-1].fix or "") + "（GitHub 側の更新の上に載せ替えてから）"
    return h


# --------------------------------------------------------------------- repair
def push_main() -> str:
    """Push HEAD to origin/main and prove it landed. Returns the pushed short SHA."""
    git("fetch", "-q", "origin", BRANCH)
    local = git("rev-parse", "HEAD")
    remote = git("rev-parse", f"origin/{BRANCH}")
    base = git("merge-base", "HEAD", f"origin/{BRANCH}")
    if remote != base:
        p = subprocess.run(["git", "rebase", "-q", f"origin/{BRANCH}"], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if p.returncode != 0:
            git("rebase", "--abort", check=False)
            raise ConflictError(
                "GitHub 側の index.html と衝突したため push を中止しました（手元は元の状態のままです）。\n"
                "「修復」を押すと、手元のコミットを退避ブランチに保存して GitHub と同期し直します。"
                "そのあと、もう一度 URL から追加してください。")
        local = git("rev-parse", "HEAD")
    git("push", "-q", "origin", f"HEAD:{BRANCH}")
    git("fetch", "-q", "origin", BRANCH)
    if git("rev-parse", f"origin/{BRANCH}") != local:
        raise GitError("push は完了しましたが、GitHub 上の main が更新されていません。git status を確認してください。")
    return local[:7]


def _park_workflow_commits(shas_oldest_first: list[str], wf: set[str]) -> str:
    """Move commits that touch workflow files out of main onto a parked branch; keep the rest."""
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    park = f"workflow-pending-{stamp}"
    git("branch", "-f", park, "HEAD")
    git("reset", "-q", "--hard", f"origin/{BRANCH}")
    for s in shas_oldest_first:
        if s[:7] in wf:
            continue
        try:
            git("cherry-pick", "-x", s)
        except GitError as e:
            git("cherry-pick", "--abort", check=False)
            git("reset", "-q", "--hard", park)      # undo everything, main back to where it was
            git("branch", "-D", park, check=False)
            raise GitError("コミットの載せ替えに失敗したため、元の状態に戻しました。\n" + str(e))
    return park


def _park_all_local_commits() -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    park = f"local-pending-{stamp}"
    git("branch", "-f", park, "HEAD")
    git("reset", "-q", "--hard", f"origin/{BRANCH}")
    return park


def repair(h: Health, *, local_changes: str = "ask", decide=None) -> list[str]:
    """Apply fixes. local_changes: 'publish' | 'discard' | 'ask' (calls decide(files) -> 'publish'|'discard'|None)."""
    log: list[str] = []
    codes = {i.code: i for i in h.issues}

    if "in_progress" in codes:
        for cmd in (("rebase", "--abort"), ("merge", "--abort"), ("cherry-pick", "--abort"), ("revert", "--abort")):
            git(*cmd, check=False)
        log.append("途中で止まっていた操作を中断し、元の状態に戻しました。")
        h = diagnose(fetch=h.online)
        codes = {i.code: i for i in h.issues}

    if "wrong_branch" in codes:
        git("checkout", "-q", BRANCH)
        log.append(f"{BRANCH} に切り替えました。")

    if "dirty" in codes:
        files = codes["dirty"].data["files"]
        choice = local_changes if local_changes != "ask" else (decide(files) if decide else None)
        if choice == "discard":
            git("checkout", "--", *files)
            log.append(f"未コミットの変更を取り消しました: {', '.join(files)}")
        elif choice == "publish":
            git("add", "--", *files)
            git("commit", "-q", "-m", "Publications: publish pending local edits")
            log.append("未コミットの変更をコミットしました。")
        else:
            log.append("未コミットの変更はそのままにしました。")

    if not h.online:
        log.append("GitHub に接続できないため、push / pull は行っていません。")
        return log

    h2 = diagnose(fetch=False)
    ahead = next((i for i in h2.issues if i.code == "ahead"), None)
    if ahead:
        shas = list(reversed(ahead.data["shas"]))   # rev-list gives newest first
        wf = set(ahead.data["workflow"])
        if wf:
            park = _park_workflow_commits(shas, wf)
            log.append(f"ワークフローファイルを含むコミットをブランチ {park} に退避しました（main からは外しました）。")
        if git("rev-list", f"origin/{BRANCH}..HEAD").split():
            try:
                sha = push_main()
                log.append(f"GitHub に push しました（commit {sha}）。")
            except ConflictError:
                park = _park_all_local_commits()
                log.append(f"GitHub 側と衝突するため、手元のコミットをブランチ {park} に退避し、GitHub の内容に合わせました。"
                           "退避した業績は、もう一度 URL から追加してください。")
        else:
            log.append("push すべきコミットは残っていません。")
    elif h2.behind:
        git("pull", "-q", "--ff-only", "origin", BRANCH)
        log.append("GitHub の最新を取り込みました。")

    final = diagnose(fetch=False)
    log.append("✔ " + final.summary() if final.ok else "⚠ まだ問題があります: " + final.summary())
    return log


def format_health(h: Health) -> str:
    lines = [("✔ " if h.ok else "⚠ ") + h.summary()]
    for i in h.issues:
        mark = {"error": "✖", "warn": "⚠", "info": "・"}[i.severity]
        lines.append(f"{mark} {i.message}")
        if i.fix:
            lines.append(f"    → 修復: {i.fix}")
    return "\n".join(lines)
