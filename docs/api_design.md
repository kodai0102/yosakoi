# YOSAKOI PHOTO ARCHIVE API設計

## 1. 設計方針

本API設計は、FastAPI + Jinja2 の構成を前提に、画面表示用のルートと非同期操作用 API を分けて整理します。

方針:

- 画面表示は Jinja2 の HTML レスポンスを基本とする。
- 状態変更や部分更新は JSON API または HTMX 対応エンドポイントとして提供する。
- API 側で必ず認証・認可チェックを行う。
- 一般ユーザー向け API では、アカウント利用期間、アルバム公開期間、写真論理削除状態を必ずチェックする。
- 管理者 API は `role = admin` のみ許可する。
- R2 の画像 URL は DB に保存せず、表示・ダウンロード時に Presigned URL を発行する。

## 2. 認証・共通仕様

### 2.1 認証方式

- JWT 認証を使用する。
- JWT は HttpOnly Cookie で保持する。Cookie/JWT の有効期限は `ACCESS_TOKEN_EXPIRE_MINUTES` で管理し、現行実装では30分とする。
- ログイン中のアクセスごとにJWT Cookieを更新するスライディング方式とし、無操作時間が有効期限を超えた場合は再ログインを求める。
- 状態変更リクエストには CSRF 対策を行う。

### 2.2 共通チェック

ログインユーザーに対して全画面/APIで以下を確認する。

```text
dept_user.is_active = true
AND current_timestamp >= dept_user.start_date
AND current_timestamp <= dept_user.end_date
```

満たさない場合:

- JWT Cookie を破棄
- 強制ログアウト
- ログイン画面へ誘導

### 2.3 権限

| 権限 | role | 可能な操作 |
| --- | --- | --- |
| 一般ユーザー | `member` | 写真閲覧、検索、お気に入り、ダウンロード |
| 管理者 | `admin` | 一般操作に加え、写真・アルバム・ユーザー・タグ・ログ管理 |

### 2.4 共通レスポンス

JSON API の成功レスポンス例:

```json
{
  "success": true,
  "data": {}
}
```

JSON API のエラーレスポンス例:

```json
{
  "success": false,
  "error": {
    "code": "validation_error",
    "message": "入力内容を確認してください"
  }
}
```

### 2.5 主なエラーコード

| HTTP | code | 概要 |
| --- | --- | --- |
| 400 | `validation_error` | 入力不正 |
| 401 | `unauthorized` | 未ログイン、JWT不正 |
| 403 | `forbidden` | 権限不足 |
| 403 | `account_expired` | 利用期間外 |
| 404 | `not_found` | 対象なし |
| 409 | `duplicate` | 重複登録 |
| 409 | `conflict` | 関連データが残っている等の状態不整合 |
| 413 | `payload_too_large` | アップロード容量超過 |
| 415 | `unsupported_media_type` | 非対応画像形式 |
| 500 | `internal_error` | サーバーエラー |

## 3. 画面ルート一覧

### 3.1 認証・共通

| Method | Path | 権限 | 概要 |
| --- | --- | --- | --- |
| GET | `/login` | 未ログイン | ログイン画面 |
| POST | `/login` | 未ログイン | ログイン実行 |
| POST | `/logout` | ログイン済み | ログアウト |
| GET | `/search` | ログイン済み | 検索結果画面 |

### 3.2 一般ユーザー画面

| Method | Path | 権限 | 概要 |
| --- | --- | --- | --- |
| GET | `/` | member/admin | ホーム画面 |
| GET | `/albums` | member/admin | 公開中アルバム一覧 |
| GET | `/albums/{album_id}` | member/admin | アルバム詳細・写真一覧 |
| GET | `/photos/{photo_id}` | member/admin | 写真詳細 |
| GET | `/favorites` | member/admin | お気に入り一覧 |
| GET | `/tags/{tag_id}/photos` | member/admin | タグ別写真一覧 |

### 3.3 管理者画面

| Method | Path | 権限 | 概要 |
| --- | --- | --- | --- |
| GET | `/admin` | admin | 管理ダッシュボード |
| GET | `/admin/users` | admin | ユーザー一覧 |
| GET | `/admin/users/new` | admin | ユーザー作成画面 |
| GET | `/admin/users/{user_id}/edit` | admin | ユーザー編集画面 |
| GET | `/admin/users/import` | admin | CSV一括登録画面 |
| GET | `/admin/albums` | admin | アルバム一覧 |
| GET | `/admin/albums/new` | admin | アルバム作成画面 |
| GET | `/admin/albums/{album_id}/edit` | admin | アルバム編集画面 |
| GET | `/admin/albums/{album_id}/photos` | admin | 写真管理画面 |
| GET | `/admin/tags` | admin | タグ管理画面 |
| GET | `/admin/logs` | admin | ログ一覧 |

## 4. API一覧

### 4.1 認証 API

| Method | Path | 権限 | 概要 |
| --- | --- | --- | --- |
| POST | `/api/auth/login` | 未ログイン | JWT Cookie発行、ログイン成功/失敗ログ記録 |
| POST | `/api/auth/logout` | ログイン済み | JWT Cookie破棄、ログアウトログ記録 |
| GET | `/api/auth/me` | ログイン済み | ログインユーザー情報取得 |

#### POST `/api/auth/login`

Request:

```json
{
  "login_id": "member001",
  "password": "password"
}
```

Response:

```json
{
  "success": true,
  "data": {
    "user": {
      "id": 1,
      "login_id": "member001",
      "display_name": "山田太郎",
      "role": "member"
    }
  }
}
```

### 4.2 ホーム API

| Method | Path | 権限 | 概要 |
| --- | --- | --- | --- |
| GET | `/api/home/summary` | member/admin | 新着アルバム、最近追加写真、お気に入り数 |

Response data:

- `recent_albums`
- `recent_photos`
- `favorite_count`

### 4.3 アルバム API

| Method | Path | 権限 | 概要 |
| --- | --- | --- | --- |
| GET | `/api/albums` | member/admin | 公開中アルバム一覧 |
| GET | `/api/albums/{album_id}` | member/admin | アルバム詳細 |
| GET | `/api/albums/{album_id}/photos` | member/admin | アルバム内写真一覧 |

#### GET `/api/albums`

Query:

| パラメータ | 必須 | 概要 |
| --- | --- | --- |
| year | NO | 年度 |
| event_name | NO | イベント名 |
| q | NO | タイトル・説明検索 |
| page | NO | ページ番号 |
| per_page | NO | 件数 |

一般ユーザー向け条件:

- 公開期間内のアルバムのみ。

### 4.4 写真 API

| Method | Path | 権限 | 概要 |
| --- | --- | --- | --- |
| GET | `/api/photos/{photo_id}` | member/admin | 写真詳細 |
| GET | `/api/photos/{photo_id}/view-url` | member/admin | 表示用 Presigned URL 発行 |
| POST | `/api/photos/{photo_id}/download` | member/admin | ダウンロードURL発行、履歴記録 |
| GET | `/api/photos` | member/admin | 写真検索 |

#### GET `/api/photos`

Query:

| パラメータ | 必須 | 概要 |
| --- | --- | --- |
| q | NO | イベント名、アルバム名、タグ名の検索 |
| year | NO | 年度 |
| event_name | NO | イベント |
| tag_id | NO | タグ |
| album_id | NO | アルバム |
| page | NO | ページ番号 |
| per_page | NO | 件数 |

Response data item:

```json
{
  "id": "b0b2d7aa-0000-0000-0000-000000000001",
  "album_id": 10,
  "album_title": "本祭1日目",
  "event_name": "本祭1日目",
  "taken_at": "2026-08-10T10:30:00+09:00",
  "thumbnail_url": "https://presigned-url.example",
  "is_favorite": true,
  "is_downloaded": false,
  "tags": ["山田太郎", "旗士"]
}
```

#### POST `/api/photos/{photo_id}/download`

処理:

1. 認証・利用期間チェック
2. 写真の公開可否チェック
3. `download_histories` 登録
4. `access_log` に写真ダウンロード情報を記録
5. 原本画像の Presigned URL を返す

Response:

```json
{
  "success": true,
  "data": {
    "download_url": "https://presigned-url.example",
    "expires_in": 900
  }
}
```

### 4.5 お気に入り API

| Method | Path | 権限 | 概要 |
| --- | --- | --- | --- |
| GET | `/api/favorites` | member/admin | お気に入り写真一覧 |
| POST | `/api/photos/{photo_id}/favorite` | member/admin | お気に入り登録 |
| DELETE | `/api/photos/{photo_id}/favorite` | member/admin | お気に入り解除 |

#### POST `/api/photos/{photo_id}/favorite`

Response:

```json
{
  "success": true,
  "data": {
    "photo_id": "b0b2d7aa-0000-0000-0000-000000000001",
    "is_favorite": true
  }
}
```

### 4.6 タグ API

| Method | Path | 権限 | 概要 |
| --- | --- | --- | --- |
| GET | `/api/tags` | member/admin | タグ一覧・検索 |
| GET | `/api/tags/{tag_id}/photos` | member/admin | タグ付き写真一覧 |

Query:

| パラメータ | 必須 | 概要 |
| --- | --- | --- |
| q | NO | タグ名部分一致 |

### 4.7 管理者: ダッシュボード API

| Method | Path | 権限 | 概要 |
| --- | --- | --- | --- |
| GET | `/api/admin/dashboard` | admin | ユーザー数、写真数、アルバム数、ダウンロード数 |

Response data:

- `user_count`
- `photo_count`
- `album_count`
- `download_count`

### 4.8 管理者: ユーザー管理 API

| Method | Path | 権限 | 概要 |
| --- | --- | --- | --- |
| GET | `/api/admin/users` | admin | ユーザー一覧 |
| POST | `/api/admin/users` | admin | ユーザー作成 |
| GET | `/api/admin/users/{user_id}` | admin | ユーザー詳細 |
| PUT | `/api/admin/users/{user_id}` | admin | ユーザー編集 |
| POST | `/api/admin/users/{user_id}/activate` | admin | 有効化 |
| POST | `/api/admin/users/{user_id}/deactivate` | admin | 無効化 |
| POST | `/api/admin/users/import` | admin | CSV一括登録 |

#### POST `/api/admin/users`

Request:

```json
{
  "login_id": "member001",
  "display_name": "山田太郎",
  "password": "initial-password",
  "role": "member",
  "valid_from": "2026-08-01T00:00:00+09:00",
  "valid_to": "2026-09-01T23:59:59+09:00",
  "is_active": true
}
```

処理:

- パスワードを bcrypt でハッシュ化。
- `login_id` 重複をチェック。
- ユーザー情報は `dept_user` に保存し、必要に応じて `access_log` に操作履歴を記録。

#### POST `/api/admin/users/import`

Content-Type:

- `multipart/form-data`

CSV列:

```csv
login_id,display_name,valid_from,valid_to
member001,山田太郎,2026-08-01,2026-09-01
```

初期パスワード:

- CSV にはパスワード列を含めない。
- 管理者がインポート画面で共通初期パスワードを入力する。
- 登録時に共通初期パスワードを bcrypt でハッシュ化して保存する。
- 初期パスワードは画面上に再表示せず、管理者が別経路で対象者へ通知する。

Response data:

- `created_count`
- `skipped_count`
- `errors`

### 4.9 管理者: アルバム管理 API

| Method | Path | 権限 | 概要 |
| --- | --- | --- | --- |
| GET | `/api/admin/albums` | admin | アルバム一覧 |
| POST | `/api/admin/albums` | admin | アルバム作成 |
| GET | `/api/admin/albums/{album_id}` | admin | アルバム詳細 |
| PUT | `/api/admin/albums/{album_id}` | admin | アルバム編集 |
| DELETE | `/api/admin/albums/{album_id}` | admin | アルバム削除 |

#### POST `/api/admin/albums`

Request:

```json
{
  "year": 2026,
  "event_name": "本祭1日目",
  "event_date": "2026-08-10",
  "title": "2026 本祭1日目",
  "description": "本祭1日目の写真",
  "publish_from": "2026-08-01T00:00:00+09:00",
  "publish_to": "2026-09-01T23:59:59+09:00"
}
```

#### DELETE `/api/admin/albums/{album_id}`

MVP の挙動:

- 紐づく写真が1件以上存在する場合は削除不可とする。
- 論理削除済み写真が紐づく場合も削除不可とする。
- 削除不可の場合は `409 conflict` として、写真が残っているため削除できない旨を返す。
- 写真が存在しないアルバムのみ削除できる。

### 4.10 管理者: 写真管理 API

| Method | Path | 権限 | 概要 |
| --- | --- | --- | --- |
| POST | `/api/admin/albums/{album_id}/photos` | admin | 複数写真アップロード |
| DELETE | `/api/admin/photos/{photo_id}` | admin | 写真論理削除 |
| PUT | `/api/admin/photos/{photo_id}/tags` | admin | 写真のタグ付け更新 |

#### POST `/api/admin/albums/{album_id}/photos`

Content-Type:

- `multipart/form-data`

Fields:

| フィールド | 必須 | 概要 |
| --- | --- | --- |
| files | YES | 複数画像ファイル |

処理:

1. ファイル形式を検証する。
2. Exif 撮影日時を取得する。
3. Exif がない場合、アップロード日時、`albums.event_date` の順で補完する。
4. サムネイルを生成する。
5. 原本とサムネイルを R2 に保存する。ローカル開発ではR2オブジェクトキー互換のパスで `LOCAL_STORAGE_ROOT` 配下へ保存する。
6. `photos` を登録する。
7. `access_log` または管理ログに写真アップロードを記録する。

#### PUT `/api/admin/photos/{photo_id}/tags`

Request:

```json
{
  "tag_ids": [1, 2, 3]
}
```

処理:

- 既存のタグ関連を差分更新する。
- 存在しないタグIDはエラー。

### 4.11 管理者: タグ管理 API

| Method | Path | 権限 | 概要 |
| --- | --- | --- | --- |
| POST | `/api/admin/tags` | admin | タグ作成 |
| PUT | `/api/admin/tags/{tag_id}` | admin | タグ編集 |
| DELETE | `/api/admin/tags/{tag_id}` | admin | タグ削除 |

#### POST `/api/admin/tags`

Request:

```json
{
  "name": "山田太郎"
}
```

#### DELETE `/api/admin/tags/{tag_id}`

MVP の挙動:

- `photo_dancer_tags` に紐づきがあるタグは削除不可とする。
- 削除不可の場合は `409 conflict` として、写真に付与済みのため削除できない旨を返す。
- 紐づきがないタグのみ削除できる。

### 4.12 管理者: ログ API

| Method | Path | 権限 | 概要 |
| --- | --- | --- | --- |
| GET | `/api/admin/logs` | admin | 操作ログ一覧 |
| GET | `/api/admin/logs.csv` | admin | 操作ログ CSV 出力 |

Query:

| パラメータ | 必須 | 概要 |
| --- | --- | --- |
| user_id | NO | ユーザー |
| action_type | NO | 操作種別 |
| from | NO | 開始日時 |
| to | NO | 終了日時 |
| page | NO | ページ番号 |
| per_page | NO | 件数 |

## 5. 画面とAPIの対応

| 画面 | 主に利用するAPI |
| --- | --- |
| ホーム | `/api/home/summary` |
| アルバム一覧 | `/api/albums` |
| 写真一覧 | `/api/albums/{album_id}/photos`, `/api/photos/{photo_id}/favorite` |
| 写真詳細 | `/api/photos/{photo_id}`, `/api/photos/{photo_id}/view-url`, `/api/photos/{photo_id}/download` |
| お気に入り一覧 | `/api/favorites` |
| タグ別写真一覧 | `/api/tags/{tag_id}/photos` |
| 検索結果 | `/api/photos`, `/api/albums` |
| 管理ダッシュボード | `/api/admin/dashboard` |
| ユーザー管理 | `/api/admin/users`, `/api/admin/users/import` |
| アルバム管理 | `/api/admin/albums` |
| 写真管理 | `/api/admin/albums/{album_id}/photos`, `/api/admin/photos/{photo_id}/tags` |
| タグ管理 | `/api/admin/tags` |
| ログ管理 | `/api/admin/logs`, `/api/admin/logs.csv` |

## 6. 実装上の注意点

### 6.1 公開可否チェック

写真表示 API は、写真単体の存在確認だけでなく、必ず紐づくアルバムの公開期間も確認します。

```text
photos.is_deleted = false
AND current_timestamp BETWEEN albums.publish_from AND albums.publish_to
```

### 6.2 ダウンロードログ

ダウンロード API では、Presigned URL を返す前に `download_histories` と `access_log` の両方へ記録します。

### 6.3 Presigned URL

- サムネイル表示用と原本表示/ダウンロード用を区別する。
- 有効期限は 900 秒。
- DB に Presigned URL は保存しない。
- Service Worker では Presigned URL 付き画像をキャッシュしない。
- PWA のキャッシュ対象は CSS、JavaScript、アイコン等の静的アセットを基本とする。

### 6.4 ページネーション

写真一覧、検索結果、ログ一覧はページネーションを必須とします。

推奨デフォルト:

- `page = 1`
- `per_page = 30`

### 6.5 CSRF 対策

以下は CSRF 対策対象です。

- ログアウト
- お気に入り登録/解除
- ダウンロードURL発行
- 管理者の作成・更新・削除操作
- CSV インポート
- 写真アップロード

## 7. 未確定事項

| 項目 | 論点 | 推奨 |
| --- | --- | --- |
| JWT保存場所 | Cookie / LocalStorage | HttpOnly Cookie 推奨 |
| APIレスポンス方式 | 全面JSON / HTMX部分HTML併用 | MVPでは画面はHTML、操作はJSON中心 |
| CSV文字コード | UTF-8 / CP932 | UTF-8優先、CP932も許容すると運用しやすい |
