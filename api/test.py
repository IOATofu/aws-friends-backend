import boto3
import datetime
from instance.get_instaces_info import getInfo

# RDSインスタンスの最新メトリクスを取得
print(getInfo())