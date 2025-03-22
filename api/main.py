from fastapi import FastAPI, File, UploadFile, Form, Query, Body
from instance import get_alb_list, getInfo, get_instance_costs, get_latest_ec2_metrics, get_latest_rds_metrics, get_latest_alb_metrics
from chat import get_response_from_json ,character_chat
import uvicorn
import json
app = FastAPI()

def get_metrics_by_arn(arn: str):
    if "alb" in arn:
        return get_latest_alb_metrics()
    elif "ec2" in arn:
        return get_latest_ec2_metrics()
    elif "rdb" in arn:
        return get_latest_rds_metrics()
    else:
        raise Exception(f"サポートされていないARNです: {arn}")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/chat")
async def chat(arn: str = Form()):
    
    metrics = get_metrics_by_arn(arn)
    
    arn,message = character_chat(arn,[],metrics)
    # モックレスポンスを返す
    return {
        "arn": arn,
        "return": {
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
            "return": {
                "role": "assistant",
                "message": message,
            },
        }
    except Exception as e:
        # エラーハンドリング
        return {
            "error": "An error occurred while processing the chat log.",
            "details": str(e)+"\n"+str(log)
        }



@app.get("/instances")
async def get_instances():
    """
    EC2、RDS、ALBインスタンスの情報を取得します。
    非同期処理で高速化されています。
    """
    return await getInfo()


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
