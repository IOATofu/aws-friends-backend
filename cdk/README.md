# AWD CDK

AWDのリソースはCDKで管理します。
コンソールで直接編集せず、CDKで変更してください。

## 使い方
事前にAWS CDKをインストールしてください。
`npm install -g aws-cdk`

- デプロイする
`cdk deploy <Stack名>`
- 削除する
`cdk destroy <Stack名>`
- デプロイの差分を確認する
`cdk diff <Stack名>`
- CloudFormationのテンプレートを確認する
`cdk synth <Stack名>`

## 環境変数
`ProgateHackathonPipelineStack`をデプロイする際は`.env.example`を参考に`.env`を作成してください。
- DISCORD_WEBHOOK_URL
通知先のDiscordのWebhook URL
- DISCORD_MENTION_USER_ID
エラーが発生した際にメンションを飛ばすユーザーのID

