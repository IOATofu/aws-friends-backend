import boto3
import asyncio
from .ec2 import get_latest_ec2_metrics
from .rds import get_latest_rds_metrics
from .alb import get_latest_alb_metrics
from .calc_state import calc_ec2, calc_rds, calc_alb
from .cost import estimate_realtime_cost_by_arn

# メトリクス取得の時間範囲設定
minutes_range = 5  # 15分間のデータのみ取得
delay_minutes = 0  # 遅延なし


async def get_all_metrics_async():
    """
    EC2、RDS、ALBのメトリクスを非同期で並列取得します。
    最適化された時間範囲設定を使用します。
    """
    print(f"メトリクス取得開始: 最適化モード（過去{minutes_range}分間のデータ）")

    # 非同期タスクを作成 - グローバル設定の時間範囲を使用
    tasks = [
        asyncio.to_thread(get_latest_ec2_metrics, minutes_range, delay_minutes),
        asyncio.to_thread(get_latest_rds_metrics, minutes_range, delay_minutes),
        asyncio.to_thread(get_latest_alb_metrics, minutes_range, delay_minutes),
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

    # デバッグ情報
    print(f"取得したEC2メトリクス数: {len(ec2_metrics)}")
    for i, metric in enumerate(ec2_metrics):
        print(
            f"EC2 {i+1}: ID={metric['instance_id']}, State={metric.get('instance_state', 'unknown')}"
        )

    print(f"取得したRDSメトリクス数: {len(rds_metrics)}")
    for i, metric in enumerate(rds_metrics):
        print(
            f"RDS {i+1}: ID={metric['db_instance_identifier']}, Status={metric.get('db_instance_status', 'unknown')}"
        )

    print(f"取得したALBメトリクス数: {len(alb_metrics)}")
    for i, metric in enumerate(alb_metrics):
        print(
            f"ALB {i+1}: Name={metric['load_balancer_name']}, State={metric.get('state', 'unknown')}"
        )

    # EC2メトリクスの処理 - 起動中のインスタンスのみ
    for metric in ec2_metrics:
        instance_id = metric["instance_id"]
        instance_state = metric.get("instance_state", "")

        # 起動中のインスタンスのみを処理
        if instance_state == "running":
            arn = f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}"
            metrics_data.append(
                {
                    "type": "ec2",
                    "name": metric["instance_name"],
                    "arn": arn,
                    "state": calc_ec2(metric["cpu_utilization"]),
                    "cost": cost_dict.get(arn, 0),
                }
            )

    # RDSメトリクスの処理 - 利用可能なインスタンスのみ
    for metric in rds_metrics:
        db_name = metric["db_instance_identifier"]
        db_status = metric.get("db_instance_status", "")

        # 利用可能なインスタンスのみを処理
        if db_status == "available":
            arn = f"arn:aws:rds:{region}:{account_id}:db:{db_name}"
            metrics_data.append(
                {
                    "type": "rds",
                    "name": db_name,
                    "arn": arn,
                    "state": calc_rds(metric["metrics"]["cpu_utilization"]),
                    "cost": cost_dict.get(arn, 0),
                }
            )

    # ALBメトリクスの処理 - アクティブなロードバランサーのみ
    for metric in alb_metrics:
        lb_state = metric.get("state", "")

        # アクティブなロードバランサーのみを処理
        if lb_state == "active":
            arn = metric["load_balancer_arn"]
            metrics_data.append(
                {
                    "type": "alb",
                    "name": metric["load_balancer_name"],
                    "arn": arn,
                    "state": calc_alb(metric["metrics"]["request_count"]),
                    "cost": cost_dict.get(arn, 0),
                }
            )
    return metrics_data


if __name__ == "__main__":
    print(getInfo())
