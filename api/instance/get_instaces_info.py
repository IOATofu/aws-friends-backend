import boto3
import asyncio
from .ec2 import get_latest_ec2_metrics
from .rds import get_latest_rds_metrics
from .alb import get_latest_alb_metrics
from .calc_state import calc_ec2, calc_rds, calc_alb
from .cost import estimate_realtime_cost_by_arn


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

async def get_cost_dict():
    return_dict = {}
    tmp_dict = await estimate_realtime_cost_by_arn()
    for tmp in tmp_dict:
        return_dict[tmp["instance_arn"]] = tmp["cost"]
    return return_dict

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
    cost_dict = await get_cost_dict()

    # EC2メトリクスの処理
    for metric in ec2_metrics:
        instance_id = metric["instance_id"]
        arn = f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}"
        metrics_data.append(
            {
                "type": "ec2",
                "arn": arn,
                "state": calc_ec2(metric["cpu_utilization"]),
                "cost": cost_dict[arn],
            }
        )

    # RDSメトリクスの処理
    for metric in rds_metrics:
        db_name = metric["db_instance_identifier"]
        arn = f"arn:aws:rds:{region}:{account_id}:db:{db_name}"
        metrics_data.append(
            {
                "type": "rds",
                "arn": arn,
                "state": calc_rds(metric["metrics"]["cpu_utilization"]),
                "cost": cost_dict[arn]
            }
        )

    # ALBメトリクスの処理
    for metric in alb_metrics:
        arn = metric["load_balancer_arn"]
        metrics_data.append(
            {
                "type": "alb",
                "arn": arn,
                "state": calc_alb(),
                "cost": cost_dict[arn],
            }
        )
    return metrics_data


if __name__ == "__main__":
    print(getInfo())
