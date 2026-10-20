# Mobile Order

飲食店向けのQRコード式モバイルオーダーWebアプリケーションです。お客様が自身のスマートフォンでメニューを閲覧・注文でき、店舗スタッフと管理者は注文・会計や商品・店舗情報を管理できます。

> このリポジトリはデモ・ポートフォリオ用の開発プロジェクトです。公開環境は準備中です。

## 主な機能

| 利用者 | 機能 |
| --- | --- |
| お客様 | テーブルQRコード経由のアクセス、ニックネーム登録、カテゴリ別メニュー表示、商品選択、注文、注文履歴、提供状況・会計確認、割り勘 |
| スタッフ | Cognitoログイン、テーブル利用開始、代理注文、注文一覧、提供済み登録・取消、数量単位のキャンセル、会計完了 |
| 管理者 | Cognitoログイン、商品・カテゴリ・テーブル・営業時間の管理、スタッフアカウント管理、会計履歴確認、会計完了の取消 |

## 使用技術

| 分類 | 技術 |
| --- | --- |
| フロントエンド | React、TypeScript、Vite |
| バックエンド | Python、FastAPI、Uvicorn |
| データベース | PostgreSQL、SQLAlchemy、psycopg |
| マイグレーション | Alembic |
| 認証 | AWS Cognito、JWT |
| 画像管理 | Amazon S3、boto3 |
| 通信 | HTTP API、WebSocket |
| テスト・静的解析 | pytest、Oxlint |

## ディレクトリ構成

```text
mobile-order/
├── backend/
│   ├── app/              # FastAPI本体・認証・ルーター・DBモデル等
│   ├── alembic/          # DBマイグレーション
│   ├── tests/            # バックエンドテスト
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/              # React画面・API通信
│   ├── public/
│   ├── package.json
│   └── .env.example
└── .gitignore
```

## ローカル環境のセットアップ

事前にPython、Node.js、PostgreSQLをインストールし、PostgreSQLにアプリ用データベースを作成してください。AWS CognitoおよびAmazon S3を使う機能には、別途AWS側の設定と適切なアクセス権限が必要です。

### 1. バックエンド

リポジトリの `backend` ディレクトリで実行します。

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

`backend/.env` にDB接続先、JWT署名用シークレット、AWS関連の設定を記入します。設定項目は `backend/.env.example` を参照してください。

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

起動後、APIのドキュメントは `http://localhost:8000/docs` で確認できます。

### 2. フロントエンド

別のターミナルで `frontend` ディレクトリに移動して実行します。

```powershell
cd frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

ブラウザで `http://localhost:5173` にアクセスします。フロントエンドのCognito設定は `frontend/.env.example` を参照してください。

> 現状のソースコードにはAPI接続先として `http://localhost:8000` を直接指定している箇所があります。クラウド公開前にはAPI URLを環境変数化し、FastAPIのCORS許可オリジンおよびCognitoのコールバック・ログアウトURLも公開先に合わせて設定してください。

## テスト・ビルド

```powershell
# backend/ で実行
python -m pytest

# frontend/ で実行
npm run lint
npm run build
```

## 環境変数と秘密情報

`.env` ファイルやシークレット、DBパスワード、AWS認証情報はコミットしないでください。サンプル値は `.env.example` に記載し、公開環境では各ホスティングサービスの環境変数管理機能を利用します。フロントエンド用の `VITE_` 変数には秘密情報を格納しないでください。

## デプロイ状況

社内発表・ポートフォリオ向けのデモ公開を予定しています。デプロイURLは公開後に追記します。

## 留意事項

本アプリはデモ用プロジェクトであり、実店舗での本番運用に必要な運用監視、セキュリティ検証、負荷試験等が完了したことを示すものではありません。
