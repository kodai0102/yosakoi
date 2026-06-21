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

## セッション有効期限

ログイン状態はサーバー側セッションではなく、JWTをHttpOnly Cookieへ保存して管理します。
`ACCESS_TOKEN_EXPIRE_MINUTES` の時間だけ無操作が続くとCookie/JWTが期限切れになり、次回アクセス時にログイン画面へ戻ります。
操作中はアクセスごとにCookie/JWTを更新します。

## 停止

```bash
docker compose down
```

DB ボリュームも削除する場合:

```bash
docker compose down -v
```

## 本番デプロイ準備

本番環境では、開発用の `docker-compose.yml` ではなく `docker-compose.prod.yml` を利用します。
開発用構成はソースコードをコンテナへマウントし、`--reload` で起動します。
本番用構成はイメージ内のコードで起動し、DB と画像保存先を Docker volume で永続化します。

### 本番用 .env 作成

```bash
cp .env.production.example .env
```

`.env` の以下は必ず本番用の強い値に変更してください。

- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `INITIAL_ADMIN_PASSWORD`
- `APP_PORT`

`DATABASE_URL` のパスワード部分は `POSTGRES_PASSWORD` と一致させます。
`APP_PORT` はEC2上で直接疎通確認するポートです。通常は `8000` のままで構いません。

### 本番用 Docker Compose 起動

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

マイグレーション:

```bash
docker compose -f docker-compose.prod.yml exec app alembic upgrade head
```

初期管理者作成:

```bash
docker compose -f docker-compose.prod.yml exec app python -m app.scripts.create_initial_admin
```

ヘルスチェック:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/db
```

既存の開発用アプリと同じPCでリハーサルする場合は、ポート競合を避けるため一時的に `APP_PORT=8010` などへ変更して起動します。

ログ確認:

```bash
docker compose -f docker-compose.prod.yml logs -f app
```

停止:

```bash
docker compose -f docker-compose.prod.yml down
```

DB と画像データも削除する場合のみ:

```bash
docker compose -f docker-compose.prod.yml down -v
```

### 永続化対象

本番用 Docker Compose では以下を Docker volume に保存します。

- `postgres_data_prod`: PostgreSQL データ
- `app_storage`: アップロード画像、サムネイル画像

EC2 運用では、この2つをバックアップ対象にしてください。

## EC2 デプロイ手順

1. EC2 インスタンスを作成します。
2. セキュリティグループで SSH は管理者IPのみに制限します。
3. HTTP/HTTPS 公開用に `80` / `443` を開放します。
4. Docker と Docker Compose plugin をインストールします。
5. アプリケーションソースを EC2 に配置します。
6. `.env.production.example` をもとに `.env` を作成します。
7. `docker compose -f docker-compose.prod.yml up -d --build` を実行します。
8. `alembic upgrade head` を実行します。
9. 初期管理者を作成します。
10. `/health` と `/health/db` を確認します。

まずは `8000` 番ポートで疎通確認できますが、本運用では Nginx などのリバースプロキシを前段に置き、HTTPS 化してください。

### EC2 本運用前チェック

- `.env` に初期パスワードや弱いJWT秘密鍵が残っていないこと
- DBポート `5432` を外部公開していないこと
- 画像保存 volume のバックアップ方針があること
- PostgreSQL volume のバックアップ方針があること
- HTTPS でアクセスできること
- 初期管理者パスワードを運用開始前に変更していること

## テーブル構成

### ユーザーアカウントテーブル
名称：dept_user
概要：ユーザーの個人情報やID、パスワードを管理
カラム案：user_no, user_id, user_name, password, create_date, start_date, end_date
補足：create_date, start_date, end_date は日時型
主キー：user_no, user_id,

### アクセスログテーブル
名称：access_log
概要：ユーザーのログオン時間、ログオフ時間、写真アップロード時間、写真ダウンロード時間、アップロード/ダウンロードした写真、お気に入りの情報を管理
カラム案：rireki_no, user_name, user_id, logon_time, logoff_time, pic_upload_time, pic_upload_list, pic_download_time, pic_download_list, favorite
補足：logon_time, logoff_time, pic_upload_time, pic_download_time は dept_user.create_date と同じ日時型
主キー：rireki_no
外部キー：user_id
