from fastapi import FastAPI, File, UploadFile, Form
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
    return {"message": "instances"}

@app.post("/instances/profile")
async def instance_profile(text: str = Form()):
    return {"message": "instances"}

@app.get("/load-state")
async def get_loadstate():
    return {"message": "load-state"}


@app.put("/load-state")
async def put_loadstate(text: str = Form()):
    return {"message": "load-state"}
