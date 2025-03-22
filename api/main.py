from fastapi import FastAPI, File, UploadFile, Form
from instance.get_instaces_info import getInfo
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


@app.get("/load-state")
async def get_loadstate():
    return {
        "arn": "(arn)",
        "level": "low",
    }


@app.put("/load-state")
async def put_loadstate(text: str = Form()):
    return {"message": "load-state"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="debug")
