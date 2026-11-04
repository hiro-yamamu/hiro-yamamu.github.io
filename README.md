# hiro-yamamu.github.io

Hiroo Yamamura の個人ホームページ。静的 HTML / CSS / JS のみで、ビルド不要。
公開URL: https://hiro-yamamu.github.io/

## 構成

```
index.html      ページ本体（Home / About / Projects / Publications / Contact）
css/style.css   デザイン。色は :root の変数で一括変更可
js/main.js      言語切替、YouTube のクリック再生、フッターの年号
img/            画像（profile.jpg, necomimi_poster.jpg, 各プロジェクト画像, favicon.svg）
.nojekyll       GitHub Pages の Jekyll 処理を無効化
```

## 編集のしかた

- 日本語と英語は同じ場所に並べて書きます。日本語は `<span class="ja">…</span>`（段落なら `<p class="ja">`）、英語は `class="en"`。
  どちらか一方しかない文（英語の論文タイトルなど）はクラス無しで書けば両言語で表示されます。
- 業績を追加するときは、該当カテゴリの `<li>` をコピーして先頭（新しい順）に挿入します。
- 学歴・職歴、受賞、助成は `<li><span class="row-year">年</span><span>内容</span></li>` の1行形式です。
- フッターの `Last updated` は手で書き換えます。

## YouTube 動画を追加する

```html
<div class="video" data-yt="動画ID" data-title="タイトル" data-poster="img/xxx.jpg"></div>
```

- 動画IDは `https://www.youtube.com/watch?v=XXXXXXXXXXX` の `XXXXXXXXXXX`。
- `data-poster` は省略可。省略すると YouTube のサムネイルを使います。
- クリックすると YouTube (youtube-nocookie.com) の埋め込みプレーヤーに切り替わります。

## 業績を自動で追加する（addpub）

論文の URL を渡すだけで Publications に追記し、公開まで行う仕組みが `tools/addpub/` と
`.github/workflows/add-publication.yml` に入っています。

### いちばん簡単な使い方（Windows）

```
git clone https://github.com/hiro-yamamu/hiro-yamamu.github.io.git
cd hiro-yamamu.github.io
setup.bat      ← 初回だけ。Git / Python がなければ入れ、.venv を作ってパッケージを入れる
start.bat      ← アプリ起動。URL を貼る → 「内容を確認」→ 「追加して公開」
```

`start.bat` は起動前に `git pull` して最新にし、公開時は commit & push まで行います。
初回の push では Git がブラウザを開いて GitHub へのサインインを求めることがあります。

### 使い方 1: GitHub の Issue から（スマホでも可）※まだ有効になっていません

この経路を動かすワークフローファイル `.github/workflows/add-publication.yml` は、GitHub の仕様で
`workflow` 権限のあるトークンからしか置けず、この PC の認証ではアップロードできませんでした。
ファイル自体はローカルのブランチ `workflow-pending` にあります。有効にするには、GitHub のサイトで
**Add file → Upload files** から同ファイルを `.github/workflows/` に置くか、`gh auth refresh -s workflow`
のあとで `git push origin workflow-pending:main` してください。それまで Issue を開いても何も起きません。

1. リポジトリの **Issues → New issue → 「業績を追加 / Add publication」** を開く
2. **URL** に論文のリンクを貼って Submit（他の欄は空でよい）
3. 1〜2 分で GitHub Actions が index.html に追記して push し、結果を Issue にコメントして閉じます
4. 情報が足りない場合（日本語論文の英語タイトルなど）はコメントで知らせるので、**Issue を編集**して欄を埋めると再実行されます

Actions タブの「Add publication」→ **Run workflow** に URL を入れても同じことができます。

### 使い方 2: デスクトップアプリ

`start.bat`（中身は `tools\addpub_gui.pyw`）。URL を貼る → 「1. 内容を確認」→ 「2. 追加して公開」。
普段の git 認証でそのまま commit & push します。

### 使い方 3: コマンドライン

```
pip install -r tools/requirements.txt
python -m tools.addpub <URL> --dry-run      # 追加される行を確認するだけ
python -m tools.addpub <URL> --push         # 追記して commit & push
python -m tools.addpub <URL> --category domestic --title-en "..." --authors-en "A, B"   # 手で補う
```

### 対応している URL と取れる情報

| URL | 取れる情報 |
| --- | --- |
| DOI（doi.org, dl.acm.org, frontiersin.org, diglib.eg.org など） | 著者・題名・媒体・巻号・ページ・年。英語論文はこれだけで完成 |
| J-STAGE の DOI（日本語論文） | 日本語の書誌。英語題名は Claude か手入力で補う |
| 情報学広場 `ipsj.ixsq.nii.ac.jp/records/…` | 日英の題名・著者・媒体 |
| 予稿 PDF（VRSJ 大会など） | 本文テキストのみ。Claude か手入力が必要。VRSJ は URL から大会名・年を推定 |

- カテゴリ（学術論文 / 国際会議 / 国内会議）は種別と言語から自動判定。年順（新しい順）の位置に挿入し、`Last updated` と `sitemap.xml` の日付も更新します。
- 同じ DOI / URL / 題名がすでにあれば追加しません。
- 共著者名の日英対応は index.html 内の既存エントリから学習します。未知の名前は `tools/addpub/config.json` の `author_names` に追記できます。学会名の対応表も同ファイルの `venues` にあります。
- **任意: Claude API による補完。** リポジトリの Secrets に `ANTHROPIC_API_KEY` を登録すると、足りない英語題名・著者の読み・PDF しかない論文の書誌を自動で埋めます（モデル: `claude-opus-5-5`、1 件あたり数円程度）。未登録でも動きますが、その場合は不足分を Issue の欄に手入力します。

## 更新して公開する

```
git add .
git commit -m "Update content"
git push
```

push 後、1〜2分で反映されます。
