# YOSAKOI PHOTO ARCHIVE

Phase1 では、FastAPI、PostgreSQL、Docker Compose、Alembic、Health Check API の最小構成を提供します。

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

Phase1 ではテーブル作成は対象外のため、初期マイグレーションファイルはまだ作成していません。

## 停止

```bash
docker compose down
```

DB ボリュームも削除する場合:

```bash
docker compose down -v
```
