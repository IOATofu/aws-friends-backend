from fastapi import FastAPI, File, UploadFile, Form
from instance.get_instaces_info import getInfo
from instance.alb import get_alb_list
import uvicorn

app = FastAPI()


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.post("/chat")
async def chat(arn: str = Form()):
    # モックレスポンスを返す
    return {
        "arn": arn,
        "return": {
            "role": "assistant",
            "message": "こんにちは！！今現在異常は無いよ！"
        }
    }

@app.post("/talk")
async def talk(arn: str = Form(), log: list = Form()):
    # モックレスポンスを返す
    return {
        "arn": arn,
        "return": {
            "role": "assistant",
            "message": "元気だよ！！今はだいぶ余裕があるみたい！"
        }
    }

@app.get("/instances")
async def get_instances():
    return getInfo()


@app.get("/alb")
async def get_albs():
    """ALBの一覧を取得するエンドポイント"""
    return get_alb_list()


@app.get("/load-state")
async def get_loadstate():
    return {
        "arn": "(arn)",
        "level": "low",
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="debug")
