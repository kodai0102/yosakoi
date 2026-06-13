# YOSAKOI PHOTO ARCHIVE

Phase0 では、FastAPI、PostgreSQL、Docker Compose、Alembic、Health Check API の最小構成を提供します。
Phase1 では、JWT認証、ユーザー管理、CSV一括登録、操作ログの最小構成を提供します。

## 前提

- Docker
- Docker Compose

## セットアップ

```bash
cp .env.example .env
```

## Docker 起動

```bash
docker compose up --build
```

バックグラウンドで起動する場合:

```bash
docker compose up -d --build
```

## DB 接続情報

DB接続情報は `.env` に集約しています。Docker Compose からは `.env` の環境変数を参照します。

ローカルPCのDBクライアントから接続する場合:

```text
Host: 127.0.0.1
Port: 5432
Database: yosakoi
User: yosakoi
Password: yosakoi
```

アプリコンテナから接続する場合:

```text
DATABASE_URL=postgresql+asyncpg://yosakoi:yosakoi@db:5432/yosakoi
```

## Health Check API

アプリケーションの起動確認:

```bash
curl http://localhost:8000/health
```

期待されるレスポンス:

```json
{"status":"ok"}
```

PostgreSQL 接続確認:

```bash
curl http://localhost:8000/health/db
```

期待されるレスポンス:

```json
{"status":"ok","database":"available"}
```

## Alembic

現在のマイグレーション状態確認:

```bash
docker compose exec app alembic current
```

マイグレーション実行:

```bash
docker compose exec app alembic upgrade head
```

## 初期管理者作成

`.env` の `INITIAL_ADMIN_*` を確認してから実行します。

```bash
docker compose exec app python -m app.scripts.create_initial_admin
```

初期値:

- ログインID: `admin`
- パスワード: `admin-password`

## ログイン

ブラウザで以下を開きます。

```text
http://localhost:8000/login
```

## 停止

```bash
docker compose down
```

DB ボリュームも削除する場合:

```bash
docker compose down -v
```
