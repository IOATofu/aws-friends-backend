import boto3
import json
import time
import os


# Bedrock Runtimeクライアントを初期化します
bedrock_client = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-west-2'
)

# モデルIDを直接指定します
model_id = 'anthropic.claude-3-7-sonnet-20250219-v1:0'  # デフォルトのモデルID
with open('/api/chat/prompts/base_head.txt', 'r', encoding='utf-8') as f:
    base_head_prompt = f.read()

with open('/api/chat/prompts/base_foot.txt', 'r', encoding='utf-8') as f:
    base_foot_prompt = f.read()

with open('/api/chat/prompts/alb.txt', 'r', encoding='utf-8') as f:
    alb_prompt = f.read()

with open('/api/chat/prompts/ec2.txt', 'r', encoding='utf-8') as f:
    ec2_prompt = f.read()

with open('/api/chat/prompts/rds.txt', 'r', encoding='utf-8') as f:
    rds_prompt = f.read()

class Chat:
    def __init__(self, debug=False):
        self.history = []
        self.debug = debug  # デバッグモードのフラグ

    def add_message(self, role, content):
        self.history.append({'role': role, 'content': content})

    def add_messages(self, messages):
        """
        複数のメッセージを一度に追加します。
        :param messages: [{'role': 'user', 'content': 'message'}, ...] の形式のリスト
        """
        for message in messages:
            self.add_message(message['role'], message['content'])

    def display_history(self):
        for message in self.history:
            print(f"{message['role']}: {message['content']}")

    def get_llm_response(self, model_id):
        start_time = time.time()  # 開始時間を記録
        try:
            if self.debug:
                print(f"モデルID: {model_id}")  # デバッグ用
                print(f"メッセージ: {self.history}")  # デバッグ用
                print(f"メッセージの数: {len(self.history)}")  # デバッグ用

            if not self.history:
                if self.debug:
                    print("メッセージリストが空です。")
                return None

            if model_id.startswith('anthropic.'):
                payload = json.dumps({
                    'messages': self.history,
                    'max_tokens': 200,
                    'anthropic_version': 'bedrock-2023-05-31'  # 必要なバージョンを指定
                })
                if self.debug:
                    print(f"ペイロード（Anthropic）: {payload}")  # デバッグ用
            elif model_id.startswith('amazon.titan-'):
                if len(self.history) > 0:
                    payload = json.dumps({
                        'prompt': self.history[-1]['content'],
                        'maxTokens': 200,
                        'temperature': 0.5
                    })
                    if self.debug:
                        print(f"ペイロード（Amazon Titan）: {payload}")  # デバッグ用
                else:
                    if self.debug:
                        print("Amazon Titan用のメッセージが不足しています。")
                    return None
            else:
                if self.debug:
                    print(f"サポートされていないモデルIDです: {model_id}")
                return None

            response = bedrock_client.invoke_model(
                modelId=model_id,
                body=payload,
                contentType='application/json',
                accept='application/json'
            )
            if self.debug:
                print(f"レスポンス: {response}")  # デバッグ用

            response_body = json.loads(response['body'].read())
            if self.debug:
                print(f"レスポンスボディ: {response_body}")  # デバッグ用

            if model_id.startswith('anthropic.'):
                return response_body['content'][0]['text']
            elif model_id.startswith('amazon.titan-'):
                return response_body['results']

        except Exception as e:
            if self.debug:
                print(f"モデルの呼び出し中にエラーが発生しました: {e}")
            return None
        finally:
            end_time = time.time()  # 終了時間を記録
            if self.debug:
                print(f"処理時間: {end_time - start_time} 秒")  # 処理時間を表示


class monitorAgent(Chat):
    def __init__(self, debug=False):
        super().__init__(debug)
        self.history.append(
            {'role': 'user', 'content': 'あなたは監視エージェントです。ユーザーの発言(二重角括弧で囲われたもの)を監視し、不適切な内容を検出した場合は警告を出します。'})

    def check_message(self, message):
        self.history.append(
            {'role': 'user', 'content': f"ユーザーの発言: [[{message}]] 不適切な内容があるかどうかを判断してください。ブロックする場合はFalseを返し、許可する場合はTrueを返してください。"})
        check_result_message = self.get_llm_response(model_id)
        self.history.append(
            {'role': 'assistant', 'content': check_result_message})
        # 簡単な不適切な内容のチェック（例: 特定のキーワードを含むかどうか）
        inappropriate_keywords = ['False']
        for keyword in inappropriate_keywords:
            if keyword in check_result_message:
                if self.debug:
                    print(f"不適切な内容が検出されました: {check_result_message}")
                return False, check_result_message
        return True, check_result_message

    def get_llm_response(self, model_id):
        return super().get_llm_response(model_id)


class Character(Chat):
    def __init__(self, prompt, debug=False):
        super().__init__(debug)
        self.history.append(
            {'role': 'user', 'content': prompt})

    def talk(self, user_message):
        self.history.append(
            {'role': 'user', 'content': f"User: {user_message}"})
        llm_response = self.get_llm_response(model_id)
        self.history.append(
            {'role': 'assistant', 'content': llm_response})
        return llm_response

def get_response_from_json(conversation_json, model_id="anthropic.claude-3-5-haiku-20241022-v1:0", debug=False):
    """
    会話ログのJSONを受け取り、LLMにリクエストして結果を返します。
    """
    # Chatクラスのインスタンスを作成
    chat_instance = Chat(debug=debug)

    # JSONから会話ログをchat_instanceのhistoryに追加
    try:
        for entry in conversation_json:
            chat_instance.add_message(entry['role'], entry['message'])
    except Exception as e:
        print(f"エラーが発生しました: {e}\n{conversation_json}")
        return None

    # LLMにリクエストを送信し、応答を取得
    return chat_instance.get_llm_response(model_id)




def character_chat(arn,conversation_json,metrics, model_id="anthropic.claude-3-5-sonnet-20241022-v2:0", debug=False):
    if "elasticloadbalancing" in arn:    
        prompt = base_head_prompt + alb_prompt + base_foot_prompt
    elif "ec2" in arn:
        prompt = base_head_prompt + ec2_prompt + base_foot_prompt
    elif "rds" in arn:
        prompt = base_head_prompt + rds_prompt + base_foot_prompt
    else:
        raise Exception(f"character_chat: サポートされていないARNです: {arn}")
    conversation_log=[{'role':x['role'],'content':x['message']} for x in conversation_json]
    chat_instance = Character(prompt=prompt, debug=debug)
    if conversation_log:
        chat_instance.add_messages(conversation_log)
    chat_instance.add_message('user',"-"*10+f"metrics_data: {metrics}\n\nこのメトリクスデータは会話に必要な時に利用してください"+"-"*10)
    return arn,chat_instance.get_llm_response(model_id)