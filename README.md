# Personal Homepage (GitHub Pages)

日英切り替え対応の個人ホームページです。静的HTML/CSS/JSのみで構成され、ビルド不要です。

## ファイル構成

```
index.html      ページ本体（全セクションの文章はここを編集）
css/style.css   デザイン（色は :root の変数で一括変更可）
js/main.js      言語切り替え・フッターの年号
img/            画像置き場（favicon.svg、顔写真を置く場合は profile.jpg）
.nojekyll       GitHub PagesのJekyll処理を無効化（そのまま配信）
```

## 編集のしかた

- 日本語の文は `<span class="ja">…</span>` または `<p class="ja">…</p>`、英語は `class="en"` に書きます。
- 論文を追加するときは `#publications` セクションの `<li>` をコピーして増やします。
- 顔写真を使う場合は `img/profile.jpg` を置き、`index.html` の `avatar-placeholder` の div を
  `<img class="avatar" src="img/profile.jpg" alt="">` に置き換えます。
- 色を変えたいときは `css/style.css` の `:root` にある `--mint` `--sky` `--lavender` を変更します。

## 更新して公開する

```
git add .
git commit -m "Update content"
git push
```

push後、1〜2分でサイトに反映されます。
