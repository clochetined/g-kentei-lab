# G検定 模試ラボ

G検定（JDLA Deep Learning for GENERAL）対策のオリジナル問題サイト。
9分野190問の4択問題と解説、時間制限つき模擬試験、要点整理、用語集を1枚の静的HTMLで提供します。

**公開サイト:** https://clochetined.github.io/g-kentei-lab/

- 問題・解説・要点・用語はすべてオリジナル（AI作成）。公式試験問題や市販書籍の転載は含みません。
- 学習記録はブラウザの localStorage に保存。API を有効にすると「端末間同期」と「みんなの正答率」が使えます。

[![CI](https://github.com/clochetined/g-kentei-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/clochetined/g-kentei-lab/actions/workflows/ci.yml)
[![Deploy Site](https://github.com/clochetined/g-kentei-lab/actions/workflows/deploy-site.yml/badge.svg)](https://github.com/clochetined/g-kentei-lab/actions/workflows/deploy-site.yml)
[![Deploy API](https://github.com/clochetined/g-kentei-lab/actions/workflows/deploy-api.yml/badge.svg)](https://github.com/clochetined/g-kentei-lab/actions/workflows/deploy-api.yml)

## 構成

```
src/bank.py              問題バンク（分野, 問題文, 選択肢×4, 正解index, 解説）
src/notes.py             要点整理と用語集
src/template_pub.html    ページのテンプレート（CSS/JS）
src/build_pub.py         ビルド → src/index.html（GK_API_BASE で API 連携を有効化）
src/make_standalone.py   完全な HTML 文書として dist/index.html に書き出し
api/                     サーバーレス API（AWS SAM: DynamoDB + Lambda + API Gateway）
  template.yaml          インフラ定義
  functions/{progress,results,stats}/app.py
  layer/python/gk_common.py
  tests/                 pytest + moto
  dev_server.py          AWS 不要のローカル API
infra/github-oidc-role.yaml   GitHub Actions → AWS の OIDC ロール（初回のみ）
.github/workflows/       ci.yml / deploy-site.yml / deploy-api.yml
docs/architecture.md     設計・API 仕様・CI/CD・セットアップ手順
```

## 問題を追加・修正する

1. `src/bank.py` の `BANK` に `(分野キー, 問題文, [選択肢×4], 正解index, 解説)` を追加・編集
2. `python src/build_pub.py && python src/make_standalone.py` でローカル確認（`dist/index.html`）
3. `main` に push すると **Deploy Site** ワークフローが GitHub Pages へ自動デプロイ

## API を動かす

設計・データモデル・セットアップ手順は [docs/architecture.md](docs/architecture.md) を参照。

```bash
cd api
pip install -r requirements-dev.txt
pytest                      # 単体テスト（DynamoDB は moto でモック）
python dev_server.py        # ローカル API http://127.0.0.1:8787
```

AWS へは GitHub Actions（**Deploy API**）が `sam deploy` します。初回だけ `infra/github-oidc-role.yaml` で
デプロイ用ロールを作り、GitHub Environments（staging / production）のシークレット `AWS_ROLE_ARN` に設定してください。
