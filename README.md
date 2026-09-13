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

## 更新して公開する

```
git add .
git commit -m "Update content"
git push
```

push 後、1〜2分で反映されます。
