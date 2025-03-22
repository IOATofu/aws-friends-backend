from fastapi import FastAPI
import getAws as getAws
import uvicorn

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/getAwsInfo")
async def getAwsInfo():
    return getAws.getInfo()
