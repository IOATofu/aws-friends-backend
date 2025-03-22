from fastapi import FastAPI, File, UploadFile, Form, Query
from instance.get_instaces_info import getInfo
from instance.alb import get_alb_list
from instance.cost import get_instance_costs
import uvicorn

app = FastAPI()


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.post("/chat")
async def chat(text: str = Form()):
    return {"message": "chat"}


@app.get("/instances")
async def get_instances():
    return getInfo()


@app.post("/instances/profile")
async def instance_profile(text: str = Form()):
    return {"name": "Sample Instance Name"}


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


@app.put("/load-state")
async def put_loadstate(text: str = Form()):
    return {"message": "load-state"}


@app.get("/costs")
async def get_costs(days: int = Query(default=30, ge=1, le=365)):
    """
    インスタンスごとの課金情報を取得します。

    Args:
        days (int): 取得する期間（日数）。1-365の範囲で指定可能。デフォルトは30日。

    Returns:
        List[Dict]: インスタンスごとの課金情報
    """
    return get_instance_costs(days)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="debug")
