import boto3
import datetime
from typing import Dict, List, Optional, Union


def get_ec2_list() -> List[Dict[str, str]]:
    """
    すべてのEC2インスタンスの一覧を取得します。

    戻り値:
        List[Dict]: EC2インスタンスの情報を含む辞書のリスト:
            - instance_id (str): インスタンスID
            - arn (str): インスタンスのARN
            - name (str): インスタンス名（Name タグ）
            - state (str): インスタンスの状態
    """
    ec2 = boto3.client("ec2")
    region = ec2.meta.region_name
    account_id = boto3.client("sts").get_caller_identity()["Account"]

    # すべてのEC2インスタンスを取得
    response = ec2.describe_instances()
    instance_list = []

    # 各インスタンスを処理
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            # インスタンスのARNを構築
            instance_arn = (
                f"arn:aws:ec2:{region}:{account_id}:instance/{instance['InstanceId']}"
            )

            # Name タグを取得
            name = "N/A"
            if "Tags" in instance:
                for tag in instance["Tags"]:
                    if tag["Key"] == "Name":
                        name = tag["Value"]
                        break

            instance_list.append(
                {
                    "instance_id": instance["InstanceId"],
                    "arn": instance_arn,
                    "name": name,
                    "state": instance["State"]["Name"],
                }
            )

    return instance_list


def get_latest_ec2_metrics(
    minutes_range: int = 30, delay_minutes: int = 2
) -> List[Dict[str, Union[str, float, datetime.datetime]]]:
    """
    すべてのEC2インスタンスの最新CPU使用率メトリクスを取得します。

    引数:
        minutes_range (int): メトリクスを取得する過去の分数（デフォルト: 30）
        delay_minutes (int): 遅延を考慮して現在時刻から引く分数（デフォルト: 2）

    戻り値:
        List[Dict]: インスタンスメトリクスを含む辞書のリスト:
            - instance_id (str): EC2インスタンスID
            - cpu_utilization (float): 最新のCPU使用率（パーセント）
            - timestamp (datetime): 測定のタイムスタンプ
            メトリクスが見つからない場合、cpu_utilizationはNoneになり、timestampもNoneになります
    """
    ec2 = boto3.client("ec2")
    cloudwatch = boto3.client("cloudwatch")

    # 時間範囲を計算
    now = datetime.datetime.now(datetime.timezone.utc)
    end_time = now - datetime.timedelta(minutes=delay_minutes)
    start_time = end_time - datetime.timedelta(minutes=minutes_range)

    # すべてのEC2インスタンスを取得
    response = ec2.describe_instances()
    instance_metrics = []

    # 各インスタンスを処理
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            instance_id = instance["InstanceId"]

            # CloudWatchメトリクスを取得
            metrics = cloudwatch.get_metric_statistics(
                Namespace="AWS/EC2",
                MetricName="CPUUtilization",
                Dimensions=[
                    {"Name": "InstanceId", "Value": instance_id},
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,  # 5分間隔
                Statistics=["Average"],
                Unit="Percent",
            )

            # メトリクスデータを処理
            datapoints = metrics["Datapoints"]
            if datapoints:
                # タイムスタンプでソートして最新のものを取得
                datapoints.sort(key=lambda x: x["Timestamp"])
                latest = datapoints[-1]

                instance_metrics.append(
                    {
                        "instance_id": instance_id,
                        "cpu_utilization": latest["Average"],
                        "timestamp": latest["Timestamp"],
                    }
                )
            else:
                # データが見つからない場合、nullメトリクスでインスタンスを含める
                instance_metrics.append(
                    {
                        "instance_id": instance_id,
                        "cpu_utilization": None,
                        "timestamp": None,
                    }
                )

    return instance_metrics


if __name__ == "__main__":
    # 使用例
    metrics = get_latest_ec2_metrics()
    for metric in metrics:
        if metric["cpu_utilization"] is not None:
            print(
                f"{metric['instance_id']} - CPU: {metric['cpu_utilization']:.2f}% at {metric['timestamp']}"
            )
        else:
            print(f"{metric['instance_id']} - CPUデータが見つかりません")
