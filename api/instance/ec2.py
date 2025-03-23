import boto3
import datetime
import concurrent.futures
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
    minutes_range: int = 15, delay_minutes: int = 0
) -> List[Dict[str, Union[str, float, datetime.datetime]]]:
    """
    すべてのEC2インスタンスの最新CPU使用率メトリクスを取得します。
    バッチ処理と並列処理を使用して高速化しています。
    最適化モード：短時間範囲、最小限のメトリクス、高速取得

    引数:
        minutes_range (int): メトリクスを取得する過去の分数（デフォルト: 15）
        delay_minutes (int): 遅延を考慮して現在時刻から引く分数（デフォルト: 0）

    戻り値:
        List[Dict]: インスタンスメトリクスを含む辞書のリスト:
            - instance_id (str): EC2インスタンスID
            - cpu_utilization (float): 最新のCPU使用率（パーセント）
            - timestamp (datetime): 測定のタイムスタンプ
    """
    ec2 = boto3.client("ec2")
    cloudwatch = boto3.client("cloudwatch")

    # 時間範囲を計算
    now = datetime.datetime.now(datetime.timezone.utc)
    end_time = now - datetime.timedelta(minutes=delay_minutes)
    start_time = end_time - datetime.timedelta(minutes=minutes_range)

    # 全てのEC2インスタンスを取得（フィルタリングなし）
    print("全てのEC2インスタンスを取得中...")
    response = ec2.describe_instances()

    # 処理対象のインスタンスを抽出
    instances = []
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            # Name タグを取得
            instance_name = "N/A"
            if "Tags" in instance:
                for tag in instance["Tags"]:
                    if tag["Key"] == "Name":
                        instance_name = tag["Value"]
                        break

            # インスタンス情報を追加
            instances.append(
                {
                    "InstanceId": instance["InstanceId"],
                    "Name": instance_name,
                    "State": instance["State"]["Name"],
                }
            )

    if not instances:
        print("EC2インスタンスが見つかりませんでした")
        return []

    print(f"{len(instances)}個のEC2インスタンスを処理します")
    print(f"インスタンス一覧: {[i['InstanceId'] for i in instances]}")

    # 一度のAPIコールで全インスタンスのメトリクスを取得（超高速化）
    instance_ids = [instance["InstanceId"] for instance in instances]

    # 最大20インスタンスずつバッチ処理（CloudWatchの制限）
    batch_size = 20
    all_metrics = []

    for i in range(0, len(instance_ids), batch_size):
        batch_ids = instance_ids[i : i + batch_size]
        print(
            f"EC2メトリクスバッチ取得中: {i+1}～{min(i+batch_size, len(instance_ids))}個目"
        )

        # バッチ処理用のメトリクスクエリを準備
        metric_queries = []
        for j, instance_id in enumerate(batch_ids):
            metric_queries.append(
                {
                    "Id": f"cpu{j}",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/EC2",
                            "MetricName": "CPUUtilization",
                            "Dimensions": [
                                {"Name": "InstanceId", "Value": instance_id}
                            ],
                        },
                        "Period": 60,  # 1分間隔（高速化）
                        "Stat": "Average",
                        "Unit": "Percent",
                    },
                }
            )

        # 一度のAPIコールでメトリクスを取得
        metrics_response = cloudwatch.get_metric_data(
            MetricDataQueries=metric_queries,
            StartTime=start_time,
            EndTime=end_time,
            ScanBy="TimestampDescending",  # 最新のデータから取得（高速化）
        )

        # メトリクスデータを処理
        for j, instance_id in enumerate(batch_ids):
            # 対応するインスタンス名を取得
            instance_name = next(
                (
                    inst["Name"]
                    for inst in instances
                    if inst["InstanceId"] == instance_id
                ),
                "N/A",
            )
            result = metrics_response["MetricDataResults"][j]

            if result["Values"]:
                # 最新の値を取得（既にTimestampDescendingでソート済み）
                latest_value = result["Values"][0]
                latest_ts = result["Timestamps"][0]

                # 対応するインスタンスの状態を取得
                instance_state = next(
                    (
                        inst["State"]
                        for inst in instances
                        if inst["InstanceId"] == instance_id
                    ),
                    "unknown",
                )

                all_metrics.append(
                    {
                        "instance_name": instance_name,
                        "instance_id": instance_id,
                        "instance_state": instance_state,  # インスタンスの状態を追加
                        "cpu_utilization": latest_value,
                        "timestamp": latest_ts,
                    }
                )
            else:
                # データが見つからない場合
                # 対応するインスタンスの状態を取得
                instance_state = next(
                    (
                        inst["State"]
                        for inst in instances
                        if inst["InstanceId"] == instance_id
                    ),
                    "unknown",
                )

                all_metrics.append(
                    {
                        "instance_name": instance_name,
                        "instance_id": instance_id,
                        "instance_state": instance_state,  # インスタンスの状態を追加
                        "cpu_utilization": None,
                        "timestamp": None,
                    }
                )

    print(f"{len(all_metrics)}個のEC2インスタンスのメトリクスを取得しました")
    return all_metrics


def get_ec2_metrics_over_time(
    minutes_range: int = 15, delay_minutes: int = 0, interval_minutes: int = 10
) -> List[Dict[str, Union[str, List[Dict[str, Union[float, str]]]]]]:
    """
    すべてのEC2インスタンスの指定された時間範囲内のCPU使用率メトリクスを取得します。

    引数:
        minutes_range (int): メトリクスを取得する過去の分数（デフォルト: 15）
        delay_minutes (int): 遅延を考慮して現在時刻から引く分数（デフォルト: 0）

    戻り値:
        List[Dict]: インスタンスメトリクスを含む辞書のリスト:
            - instance_id (str): EC2インスタンスID
            - metrics (List[Dict]): 各メトリクスのリスト:
                - cpu_utilization (float): CPU使用率（パーセント）
                - timestamp (str): 測定のタイムスタンプ
    """
    ec2 = boto3.client("ec2")
    cloudwatch = boto3.client("cloudwatch")

    # 時間範囲を計算
    now = datetime.datetime.now(datetime.timezone.utc)
    end_time = now - datetime.timedelta(minutes=delay_minutes)
    start_time = end_time - datetime.timedelta(minutes=minutes_range)

    # 全てのEC2インスタンスを取得（フィルタリングなし）
    response = ec2.describe_instances()

    # 処理対象のインスタンスを抽出
    instances = []
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            instances.append(instance["InstanceId"])

    if not instances:
        print("EC2インスタンスが見つかりませんでした")
        return []

    # 最大20インスタンスずつバッチ処理（CloudWatchの制限）
    batch_size = 20
    all_metrics = []

    for i in range(0, len(instances), batch_size):
        batch_ids = instances[i : i + batch_size]

        # バッチ処理用のメトリクスクエリを準備
        metric_queries = []
        for j, instance_id in enumerate(batch_ids):
            metric_queries.append(
                {
                    "Id": f"cpu{j}",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/EC2",
                            "MetricName": "CPUUtilization",
                            "Dimensions": [
                                {"Name": "InstanceId", "Value": instance_id}
                            ],
                        },
                        "Period": 60,  # 1分間隔
                        "Stat": "Average",
                        "Unit": "Percent",
                    },
                }
            )

        # メトリクスを取得
        metrics_response = cloudwatch.get_metric_data(
            MetricDataQueries=metric_queries,
            StartTime=start_time,
            EndTime=end_time,
            ScanBy="TimestampDescending",
        )

        # メトリクスデータを処理
        for j, instance_id in enumerate(batch_ids):
            result = metrics_response["MetricDataResults"][j]
            metrics = []

            # interval_minutesごとに平均を計算
            interval_start = start_time
            while interval_start < end_time:
                interval_end = interval_start + datetime.timedelta(minutes=interval_minutes)
                interval_values = [
                    value for value, ts in zip(result["Values"], result["Timestamps"])
                    if interval_start <= ts < interval_end
                ]

                if interval_values:
                    avg_cpu = sum(interval_values) / len(interval_values)
                    metrics.append(
                        {
                            "cpu_utilization": round(avg_cpu, 2),
                            "timestamp": interval_start.strftime("%Y-%m-%d %H:%M"),
                        }
                    )

                interval_start = interval_end

            all_metrics.append(
                {
                    "instance_id": instance_id,
                    "metrics": metrics,
                }
            )

    return all_metrics


if __name__ == "__main__":
    # 使用例: 最新のメトリクスを取得
    metrics = get_latest_ec2_metrics()
    for metric in metrics:
        if metric["cpu_utilization"] is not None:
            print(
                f"{metric['instance_id']} ({metric['instance_name']}) - CPU: {metric['cpu_utilization']:.2f}% at {metric['timestamp']}"
            )
        else:
            print(
                f"{metric['instance_id']} ({metric['instance_name']}) - CPUデータが見つかりません"
            )

    # 使用例: 時間範囲内のメトリクスを取得
    time_range_metrics = get_ec2_metrics_over_time(180, 10)  # 過去12時間のデータを取得
    for instance_metrics in time_range_metrics:
        print(f"インスタンスID: {instance_metrics['instance_id']}")
        for metric in instance_metrics["metrics"]:
            print(
                f"  CPU: {metric['cpu_utilization']:.2f}% at {metric['timestamp']}"
            )
    print(time_range_metrics)