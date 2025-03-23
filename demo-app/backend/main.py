from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db, engine
import models
import httpx
import json
from pydantic import BaseModel
import uuid

# データベーステーブルの作成
models.Base.metadata.create_all(bind=engine)

app = FastAPI()


class TalkRequest(BaseModel):
    arn: str
    session_id: str | None = None
    message: str


class TalkResponse(BaseModel):
    message: str
    session_id: str


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.post("/talk", response_model=TalkResponse)
async def talk(request: TalkRequest, db: Session = Depends(get_db)):
    # セッションIDがない場合は新規作成
    session_id = request.session_id or str(uuid.uuid4())

    # 会話履歴の取得
    conversation = None
    if request.session_id:
        conversation = (
            db.query(models.Conversation)
            .filter(models.Conversation.session_id == session_id)
            .first()
        )

    conversation_history = (
        json.loads(conversation.conversation_history) if conversation else []
    )

    # AWS Friendsへのリクエストデータ準備
    aws_friends_data = {
        "arn": request.arn,
        "message": request.message,
        "conversation_history": conversation_history,
    }

    # AWS Friendsへリクエスト
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://aws-friends.k1h.dev/talk", json=aws_friends_data
        )
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code, detail="AWS Friends API error"
            )

        aws_friends_response = response.json()

    # 会話履歴の更新
    conversation_history.append({"role": "user", "content": request.message})
    conversation_history.append(
        {"role": "assistant", "content": aws_friends_response["message"]}
    )

    # データベースの更新
    if conversation:
        conversation.conversation_history = json.dumps(conversation_history)
        db.commit()
    else:
        new_conversation = models.Conversation(
            session_id=session_id, conversation_history=json.dumps(conversation_history)
        )
        db.add(new_conversation)
        db.commit()

    return {"message": aws_friends_response["message"], "session_id": session_id}
