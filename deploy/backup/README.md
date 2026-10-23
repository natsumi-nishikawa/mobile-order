# PostgreSQLバックアップ・復元・ログ運用手順

この手順はUbuntu 24.04上の同一EC2構成向けです。テンプレートの作成だけでは復旧可能性は証明されません。初回バックアップを別DBへ復元し、定期的に復元試験を完了して初めて「復旧可能と検証済み」と判断します。`REPLACE_WITH_*`は実機で置換し、置換済みファイルをGitへ追加しません。

## 1. 方式と必要パッケージ

- PostgreSQLクライアントの`pg_dump`/`pg_restore`。サーバーのメジャーバージョン以上の互換クライアントを選びます。
- AWS CLI v2。固定アクセスキーではなくEC2 IAMロールを利用します。
- util-linuxの`flock`、GNU coreutils。
- `pg_dump -Fc`によるカスタム形式の日次バックアップ。
- ローカルの保護された一時領域で検査後、非公開の専用S3バケットへ転送。
- systemd timerで毎日03:20、最大30分のランダム遅延、再起動時の取りこぼし実行を有効化。

商品画像バケットとバックアップバケットは分離します。バックアップバケットはパブリックアクセスブロックを4項目すべて有効、Object OwnershipはBucket owner enforced、Webサイト公開は無効、デフォルト暗号化はSSE-S3とします。SSE-KMSは追加権限・費用・復旧時の鍵依存が増えるため、この小規模デモの初期案では使用しません。

## 2. 専用DBロール

`deploy/postgresql/create_backup_role.sql.example`で4番目の専用ロールを作ります。これは既存の管理者、マイグレーション、アプリ実行ロールを置き換えません。

バックアップロールに付与するのは次だけです。

- 対象DBへのCONNECT
- `public`スキーマへのUSAGE
- 対象スキーマの全テーブルへのSELECT
- 全シーケンスへのSELECT
- マイグレーションロールが将来作るテーブル・シーケンスへのDEFAULT PRIVILEGES

SUPERUSER、CREATEDB、CREATEROLE、レプリケーション、RLS迂回、CREATE、書込み権限は与えません。large object、別スキーマ、拡張機能固有オブジェクトが将来追加された場合は、実物を棚卸しして必要な読取りだけを追加します。`pg_read_all_data`は対象DB外や追加スキーマまで広がり得るため使用しません。

SCRAMパスワードは管理者の対話型psqlで`\password REPLACE_WITH_BACKUP_ROLE`として設定します。`pg_hba.conf`は更新済みテンプレートどおり、このロールのloopback TCPだけを許可します。

## 3. S3とIAM

`backup-writer-policy.example.json`はEC2 IAMロールへ追加するバックアップ用ポリシーです。`postgresql/*`への`PutObject`と、転送後のHEAD検証に必要な`GetObject`だけを許可します。List/Delete、`s3:*`、商品画像バケット、別バケットへの権限はありません。

`restore-reader-policy.example.json`は承認された復元担当主体用です。GetObjectだけです。同じEC2ロールへ常時追加する必要はありません。実際にはインスタンスロールの認証情報を同一EC2上の全プロセスが取得できるため、OSユーザー分離だけをIAM境界とは見なしません。バックアップスクリプトへの誤操作は権限とsystemd hardeningの両方で抑えます。

バージョニングから特定世代を回収する管理担当には、作業時に限り`ListBucketVersions`と`GetObjectVersion`が必要になる場合があります。通常バックアップポリシーへは追加しません。

## 4. 保持方針

スクリプトはUTC基準で次のキーを作ります。

- 毎回: `postgresql/daily/postgresql-YYYYMMDDTHHMMSSZ.dump`
- UTC日曜日: 同じダンプを`postgresql/weekly/`にも保存
- UTC各月1日: 同じダンプを`postgresql/monthly/`にも保存

Lifecycleテンプレートはdailyを7日、weeklyを28日、monthlyを92日で削除対象にします。正常に毎回取得できる定常状態で、日次7回、週次4回、月次約3回を意図しています。ただしS3 Lifecycleは「世代数」ではなくオブジェクト経過日数で判定し、削除は非同期です。月長の差や失敗日、削除処理の遅延により一時的な件数は一致しません。厳密な件数制御にはList/Delete権限を持つ追加処理が必要になるため、初期構成では採用しません。

Versioningは誤削除・同一キー上書きへの防御として有効です。固有キーとDeleteなしIAMにより通常の上書き・削除リスクは低いものの、管理者操作への備えとして有効化を推奨します。非現行版にもLifecycleを設定しています。バージョニング、複製prefix、Lifecycle削除待ちはS3保存量とリクエスト料金を増やします。初回取得後に実サイズから月額を再見積もりします。

## 5. OSユーザー、秘密ファイル、systemdの設置

IAM/Lifecycle JSONの適用前、およびenv、pgpass、service、timerの配置前に、実際に使用するレンダリング済みファイルをすべて検査します。非0終了ならAWS適用とファイル配置を中止します。値は表示されません。`.example`ファイルは未置換のままGit管理でき、そのまま検査すれば失敗することが正常です。

```bash
python3 deploy/preflight/validate_deployment_config.py REPLACE_WITH_RENDERED_BACKUP_POLICY REPLACE_WITH_RENDERED_RESTORE_POLICY REPLACE_WITH_RENDERED_LIFECYCLE_JSON REPLACE_WITH_RENDERED_BACKUP_ENV REPLACE_WITH_RENDERED_PGPASS REPLACE_WITH_RENDERED_BACKUP_SERVICE REPLACE_WITH_RENDERED_BACKUP_TIMER
```

```bash
sudo adduser --system --group --home /var/lib/mobile-order-backup --shell /usr/sbin/nologin mobile-order-backup
sudo install -d -o root -g root -m 0750 /etc/mobile-order
sudo install -d -o mobile-order-backup -g mobile-order-backup -m 0700 /var/lib/mobile-order-backup
sudo install -o root -g root -m 0600 REPLACE_WITH_RENDERED_BACKUP_ENV /etc/mobile-order/backup.env
sudo install -o mobile-order-backup -g mobile-order-backup -m 0600 REPLACE_WITH_RENDERED_PGPASS /var/lib/mobile-order-backup/.pgpass
sudo install -o root -g root -m 0755 deploy/backup/mobile-order-postgresql-backup /usr/local/sbin/mobile-order-postgresql-backup
sudo install -o root -g root -m 0644 deploy/backup/mobile-order-postgresql-backup.service.example /etc/systemd/system/mobile-order-postgresql-backup.service
sudo install -o root -g root -m 0644 deploy/backup/mobile-order-postgresql-backup.timer.example /etc/systemd/system/mobile-order-postgresql-backup.timer
```

`backup.env`にはDBパスワードやAWSキーを置きません。DBパスワードはバックアップOSユーザーだけが読める`.pgpass`に置きます。AWSはIAMロールの一時資格情報を標準認証チェーンで取得します。ファイル内容を`cat`、`systemctl show --property=Environment`、シェル引数へ出力しません。

検証後に有効化します。

```bash
sudo systemd-analyze verify /etc/systemd/system/mobile-order-postgresql-backup.service /etc/systemd/system/mobile-order-postgresql-backup.timer
sudo systemctl daemon-reload
sudo systemctl start mobile-order-postgresql-backup.service
sudo systemctl status mobile-order-postgresql-backup.service --no-pager
sudo journalctl -u mobile-order-postgresql-backup.service -n 100 --no-pager
sudo systemctl enable --now mobile-order-postgresql-backup.timer
systemctl list-timers mobile-order-postgresql-backup.timer
```

スクリプトは`set -Eeuo pipefail`、排他`flock`、0700一時ディレクトリ、終了時削除を使います。pg_dump終了、非空、`pg_restore --list`、ローカルSHA-256、S3 PUT、HEAD後のサイズ・SHA-256メタデータがすべて成功した場合だけ成功終了します。途中失敗は非0終了となりjournaldへ残ります。秘密値やオブジェクトキーはログ出力しません。

失敗後は原因を直し、次で手動再実行します。既に実行中なら排他ロックで失敗します。

```bash
sudo systemctl start mobile-order-postgresql-backup.service
sudo systemctl show mobile-order-postgresql-backup.service -p Result -p ExecMainStatus
```

## 6. 初回バックアップ確認

IAMロール、バケット、DB権限を適用後、タイマー有効化前に手動実行します。

1. systemdの終了コードが0であること。
2. journalに開始、検証済み保存区分、完了があること。秘密がないこと。
3. S3コンソールで対象prefix、サイズ、SSE-S3、非公開、SHA-256メタデータを確認すること。
4. LifecycleとVersioning状態を確認すること。
5. 後述の別DB復元試験を完了すること。

`aws sts get-caller-identity`等の結果は共有ログへ貼らず、固定キー由来でないことだけ確認します。既存の商品画像操作も回帰確認します。

## 7. 安全な復元試験

復元は自動化せず、作業者が対象を確認して隔離DBへ実施します。以下のプレースホルダーが残るコマンドは実行しません。本番DB名と同じ名前を復元先に指定しません。

1. S3コンソールまたは承認済み読取り主体で、日付、prefix、サイズ、暗号化、メタデータを確認する。
2. 復元対象キーを別担当者と照合する。
3. 0700の一時ディレクトリへダウンロードし、HEADのサイズ・SHA-256と再照合する。
4. `pg_restore --list`を実行し、終了コードと内容を確認する。
5. 本番接続文字列をシェルから除き、`REPLACE_WITH_ISOLATED_RESTORE_DB`が存在しないことを確認する。
6. 管理者が隔離DBを作成し、ネットワーク公開せず、復元用の所有者を設定する。
7. `pg_restore --exit-on-error --no-owner --no-privileges --dbname=REPLACE_WITH_ISOLATED_RESTORE_DB REPLACE_WITH_DOWNLOADED_DUMP`を実行する。
8. 終了コード0、テーブル、シーケンス、主キー・外部キー・CHECK制約・索引を確認する。
9. `SELECT version_num FROM alembic_version;`を確認し、リリースの期待revisionと照合する。
10. 事前記録した主要テーブル件数と比較する。個人情報や注文内容をログへ出さない。
11. 開始・終了時刻、ダンプサイズ、復元時間、検証結果を記録する。
12. 承認後、接続先を再確認して隔離テストDBだけを削除し、ダウンロードファイルを安全に削除する。

失敗時はエラー終了位置、PostgreSQLとディスク容量、クライアント互換性、必要拡張、所有者を確認します。本番DBへ上書きして回避しません。修正後は新しい隔離DBで先頭からやり直します。復元試験未完了のバックアップは「取得済み」であっても「復旧検証済み」ではありません。

## 8. 負荷と容量

t3.microはCPUクレジット、メモリ、EBS容量が小さいため、利用の少ない時間帯に単一ジョブで実行します。serviceはNice、低I/O優先度、CPU 25%、Memory 256MB上限を設定しています。最初の実行ではAPI応答、WebSocket、DBロック、CPUクレジット、空き容量を監視します。ダンプ最大サイズの少なくとも2倍程度の空き領域を確保し、容量不足なら開始時間・上限を再検討します。大容量化してAWS CLIの単一PUT上限に近づく前にマルチパート方式を再設計します。

## 9. ログ運用

### Nginx

Nginxテンプレートはquery string、request body、Referer、Cookie、Authorizationなどのヘッダーを記録しない専用形式を使います。`$request`ではなくmethod、`$uri`、protocolだけを記録するため、Cognito認可コードやS3署名付きURLのqueryを避けます。アクセス・エラーを14日、20MB上限目安でローテーションするテンプレートがあります。Nginxのerror logは書式を完全には制御できず、障害内容によってリクエスト情報が含まれる可能性があるためレベルを`error`へ絞り、ファイル権限を制限し、外部へそのまま共有しません。

### FastAPI・バックアップ

systemd/journaldへ標準出力・標準エラーを記録します。Uvicorn標準アクセスログはqueryを含み得るため本番unitでは無効化し、アクセス記録はNginxの安全な形式へ一本化します。アプリケーションエラーと起動・停止ログはjournaldへ残します。JWT、Cookie、Authorization、DB URL、パスワード、AWS認証情報、認可コード、署名付きURLを追加ログへ出しません。journald drop-in案は永続ログ200MB、ランタイム50MB、14日を上限にします。これはシステム全体へ影響するため、現在値とディスク容量を確認してから適用します。

### PostgreSQL

Ubuntuの`postgresql-common`標準ログと既存`/etc/logrotate.d/postgresql-common`を優先します。重複するlogrotate規則は設置しません。SQL全文・実行時間・バインド値の常時記録は無効とし、対応バージョンではパラメータ値長を0にします。提供したlogrotateは標準規則がない場合だけ使います。

ローテーション確認は各設定のdry-run/forceを保守時間帯に行い、ローテーション前後へ安全なテストアクセスまたは既知の非機密イベントを発生させ、新旧ファイルまたはjournalへ継続記録されることを確認します。Nginxは`nginx -t`後、PostgreSQLは設定互換性確認後に行います。

調査は次を基本とし、秘密値の検索結果そのものをチケットへ貼りません。

```bash
sudo journalctl -u mobile-order-api.service --since today
sudo journalctl -u mobile-order-postgresql-backup.service --since today
sudo tail -n 100 /var/log/nginx/mobile-order-error.log
sudo tail -n 100 /var/log/postgresql/REPLACE_WITH_LOG_FILE
df -h
journalctl --disk-usage
```

## 10. ロールバックとAWS費用

タイマー障害時は`systemctl disable --now mobile-order-postgresql-backup.timer`で新規実行だけを止め、既存S3バックアップを削除しません。以前のunit、script、環境ファイルメタデータ、IAMポリシーを保管し、原因修正後に手動バックアップと復元試験をやり直します。

S3には保存容量、PUT/GET、Lifecycle、Versioningの非現行版に料金が発生します。小規模DBでは一般に小額ですが無料とは限りません。週次・月次は同じダンプを複製するため、その分の保存量が増えます。S3 Inventory、CloudTrailデータイベント、別リージョン複製、AWS Backup、KMSを追加する場合も追加費用を確認します。初期構成ではこれら有料機能を必須にしません。
