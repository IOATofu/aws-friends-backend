import boto3
import datetime
from instance.utils import format_bytes
from instance.rds import get_latest_rds_metrics
from instance.ec2 import get_latest_ec2_metrics

# RDSインスタンスの最新メトリクスを取得
metrics_data = {}
ec2_metrics = get_latest_ec2_metrics()
for metric in ec2_metrics:
    if metric["cpu_utilization"] is not None:
        tmp = f"CPU: {metric['cpu_utilization']:.2f}% at {metric['timestamp']}"
    else:
        tmp = f"CPUデータが見つかりません"
    metrics_data[metric["instance_id"]] = tmp
print(metrics_data)