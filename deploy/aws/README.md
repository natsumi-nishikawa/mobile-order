# EC2 IAM role migration runbook

この手順はAWSへ適用する前にレビューしてください。JSON内の`REPLACE_WITH_*`はすべて置換必須であり、実値をリポジトリへ保存しません。

## 事前確認、バックアップ、復旧計画

変更前に次を記録します。秘密値そのものは記録・画面共有・ログ出力しません。

1. 対象のAWSアカウント、リージョン、EC2インスタンスID、S3バケット、Cognito User Poolを相互確認する。
2. EC2に現在関連付いているインスタンスプロファイル名と、そのポリシーをJSONで保存する。保存先はGit外かつアクセス制限された場所にする。
3. FastAPIのsystemdユニット名、`EnvironmentFile`のパス、起動ユーザー、再起動・ヘルスチェック手順を記録する。
4. 現在の`.env`をGit外のアクセス制限された場所へバックアップする。内容をターミナルへ表示しない。
5. IAMユーザーのアクセスキーID、状態、最終使用サービス・日時だけをIAMコンソールで記録する。シークレットキーは記録しない。
6. 商品画像のアップロード・表示・置換による旧画像削除と、Cognitoスタッフ管理の基準動作を確認する。

初回切り替えでは固定キーをすぐ削除しません。サービスの環境からだけ除外してIAMロールを検証し、問題があればバックアップ済み環境設定を戻してサービスを再起動するか、以前のインスタンスプロファイルへ戻します。復旧後はヘルスチェックと上記基準動作を再確認します。

## 1. EC2用IAMロールを作成する

1. IAMコンソールで **ロール**、**ロールを作成**を開く。
2. 信頼されたエンティティに **AWSのサービス**、ユースケースに **EC2**を選ぶ。
3. アプリ専用と分かる名前を付ける。他アプリや管理作業と共用しない。
4. 信頼ポリシーが`ec2-trust-policy.example.json`と同等で、`ec2.amazonaws.com`だけが引き受けられることを確認する。

コンソールでEC2ロールを作成すると、通常は対応するインスタンスプロファイルも作成されます。

## 2. 最小権限ポリシーを設定する

`ec2-app-permissions-policy.example.json`を作業用コピーへ複製し、次を実値に置換します。実値入りコピーはGitへ追加しません。

AWSコンソールまたはCLIへ入力する直前に、実際に適用するJSONコピーを共通プリフライトへ渡します。非0終了なら適用を中止します。JSON構文と未置換マーカーを検査し、値自体は表示しません。

```bash
python3 deploy/preflight/validate_deployment_config.py REPLACE_WITH_RENDERED_TRUST_POLICY REPLACE_WITH_RENDERED_PERMISSION_POLICY
```

リポジトリの`.example.json`はプレースホルダーを含むため検査失敗が正常であり、そのまま適用しません。

- `REPLACE_WITH_BUCKET_NAME`
- `REPLACE_WITH_REGION`
- `REPLACE_WITH_AWS_ACCOUNT_ID`
- `REPLACE_WITH_USER_POOL_ID`

IAMコンソールのJSONエディターで検証し、作成したEC2ロールだけへ付与します。次を確認します。

- S3は`products/*`の`GetObject`、`PutObject`、`DeleteObject`だけ。
- Cognitoは記載した8操作だけで、Resourceは1つのUser Pool ARNだけ。
- `s3:*`、`cognito-idp:*`、Resourceの`*`単独、AWS管理のFullAccessポリシーがない。
- `ListBucket`、バケット設定変更、ACL変更、IAM管理権限がない。

可能ならIAM Policy Simulatorで、許可対象と次の拒否対象を適用前に確認します。

- 対象バケットの`products/example.jpg`はS3の3操作を許可。
- 同じバケットの`private/example.jpg`と別バケットは拒否。
- 対象User Poolの8操作は許可。
- 別User Poolと、それ以外のCognito管理操作は拒否。

## 3. EC2へIAMロールを割り当てる

1. EC2コンソールで対象インスタンスを再確認する。
2. **アクション**、**セキュリティ**、**IAMロールを変更**を開く。
3. 作成したインスタンスプロファイルを選択し、更新する。
4. 既存ロールがある場合は、その権限を新ロールへ不用意に統合せず、必要性を確認してから置換する。

ロールの割り当てだけでは固定キーの優先利用は止まりません。手順5までサービスを切り替えないでください。

## 4. IMDSv2を必須にする

EC2コンソールで **アクション**、**インスタンスの設定**、**インスタンスメタデータオプションを変更**を開き、次を設定します。

- Instance Metadata Service: 有効
- Metadata version: V2 only / token required
- Metadata response hop limit: FastAPIをホスト上で直接動かす場合は1を基本とする
- Instance tags in metadata: 不要なら無効

コンテナ内で実行する構成へ変更する場合は、ホップ制限2が必要になることがあるため別途検証します。

## 5. EC2に固定キーが残っていないか確認する

boto3では、明示的なクライアント引数、環境変数、共有AWS設定などがEC2ロールより先に評価されます。少なくとも次を確認します。

- FastAPI用`.env`、systemdの`Environment`と`EnvironmentFile`
- サービスプロセスの環境変数名
- 起動ユーザーとrootの`~/.aws/credentials`、`~/.aws/config`
- `/etc/environment`、シェルプロファイル、User Data、デプロイスクリプト
- `AWS_PROFILE`、`AWS_SHARED_CREDENTIALS_FILE`、`AWS_CONFIG_FILE`

確認時に値を表示しません。実行中プロセスは、環境変数名だけを抽出します。

```bash
sudo sh -c 'tr "\0" "\n" < /proc/REPLACE_WITH_FASTAPI_PID/environ | cut -d= -f1 | grep -E "^(AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN|AWS_PROFILE|AWS_SHARED_CREDENTIALS_FILE|AWS_CONFIG_FILE)$" || true'
```

認証元はサービスと同じOSユーザーで確認します。`aws configure list`はキー値ではなく、認証元が`env`、共有ファイル、IAM roleのどれかを確認する目的だけに使います。コマンド出力をチケットや公開ログへ貼りません。

固定キーの行はバックアップ後にサービスが読む本番設定から削除し、systemdを再読込してFastAPIを再起動します。ローカルの`backend/.env`はこの作業では変更しません。

## 6. IAMロールによる認証を確認する

サービスと同じOSユーザーで次を実行します。結果にはアカウントIDとロールARNが含まれるため、公開ログへ貼りません。

```bash
aws sts get-caller-identity
aws configure list
```

確認条件：

- Caller identityが作成したEC2ロールのセッションである。
- 認証元が環境変数や共有credentialsファイルではない。
- FastAPI起動後、認証情報不足エラーが発生しない。

## 7. S3商品画像機能を確認する

管理画面からテスト用の画像を使い、次の順に確認します。

1. 画像をアップロードでき、キーが`products/`配下になる。
2. 顧客画面と管理画面で署名付きURLにより表示できる。
3. 画像を別画像へ置換し、旧オブジェクトが削除される。
4. テスト商品または画像を通常のアプリ操作で後片付けする。
5. CloudTrailやアプリログに認証情報が出ていないことを確認する。

IAM Policy Simulatorまたは専用の安全なテストオブジェクトで、同一バケットの`products/`外と別バケットへの操作が拒否されることも確認します。既存データを削除対象に使いません。

## 8. Cognitoスタッフ管理を確認する

本番利用者と区別できるテスト用メールアドレスを使い、管理画面から次を確認します。

1. staff一覧取得
2. staff作成とstaffグループ追加
3. 無効化と有効化
4. 仮パスワード再設定
5. テストstaff削除
6. 通常のスタッフ・管理者ログインと権限制御

IAM Policy Simulatorで別User Pool ARNへの同じ操作が拒否されることを確認します。実在する別環境の利用者を変更するテストは行いません。

## 9. S3の安全設定を確認する

S3コンソールで対象バケットの **アクセス許可**と**プロパティ**を開きます。

- BlockPublicAcls: 有効
- IgnorePublicAcls: 有効
- BlockPublicPolicy: 有効
- RestrictPublicBuckets: 有効
- Object Ownership: Bucket owner enforced（ACL無効）
- Bucket policy: 匿名Principalや公開許可がない
- Static website hosting: 無効
- Default encryption: SSE-S3

署名付きURLは非公開バケットのまま使用できます。SSE-KMSを選ぶ場合はKMS権限と費用が増えるため、このテンプレートをそのまま適用しません。

## 10. 固定アクセスキーの無効化・削除を判断する

次をすべて満たしてから旧キーを無効化します。

- FastAPIプロセスに固定AWS認証情報がない。
- `get-caller-identity`がEC2ロールを示す。
- S3のアップロード・表示・削除が成功する。
- Cognitoスタッフ管理の全操作が成功する。
- 再起動後も成功し、一時的な認証キャッシュに依存していない。
- IAMの最終使用情報とCloudTrailで、旧キーを使う別システムがない。
- 復旧手順と担当者が確認済み。

最初はIAMコンソールで旧キーを**無効化**し、監視期間中に問題がないことを確認します。問題があれば原因を確認したうえで一時的に再有効化できます。依存がないと確認できた後に削除します。漏えいが疑われるキーは監視期間を待たず、インシデント対応として直ちに無効化します。

## ローカル開発は別作業とする

このEC2移行ではローカルの`backend/.env`を変更しません。後続作業でIAM Identity Centerを設定し、`aws configure sso`、`aws sso login --profile REPLACE_WITH_PROFILE`による短期認証へ移行します。ローカル権限も専用の開発環境バケットとUser Poolに限定し、本番ロールを流用しません。

移行後はローカル`.env`から固定キーを削除し、必要なら`AWS_PROFILE`だけをローカルシェルで指定します。プロファイル名をアプリコードへハードコードしません。
