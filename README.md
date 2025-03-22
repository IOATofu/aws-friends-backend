# Progate Hackathon Backend

## uvの使い方
1. 環境の作成
`.venv`以下に作成されます
```
$ uv venv
```
2. 環境の有効化
```
$ source .venv/bin/activate # Mac/Linux
$ .venv\Scripts\activate # Windows
```
3. パッケージの追加
```
# uv pip install <package>
```


## AWS CodeBuildの環境変数更新

```bash
aws codebuild update-project --name progate-hackathon-backend \
  --environment-variables name=AWS_DEFAULT_REGION,value=us-west-2,type=PLAINTEXT \
                         name=AWS_ACCOUNT_ID,value=520070710501,type=PLAINTEXT \
                         name=IMAGE_REPO_NAME,value=progate-hackathon-api,type=PLAINTEXT
```
