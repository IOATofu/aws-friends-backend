import boto3
import asyncio
from .ec2 import get_latest_ec2_metrics
from .rds import get_latest_rds_metrics
from .alb import get_latest_alb_metrics
from .calc_state import calc_ec2, calc_rds, calc_alb


async def get_all_metrics_async():
    """
    EC2、RDS、ALBのメトリクスを非同期で並列取得します。
    """
    # 非同期タスクを作成
    tasks = [
        asyncio.to_thread(get_latest_ec2_metrics),
        asyncio.to_thread(get_latest_rds_metrics),
        asyncio.to_thread(get_latest_alb_metrics),
    ]

    # 並列実行して結果を取得
    ec2_metrics, rds_metrics, alb_metrics = await asyncio.gather(*tasks)

    return ec2_metrics, rds_metrics, alb_metrics


async def getInfo():
    metrics_data = []
    # セッションからリージョンを取得
    session = boto3.Session()
    region = session.region_name

    # STS クライアントを作成してアカウントIDを取得
    sts_client = boto3.client("sts")
    response = sts_client.get_caller_identity()
    account_id = response["Account"]

    # 非同期で全メトリクスを一気に取得（asyncio.runは使わない）
    ec2_metrics, rds_metrics, alb_metrics = await get_all_metrics_async()

    # EC2メトリクスの処理
    for metric in ec2_metrics:
        instance_id = metric["instance_id"]
        metrics_data.append(
            {
                "type": "ec2",
                "arn": f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}",
                "state": calc_ec2(metric["cpu_utilization"]),
            }
        )

    # RDSメトリクスの処理
    for metric in rds_metrics:
        db_name = metric["db_instance_identifier"]
        metrics_data.append(
            {
                "type": "rds",
                "arn": f"arn:aws:rds:{region}:{account_id}:db:{db_name}",
                "state": calc_rds(metric["metrics"]["cpu_utilization"]),
            }
        )

    # ALBメトリクスの処理
    for metric in alb_metrics:
        metrics_data.append(
            {
                "type": "alb",
                "arn": metric["load_balancer_arn"],
                "state": calc_alb(),
            }
        )
    return metrics_data


if __name__ == "__main__":
    print(getInfo())
