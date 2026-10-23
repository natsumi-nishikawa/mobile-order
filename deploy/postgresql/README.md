# PostgreSQL本番セキュリティ設定手順（Ubuntu 24.04）

この手順は、PostgreSQLを同一EC2のループバックだけで待ち受けさせ、FastAPIの実行権限とAlembicのDDL権限を分離するためのひな形です。既存設定を丸ごと置換せず、実機で確認したファイルへ必要な行だけを反映します。`REPLACE_WITH_*`は適用前に実在値へ置換してください。秘密値をGit、画面共有、シェル履歴、ログへ残さないでください。

SQL実行、設定ファイル編集、環境ファイル配置の直前に、実際に適用する全ファイルを共通プリフライトへ渡します。非0終了なら適用を中止します。リポジトリの`.example`は未置換であることが正常で、そのまま適用しません。

```bash
python3 deploy/preflight/validate_deployment_config.py REPLACE_WITH_RENDERED_POSTGRESQL_SNIPPET REPLACE_WITH_RENDERED_PG_HBA_SNIPPET REPLACE_WITH_RENDERED_ROLE_SQL REPLACE_WITH_RENDERED_MIGRATION_ENV
```

この検査は未置換マーカーとJSON形式を扱います。PostgreSQL固有の構文・認証ルールは、続く`pg_file_settings`、`pg_hba_file_rules`、隔離DB検証でも確認します。

## 設計

- 既存PostgreSQL管理者: クラスタ管理、ロール作成、障害復旧だけに使い、FastAPIや通常のAlembicには渡しません。
- `REPLACE_WITH_MIGRATION_ROLE`: LOGIN可能な非特権ロールです。対象DB、`public`スキーマ、Alembic管理下のテーブルとシーケンスを所有し、DDLを実行します。資格情報は一時的な管理作業だけに使います。
- `REPLACE_WITH_APP_ROLE`: LOGIN可能な非特権ロールです。対象DBへのCONNECT、スキーマUSAGE、テーブルのSELECT/INSERT/UPDATE/DELETE、シーケンスのUSAGE/SELECTだけを持ちます。オブジェクトを所有せず、スキーマCREATEを持ちません。

現行モデルはスキーマ名を明示していないため、この段階では`public`を維持します。5本の既存マイグレーションはテーブル、索引、列、制約を作成・変更・削除するため、アプリ用ロールでは実行できず、所有者であるマイグレーション用ロールで実行します。アプリの通常コードには起動時DDL処理はありません。

## 1. 適用前の停止条件とバックアップ

作業時間帯を確保し、現在のアプリ、PostgreSQL、Nginx設定と復旧担当者を確認します。次のいずれかを満たせなければ既存DBへ権限変更を適用しません。

1. 保護されたDBバックアップを取得できる。
2. `pg_restore --list`でアーカイブを読める。
3. 本番とは別の隔離DBへの復元試験、または承認済みの復元演習で復旧可能性を確認できる。
4. 現行設定ファイルと権限一覧を安全な場所へ戻せる。

例（保存先の容量、所有者、暗号化、保持期間を先に決める）:

```bash
sudo -u postgres pg_dump --format=custom --file=/REPLACE_WITH_PROTECTED_BACKUP_PATH/mobile-order-before-role-split.dump REPLACE_WITH_DATABASE_NAME
sudo -u postgres pg_restore --list /REPLACE_WITH_PROTECTED_BACKUP_PATH/mobile-order-before-role-split.dump >/dev/null
```

復元試験では隔離したDB名を使い、アプリや本番DBの接続先にしません。バックアップ自動化と保持期間の実装はこの段階の対象外です。

## 2. バージョン、設定ファイル、現状を確認

Ubuntuパッケージのバージョンやクラスタ名を推測せず確認します。

```bash
sudo pg_lsclusters
sudo -u postgres psql -X -d postgres -c "SHOW server_version;"
sudo -u postgres psql -X -d postgres -c "SHOW config_file; SHOW hba_file; SHOW data_directory; SHOW listen_addresses; SHOW password_encryption;"
sudo ss -lntp | grep ':5432'
```

対象DBへ接続し、ロール属性、DB・スキーマ所有者、既存テーブル・シーケンス所有者、権限を確認します。結果にパスワードや接続URLは含めません。

```sql
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
FROM pg_roles ORDER BY rolname;
SELECT datname, pg_get_userbyid(datdba) AS owner FROM pg_database;
SELECT nspname, pg_get_userbyid(nspowner) AS owner
FROM pg_namespace WHERE nspname = 'public';
SELECT schemaname, tablename, tableowner
FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
SELECT sequence_schema, sequence_name
FROM information_schema.sequences WHERE sequence_schema = 'public' ORDER BY sequence_name;
SELECT grantee, table_name, privilege_type
FROM information_schema.role_table_grants WHERE table_schema = 'public'
ORDER BY table_name, grantee, privilege_type;
```

`SHOW config_file`と`SHOW hba_file`で得た実パスをバックアップします。

```bash
sudo cp --preserve=all REPLACE_WITH_POSTGRESQL_CONF REPLACE_WITH_POSTGRESQL_CONF.pre-mobile-order
sudo cp --preserve=all REPLACE_WITH_PG_HBA_CONF REPLACE_WITH_PG_HBA_CONF.pre-mobile-order
```

## 3. ロールと所有権を準備

`create_roles_and_privileges.sql.example`を複製し、識別子だけを置換して管理者として実行します。既存ロールと衝突する場合はCREATEを繰り返さず、現状属性をレビューしてください。テンプレートは意図しない再実行を隠さないよう、冪等化していません。

SQLファイルにパスワードを書かず、管理者の対話型psqlで次を実行します。

```text
\password REPLACE_WITH_MIGRATION_ROLE
\password REPLACE_WITH_APP_ROLE
```

サーバー側の`password_encryption`が`scram-sha-256`になった後に設定し、保存形式を確認します。認証情報は別々の十分に強い値にします。

既存DBでは、所有者でなければAlembicが既存テーブルをALTERできません。現状一覧と5本のマイグレーションを照合してから`transfer_existing_ownership.sql.example`を調整します。存在しない行は削除し、独自追加オブジェクトは明示的に追加します。共有DBでの一括`REASSIGN OWNED`は、対象外オブジェクトまで移すため使用しません。所有権移行後に権限テンプレートのGRANTとDEFAULT PRIVILEGESを確認します。

DEFAULT PRIVILEGESは「その設定を行ったロールが将来作成するオブジェクト」にだけ効きます。したがって、将来のAlembicも必ずマイグレーション用ロールで実行します。別の所有者で作成するとアプリ用ロールへ権限が自動継承されません。

## 4. 接続制限を反映

`postgresql.conf.snippet.example`の2設定を、確認済みの現行`postgresql.conf`へ統合します。ファイル全体は置換しません。

- `listen_addresses = 'localhost'`: IPv4/IPv6のローカルだけで待受。
- `password_encryption = 'scram-sha-256'`: 今後設定・変更するパスワードをSCRAMで保存。

`pg_hba.conf.snippet.example`は先頭一致なので順序が重要です。Ubuntuの`local all postgres peer`管理経路を維持し、その直後で対象DBへのその他Unixソケット接続を拒否します。アプリとAlembicには対象DB・対象ロール・127.0.0.1/::1のSCRAM許可を使い、最後に対象DBのその他TCP接続を拒否します。管理者ロールや既存のローカル管理経路が`postgres`以外なら、拒否規則より前に同等の限定peer規則が必要です。既存の`local all all ...`や`host all all ...`が先にあれば、この限定規則を迂回するため、影響を確認したうえで削除または対象規則より後へ移動します。`trust`は追加しません。

EC2セキュリティグループとUFWでも5432/TCPの受信を許可しません。これは`listen_addresses`とpg_hba.confに加える多層防御です。

## 5. 反映前検証、reloadとrestart

編集後、現在稼働中の管理接続を閉じずに別ターミナルで確認します。

```sql
SELECT sourcefile, sourceline, name, setting, error
FROM pg_file_settings WHERE error IS NOT NULL;
SELECT line_number, type, database, user_name, address, auth_method, error
FROM pg_hba_file_rules WHERE error IS NOT NULL;
```

エラーが1件でもあれば反映しません。pg_hba.confだけの変更はreloadで反映できますが、`listen_addresses`はrestartが必要です。実際のバージョンとクラスタ名を使います。

```bash
sudo pg_ctlcluster REPLACE_WITH_VERSION REPLACE_WITH_CLUSTER reload
sudo pg_ctlcluster REPLACE_WITH_VERSION REPLACE_WITH_CLUSTER restart
```

再起動前にFastAPIを停止して短時間のメンテナンスとし、再起動後も管理者のpeer接続ができることを最初に確認します。設定値、5432の待受、PostgreSQLログを確認し、秘密値は出力しません。

## 6. FastAPIとAlembicの資格情報を分離

`/etc/mobile-order/backend.env`の`DATABASE_URL`はアプリ用ロールで、ホストを`127.0.0.1`にします。URL内の特殊文字はURLエンコードします。このファイルに`MIGRATION_DATABASE_URL`を入れないでください。FastAPIは本番環境でこの変数を検出すると起動を拒否します。

`migration.env.example`を置換した`/etc/mobile-order/migration.env`はroot所有0600にし、通常のsystemdサービスから読ませません。

```bash
sudo install -o root -g root -m 0600 REPLACE_WITH_RENDERED_MIGRATION_ENV /etc/mobile-order/migration.env
sudo stat -c '%U:%G %a %n' /etc/mobile-order/migration.env
```

Alembicは`MIGRATION_DATABASE_URL`を優先し、未設定なら開発互換のため`DATABASE_URL`へフォールバックします。本番マイグレーションは管理された一回限りの作業として実行します。

```bash
cd /opt/mobile-order/backend
sudo env ENV_FILE=/etc/mobile-order/migration.env /opt/mobile-order/backend/.venv/bin/alembic current
sudo env ENV_FILE=/etc/mobile-order/migration.env /opt/mobile-order/backend/.venv/bin/alembic upgrade head
```

環境ファイルの内容や`systemctl show --property=Environment`を共有端末へ出力しません。マイグレーション前後で`alembic current`、バックアップ、アプリ停止条件、ロールバック方法を確認します。スキーマのdowngradeがデータを失う可能性がある場合、復旧は確認済みバックアップから行います。

## 7. 権限と動作を検証

アプリ用ロールでSELECT/INSERT/UPDATE/DELETEとシーケンス採番が成功し、次の永久オブジェクトDDLが拒否されることを隔離したトランザクションまたは専用テストDBで確認します。

```sql
CREATE TABLE public.permission_probe (id integer);
ALTER TABLE public.tables ADD COLUMN permission_probe integer;
DROP TABLE public.tables;
```

本番データを使って破壊的テストをしません。マイグレーション用ロールでは`alembic current`が成功し、バックアップ済みの本番相当環境で5本を先頭から`upgrade head`できること、追加オブジェクトの所有者がマイグレーション用ロールであること、アプリ用ロールのDEFAULT PRIVILEGESが付くことを確認します。

FastAPIを再起動し、ヘルスチェック、認証、商品、注文、会計、WebSocketの回帰確認を行います。別ホストからEC2の5432へ接続できないこと、EC2上でも127.0.0.1以外のインターフェースで待受していないことを確認します。

## 8. 障害時の復旧

1. FastAPIを停止し、失敗後の変更を増やさない。
2. PostgreSQL管理者のpeer接続を維持したまま、ログと`pg_file_settings`/`pg_hba_file_rules`を確認する。
3. 接続制限が原因なら、バックアップした設定ファイルを復元し、構文確認後にreload/restartする。
4. 権限が原因なら、事前に記録した所有者・GRANTだけを管理者から戻す。ロールやデータを削除しない。
5. マイグレーションまたはデータ破損なら、アプリを停止したまま承認済みの復元手順で隔離復元を確認してから復旧する。
6. 旧設定へ戻した後も、5432をセキュリティグループやUFWで外部公開しない。

本番適用完了は、設定バックアップとDB復元試験、管理経路、ループバック制限、SCRAM、所有権、最小権限、FastAPI回帰、外部5432拒否がすべて確認できた時点です。
