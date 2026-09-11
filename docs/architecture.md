# アーキテクチャと CI/CD

## 全体像

```mermaid
flowchart LR
  subgraph GitHub
    Repo[(g-kentei-lab<br/>main)]
    CI[Actions: CI<br/>lint / pytest / cfn-lint / sam validate / site build]
    DS[Actions: Deploy Site]
    DA[Actions: Deploy API]
  end
  subgraph "GitHub Pages"
    Site[静的サイト<br/>index.html]
  end
  subgraph AWS["AWS (ap-northeast-1)"]
    GW[API Gateway<br/>HTTP API]
    L1[Lambda<br/>progress]
    L2[Lambda<br/>results]
    L3[Lambda<br/>stats]
    DDB[(DynamoDB<br/>g-kentei-lab-{stage})]
    CW[CloudWatch<br/>Logs / Alarms / X-Ray]
  end
  Browser((受検者の<br/>ブラウザ))

  Repo -->|PR / push| CI
  Repo -->|push main, src/**| DS -->|upload-pages-artifact| Site
  Repo -->|push main, api/**| DA -->|OIDC → sam deploy| GW
  Browser -->|HTML/JS| Site
  Browser -->|fetch JSON<br/>CORS| GW
  GW --> L1 & L2 & L3
  L1 & L2 --> DDB
  L3 -->|Query| DDB
  L1 & L2 & L3 -.-> CW
```

サイトは静的 HTML 1 枚で完結し、API は **任意の拡張** です。ビルド時に `GK_API_BASE` が空なら
API 連携のコードは一切呼ばれず、従来どおり localStorage だけで動きます。

## API が提供する機能

| 機能 | エンドポイント | 用途 |
|---|---|---|
| 端末間同期 | `GET/PUT/DELETE /v1/progress/{syncKey}` | ログイン不要。ブラウザが発行した 16 文字の同期コードを知っている端末だけが同じ記録を読み書きできる |
| 結果の匿名集計 | `POST /v1/results` | 模擬試験・演習の結果を送信（オプトアウト可）。個人を特定する情報は送らない |
| 集計の参照 | `GET /v1/stats` | 模試の受験回数と平均、分野別正答率、問題ごとの「みんなの正答率」 |
| 死活確認 | `GET /v1/health` | デプロイ後のスモークテストに使用 |

### リクエスト / レスポンス

`PUT /v1/progress/{syncKey}`

```json
{ "data": { "quiz": {...}, "terms": {...}, "mocks": [...] }, "updatedAt": 1789170310812 }
```

- `updatedAt` が保存済みより古い場合は **409** で現在の記録を返す（クライアントは統合してから再送）。
- 1 年間更新がない記録は TTL で自動削除。

`POST /v1/results`

```json
{
  "resultId": "20文字の一意ID", "clientId": "16文字の匿名ID", "kind": "mock",
  "n": 30, "correct": 21, "sec": 1180,
  "byCat": { "cv": { "n": 5, "ok": 4 } },
  "answers": [ { "id": "cv-1a2b3c", "ok": true } ]
}
```

- 同じ `resultId` の再送は **200 `duplicate: true`** で二重集計しない（冪等）。
- バリデーション（範囲・正規表現・件数上限）に外れる入力は 400。

`GET /v1/stats`

```json
{
  "global": { "mockCount": 12, "mockAvgPct": 68, "practiceCount": 40, "answered": 800, "correct": 520 },
  "cats": { "cv": { "n": 120, "ok": 80, "pct": 67 } },
  "questions": { "cv-1a2b3c": { "a": 25, "c": 20, "pct": 80 } }
}
```

## DynamoDB の設計（シングルテーブル）

| PK | SK | 内容 | 更新方法 |
|---|---|---|---|
| `USER#<syncKey>` | `PROGRESS` | 学習記録 (`data`, `updatedAt`, `ttl`) | 条件付き `PutItem`（楽観ロック） |
| `RESULT#<yyyy-mm>` | `<resultId>` | 個別の結果（分析用、TTL 400 日） | 条件付き `PutItem`（冪等キー） |
| `STATS` | `GLOBAL` | 種別ごとの件数・スコア合計・回答数 | `UpdateItem ADD` |
| `STATS` | `CAT#<cat>` | 分野ごとの出題数・正解数 | `UpdateItem ADD` |
| `QSTAT` | `<questionId>` | 問題ごとの出題数・正解数 | `UpdateItem ADD` |

- 集計は書き込み時に加算しておき、読み出しは `STATS` と `QSTAT` の 2 パーティションを Query するだけ（問題数 190 件 + 分野 9 件）。
- オンデマンド課金、サーバサイド暗号化、prod は PITR 有効・`DeletionPolicy: Retain`。
- 個人情報は保存しない。`clientId` はブラウザ生成のランダム値で、同一端末の重複投稿の把握にのみ使う。

## Lambda

- Python 3.12 / arm64 / 256 MB / 10 s。外部依存なし（boto3 はランタイム同梱）。
- 共通コードは Lambda Layer `layer/python/gk_common.py`（レスポンス整形、バリデーション、例外→JSON）。
- IAM は関数ごとに最小権限（`stats` は読み取りのみ）。X-Ray トレース有効。
- CloudWatch Alarm: API 5xx ≥ 5 / 5 分、Lambda Errors ≥ 5 / 5 分（通知先は必要に応じて SNS を追加）。

## CI/CD

```mermaid
flowchart LR
  PR[Pull Request] --> CI
  CI{CI: ruff · pytest(moto) · cfn-lint · sam validate · site build + node --check}
  CI -->|merge| Main[main]
  Main -->|api/** 変更| T[test] --> S[deploy → staging<br/>sam deploy + smoke test] --> P[deploy → production<br/>環境の Required reviewers で手動承認]
  Main -->|src/** 変更| B[build site<br/>GK_API_BASE を埋め込み] --> Pages[deploy-pages]
```

| ワークフロー | トリガー | 内容 |
|---|---|---|
| `ci.yml` | PR / push | API の lint・単体テスト（moto で DynamoDB をモック）・テンプレート lint、サイトのビルド検証 |
| `deploy-api.yml` | `api/**` の push（main）/ 手動 | `sam build` → staging に `sam deploy` → `/v1/health` `/v1/stats` のスモークテスト → production（GitHub Environment の承認ゲート） |
| `deploy-site.yml` | `src/**` の push（main）/ 手動 | ビルドして GitHub Pages にデプロイ。リポジトリ変数 `GK_API_BASE` があれば API 連携を有効化 |

- AWS 認証は **OIDC**（`aws-actions/configure-aws-credentials` の `role-to-assume`）。長期キーは置かない。
- 同時デプロイは `concurrency` で直列化。
- staging と prod は別スタック（`g-kentei-lab-api-staging` / `-prod`）・別テーブル。

## 初回セットアップ（AWS 側は 1 回だけ）

1. AWS アカウントで `infra/github-oidc-role.yaml` をデプロイ（CloudFormation コンソール、または CLI）:
   ```bash
   aws cloudformation deploy --stack-name g-kentei-lab-github-oidc \
     --template-file infra/github-oidc-role.yaml --capabilities CAPABILITY_NAMED_IAM \
     --parameter-overrides GitHubOrg=clochetined GitHubRepo=g-kentei-lab
   ```
   既に GitHub の OIDC プロバイダがあるアカウントでは `CreateOidcProvider=false` を付ける。
2. Outputs の `RoleArn` を GitHub の **Settings → Environments** で `staging` と `production` を作成し、
   それぞれの環境シークレット `AWS_ROLE_ARN` に設定。`production` には Required reviewers を付ける。
3. リポジトリ変数 `AWS_DEPLOY_ENABLED` を `true` に設定（これが無い間、デプロイジョブはスキップされる）。
   `Actions → Deploy API → Run workflow`（または `api/` を変更して push）。ジョブのサマリーに API URL が出る。
4. リポジトリの **Settings → Secrets and variables → Actions → Variables** に `GK_API_BASE`（prod の API URL）を設定し、
   `Deploy Site` を実行。以降サイトが集計・同期機能を表示する。
5. 独自ドメインを使う場合は `api/samconfig.toml` の `AllowedOrigins` にそのオリジンを追加する。

## ローカル開発

```bash
cd api && pip install -r requirements-dev.txt
pytest                                  # 単体テスト
python dev_server.py                    # http://127.0.0.1:8787（moto のインメモリ DynamoDB）
cd .. && GK_API_BASE=http://127.0.0.1:8787 python src/build_pub.py && python src/make_standalone.py
python -m http.server 8000 --directory dist
```

SAM CLI があれば `sam build && sam local start-api` でも動く（`--parameter-overrides Stage=staging`）。

## 費用の目安

すべて従量課金で、無料枠内に収まる規模を想定（API Gateway 100 万リクエスト/月まで無料枠、Lambda 100 万リクエスト、DynamoDB 25 GB・オンデマンド 250 万リクエスト相当）。利用が増えても月数百円程度。
