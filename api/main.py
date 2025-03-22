from fastapi import FastAPI, File, UploadFile, Form
from instance.alb import get_latest_alb_metrics
from instance.ec2 import get_latest_ec2_metrics
from instance.rds import get_latest_rds_metrics
import uvicorn

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.post("/chat")
async def chat(text: str = Form()):
    return {"message": "chat"}

@app.get("/instances")
async def get_instances():
    metrics_data = {}
    ec2_metrics = get_latest_ec2_metrics()
    for metric in ec2_metrics:
        if metric["cpu_utilization"] is not None:
            tmp = f"CPU: {metric['cpu_utilization']:.2f}% at {metric['timestamp']}"
        else:
            tmp = f"CPUデータが見つかりません"
        metrics_data[metric["instance_id"]] = tmp
    return metrics_data

@app.post("/instances/profile")
async def instance_profile(text: str = Form()):
    return {"message": "instances"}

@app.get("/load-state")
async def get_loadstate():
    return {"message": "load-state"}


@app.put("/load-state")
async def put_loadstate(text: str = Form()):
    return {"message": "load-state"}
