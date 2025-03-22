import boto3
import datetime
from instance.get_instaces_info import getInfo
import asyncio

# RDSインスタンスの最新メトリクスを取得
async def main():
    print(await getInfo())

if __name__ == "__main__":
    asyncio.run(main())
