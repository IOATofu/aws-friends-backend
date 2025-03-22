from fastapi import FastAPI, File, UploadFile, Form, Query, Body, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from instance import (
    get_alb_list,
    getInfo,
    get_instance_costs,
    get_latest_ec2_metrics,
    get_latest_rds_metrics,
    get_latest_alb_metrics,
)
from chat import get_response_from_json, character_chat
import logging
import asyncio
import uvicorn
import json

app = FastAPI()


def get_metrics_by_arn(arn: str):
    if "elasticloadbalancing" in arn:
        return get_latest_alb_metrics()
    elif "ec2" in arn:
        return get_latest_ec2_metrics()
    elif "rds" in arn:
        return get_latest_rds_metrics()
    else:
        raise Exception(f"get_metrics_by_arn: サポートされていないARNです: {arn}")



# ロガーの設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORSミドルウェアを追加
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本番環境では適切なオリジンに制限することをお勧めします
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# キャッシュヘッダーを追加するミドルウェア
class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # GETリクエストのみにキャッシュヘッダーを追加
        if request.method == "GET":
            # /healthエンドポイントはキャッシュしない
            if request.url.path == "/health":
                response.headers["Cache-Control"] = (
                    "no-store, no-cache, must-revalidate, max-age=0"
                )
            else:
                # その他のGETエンドポイントは60秒間キャッシュ
                response.headers["Cache-Control"] = "public, max-age=60"
        else:
            # POSTなどの変更を伴うリクエストはキャッシュしない
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, max-age=0"
            )

        return response


app.add_middleware(CacheControlMiddleware)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/chat")
async def chat(arn: str = Form()):

    metrics = get_metrics_by_arn(arn)

    arn, message = character_chat(arn, [], metrics)
    # モックレスポンスを返す
    return {
        "arn": arn,
        "return_message": {
            "role": "assistant",
            "message": message,
        },
    }


@app.post("/talk")
async def talk(data: dict = Body(...)):
    # JSONデータを受け取る
    try:
        arn = data.get("arn")
        log = data.get("log")
        metrics = get_metrics_by_arn(arn)
        arn, message = character_chat(arn, log, metrics)
        return {
            "arn": arn,
            "return_message": {
                "role": "assistant",
                "message": message,
            },
        }
    except Exception as e:
        # エラーハンドリング
        return {
            "error": "An error occurred while processing the chat log.",
            "details": str(e) + "\n" + str(log),
        }


@app.get("/instances")
async def get_instances():
    """
    EC2、RDS、ALBインスタンスの情報を取得します。
    非同期処理で高速化されています。
    """
    logger.info("GET /instances リクエストを受信")
    start_time = asyncio.get_event_loop().time()

    try:
        result = await getInfo()
        end_time = asyncio.get_event_loop().time()
        logger.info(
            f"/instances リクエスト処理完了 (所要時間: {end_time - start_time:.2f}秒)"
        )
        return result
    except Exception as e:
        logger.error(f"/instances エンドポイントでエラーが発生: {str(e)}")
        raise


@app.get("/alb")
async def get_albs():
    """ALBの一覧を取得するエンドポイント"""
    return get_alb_list()


@app.get("/costs")
async def get_costs(days: int = Query(default=30, ge=1, le=365)):
    """
    インスタンスごとの課金情報を取得します。

    Args:
        days (int): 取得する期間（日数）。1-365の範囲で指定可能。デフォルトは30日。

    Returns:
        List[Dict]: インスタンスごとの課金情報
    """
    return await get_instance_costs(days)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="debug")
