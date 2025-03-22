from fastapi import FastAPI
import getAws
import uvicorn

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/getAwsInfo")
async def getAwsInfo():
    return getAws.getInfo()

def debug():
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="debug")

if __name__ == "__main__":
    debug()
