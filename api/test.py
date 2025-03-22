import boto3
import datetime
from instance.utils import format_bytes
from instance.rds import get_latest_rds_metrics

# RDSインスタンスの最新メトリクスを取得
metrics = get_latest_rds_metrics()
for metric in metrics:
    print(f"RDS Instance: {metric['db_instance_identifier']}")
    print(f"CPU Usage: {metric['metrics']['cpu_utilization']}%")
    print(f"Free Storage: {format_bytes(metric['metrics']['free_storage_space'])}")
