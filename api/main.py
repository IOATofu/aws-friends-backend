from fastapi import FastAPI, File, UploadFile, Form, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from instance import get_alb_list, getInfo, get_instance_costs
import uvicorn
import logging
import asyncio

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
    # モックレスポンスを返す
    return {
        "arn": arn,
        "return": {
            "role": "assistant",
            "message": "こんにちは！！今現在異常は無いよ！",
        },
    }


@app.post("/talk")
async def talk(arn: str = Form(), log: list = Form()):
    # モックレスポンスを返す
    return {
        "arn": arn,
        "return": {
            "role": "assistant",
            "message": "元気だよ！！今はだいぶ余裕があるみたい！",
        },
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
