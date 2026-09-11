# G検定 模試ラボ

G検定（JDLA Deep Learning for GENERAL）対策のオリジナル問題サイト。
9分野190問の4択問題と解説、時間制限つき模擬試験、要点整理、用語集を1枚の静的HTMLで提供します。

- 問題・解説・要点・用語はすべてオリジナル（AI作成）。公式試験問題や市販書籍の転載は含みません。
- 学習記録はブラウザの localStorage にのみ保存されます（サーバ側の保存なし）。

## 構成

```
index.html            デプロイされる完成ページ（ビルド成果物）
src/bank.py           問題バンク（分野, 問題文, 選択肢×4, 正解index, 解説）
src/notes.py          要点整理と用語集
src/template_pub.html ページのテンプレート（CSS/JS）
src/build_pub.py      ビルドスクリプト
```

## 問題を追加・修正する

1. `src/bank.py` の `BANK` に `(分野キー, 問題文, [選択肢×4], 正解index, 解説)` を追加・編集
2. ビルド:

```bash
cd src && python build_pub.py
```

3. 生成された `src/index.html` を `<!DOCTYPE html>` 付きの完全なHTMLに包んでルートの `index.html` を更新（`make_standalone.py` 参照）
4. コミットして push すると Vercel が自動でデプロイします。
