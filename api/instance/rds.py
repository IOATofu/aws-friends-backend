import boto3
import datetime
import concurrent.futures
from typing import Dict, List, Optional, Union
from .utils import format_bytes
from datetime import timezone, timedelta


def get_latest_rds_metrics(
    minutes_range: int = 15, delay_minutes: int = 0
) -> List[Dict[str, Union[str, float, datetime.datetime, Dict]]]:
    """
    すべてのRDSインスタンスの最新メトリクスを取得します。
    バッチ処理と並列処理を使用して高速化しています。
    最適化モード：短時間範囲、最小限のメトリクス、高速取得

    引数:
        minutes_range (int): メトリクスを取得する過去の分数（デフォルト: 15）
        delay_minutes (int): 遅延を考慮して現在時刻から引く分数（デフォルト: 0）

    戻り値:
        List[Dict]: RDSメトリクスを含む辞書のリスト:
            - db_instance_identifier (str): RDSインスタンス識別子
            - metrics (Dict): 以下を含む最新メトリクス:
                - cpu_utilization (float): CPU使用率（パーセント）
                - free_storage_space (float): 利用可能なストレージ容量（バイト）
                - database_connections (float): データベース接続数
                - freeable_memory (float): 解放可能なメモリ（バイト）
                - read_iops (float): 1秒あたりの読み取り操作数
                - write_iops (float): 1秒あたりの書き込み操作数
            - timestamp (datetime): 測定のタイムスタンプ
    """
    rds = boto3.client("rds")
    cloudwatch = boto3.client("cloudwatch")

    # JSTタイムゾーンを定義
    JST = timezone(timedelta(hours=9))

    # 時間範囲を計算
    now = datetime.datetime.now(JST)
    end_time = now - datetime.timedelta(minutes=delay_minutes)
    start_time = end_time - datetime.timedelta(minutes=minutes_range)

    # 利用可能なRDSインスタンスを取得
    print("利用可能なRDSインスタンスを取得中...")
    response = rds.describe_db_instances()

    # 処理対象のRDSインスタンスを抽出
    instances = response["DBInstances"]

    if not instances:
        print("RDSインスタンスが見つかりませんでした")
        return []

    print(f"{len(instances)}個のRDSインスタンスを処理します")

    # 単位付きで収集するメトリクス（全てのメトリクスを取得）
    metric_configs = [
        ("CPUUtilization", "Percent", "cpu_utilization"),
        ("FreeStorageSpace", "Bytes", "free_storage_space"),
        ("DatabaseConnections", "Count", "database_connections"),
        ("FreeableMemory", "Bytes", "freeable_memory"),
        ("ReadIOPS", "Count/Second", "read_iops"),
        ("WriteIOPS", "Count/Second", "write_iops"),
    ]

    # 各RDSインスタンスのメトリクスをバッチで取得
    rds_metrics = []

    for instance in instances:
        db_instance_identifier = instance["DBInstanceIdentifier"]
        print(f"処理中のRDSインスタンス: {db_instance_identifier}")

        # バッチ処理用のメトリクスクエリを準備
        metric_queries = []
        for i, (metric_name, unit, _) in enumerate(metric_configs):
            metric_queries.append(
                {
                    "Id": f"m{i}",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/RDS",
                            "MetricName": metric_name,
                            "Dimensions": [
                                {
                                    "Name": "DBInstanceIdentifier",
                                    "Value": db_instance_identifier,
                                }
                            ],
                        },
                        "Period": 60,  # 1分間隔（高速化）
                        "Stat": "Average",
                        "Unit": unit,
                    },
                }
            )

        # 一度のAPIコールで複数のメトリクスを取得
        print(f"{db_instance_identifier}のメトリクスを一括取得中...")
        metrics_response = cloudwatch.get_metric_data(
            MetricDataQueries=metric_queries,
            StartTime=start_time,
            EndTime=end_time,
            ScanBy="TimestampDescending",  # 最新のデータから取得（高速化）
        )

        # メトリクスデータを処理
        metrics_data = {
            "cpu_utilization": None,
            "free_storage_space": None,
            "database_connections": None,
            "freeable_memory": None,
            "read_iops": None,
            "write_iops": None,
        }
        latest_timestamp = None

        # 各メトリクスの結果を処理
        for i, (_, _, metric_key) in enumerate(metric_configs):
            result = metrics_response["MetricDataResults"][i]

            if result["Values"]:
                # 最新の値を取得（既にTimestampDescendingでソート済み）
                latest_value = result["Values"][0]
                latest_ts = result["Timestamps"][0]

                # メトリクスデータを更新
                metrics_data[metric_key] = latest_value

                # タイムスタンプを更新
                if latest_timestamp is None or latest_ts > latest_timestamp:
                    latest_timestamp = latest_ts.astimezone(JST)

        # インスタンスのステータスを取得
        db_instance_status = instance.get("DBInstanceStatus", "unknown")

        rds_metrics.append(
            {
                "db_instance_identifier": db_instance_identifier,
                "db_instance_status": db_instance_status,  # インスタンスのステータスを追加
                "metrics": metrics_data,
                "timestamp": latest_timestamp,
            }
        )

    print(f"{len(rds_metrics)}個のRDSインスタンスのメトリクスを取得しました")
    return rds_metrics


def get_rds_metrics_over_time(
    minutes_range: int = 15, delay_minutes: int = 0, interval_minutes: int = 5
) -> List[Dict[str, Union[str, List[Dict[str, Union[float, str]]]]]]:
    """
    すべてのRDSインスタンスの指定された時間範囲内のメトリクスを取得し、タイムスタンプごとに集計します。

    引数:
        minutes_range (int): メトリクスを取得する過去の分数（デフォルト: 15）
        delay_minutes (int): 遅延を考慮して現在時刻から引く分数（デフォルト: 0）
        interval_minutes (int): サンプリング間隔（デフォルト: 5）

    戻り値:
        List[Dict]: インスタンスメトリクスを含む辞書のリスト:
            - db_instance_identifier (str): RDSインスタンス識別子
            - metrics (List[Dict]): 各メトリクスのリスト:
                - metric (str): メトリクス名
                - value (float): メトリクスの値
                - timestamp (str): 測定のタイムスタンプ（YYYY-MM-DD HH:MM形式）
    """
    rds = boto3.client("rds")
    cloudwatch = boto3.client("cloudwatch")

    # JSTタイムゾーンを定義
    JST = timezone(timedelta(hours=9))

    # 時間範囲を計算
    now = datetime.datetime.now(JST)
    end_time = now - datetime.timedelta(minutes=delay_minutes)
    start_time = end_time - datetime.timedelta(minutes=minutes_range)

    # 利用可能なRDSインスタンスを取得
    response = rds.describe_db_instances()
    instances = response["DBInstances"]

    if not instances:
        print("RDSインスタンスが見つかりませんでした")
        return []

    # 単位付きで収集するメトリクス
    metric_configs = [
        ("CPUUtilization", "Percent", "cpu_utilization"),
        ("FreeStorageSpace", "Bytes", "free_storage_space"),
        ("DatabaseConnections", "Count", "database_connections"),
        ("FreeableMemory", "Bytes", "freeable_memory"),
        ("ReadIOPS", "Count/Second", "read_iops"),
        ("WriteIOPS", "Count/Second", "write_iops"),
    ]

    rds_metrics = []

    for instance in instances:
        db_instance_identifier = instance["DBInstanceIdentifier"]

        # バッチ処理用のメトリクスクエリを準備
        metric_queries = []
        for i, (metric_name, unit, _) in enumerate(metric_configs):
            metric_queries.append(
                {
                    "Id": f"m{i}",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/RDS",
                            "MetricName": metric_name,
                            "Dimensions": [
                                {
                                    "Name": "DBInstanceIdentifier",
                                    "Value": db_instance_identifier,
                                }
                            ],
                        },
                        "Period": 60,
                        "Stat": "Average",
                        "Unit": unit,
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
        interval_delta = datetime.timedelta(minutes=interval_minutes)
        metrics_by_timestamp = {}

        for i, (_, _, metric_key) in enumerate(metric_configs):
            result = metrics_response["MetricDataResults"][i]
            if result["Values"]:
                # タイムスタンプをサンプリング間隔で丸める
                rounded_timestamps = [
                    ts - datetime.timedelta(minutes=ts.minute % interval_minutes, seconds=ts.second, microseconds=ts.microsecond)
                    for ts in result["Timestamps"]
                ]

                # 丸めたタイムスタンプを基にデータを集計
                for value, rounded_ts in zip(result["Values"], rounded_timestamps):
                    rounded_ts = rounded_ts.astimezone(JST)
                    if rounded_ts not in metrics_by_timestamp:
                        metrics_by_timestamp[rounded_ts] = {"timestamp": rounded_ts.strftime("%Y-%m-%d %H:%M")}
                    # 値をフォーマット
                    if metric_key in ["cpu_utilization", "read_iops", "write_iops"]:
                        metrics_by_timestamp[rounded_ts][metric_key] = round(value, 2)
                    elif metric_key in ["free_storage_space", "freeable_memory"]:
                        metrics_by_timestamp[rounded_ts][metric_key] = format_bytes(value)
                    else:
                        metrics_by_timestamp[rounded_ts][metric_key] = value

        # metrics_by_timestampをリストに変換
        metrics = list(metrics_by_timestamp.values())

        rds_metrics.append(
            {
                "range": f"{minutes_range} min",
                "interval": f"{interval_minutes} min",
                "db_instance_identifier": db_instance_identifier,
                "metrics": metrics,
            }
        )

    return rds_metrics


if __name__ == "__main__":
    # 使用例
    metrics = get_latest_rds_metrics(720)
    for metric in metrics:
        print(f"\nRDS Instance: {metric['db_instance_identifier']}")
        print(f"Timestamp: {metric['timestamp']}")
        print("Metrics:")
        for metric_name, value in metric["metrics"].items():
            if value is not None:
                if metric_name in ["free_storage_space", "freeable_memory"]:
                    print(f"  - {metric_name}: {format_bytes(value)}")
                elif metric_name == "cpu_utilization":
                    print(f"  - {metric_name}: {value:.2f}%")
                elif metric_name.endswith("iops"):
                    print(f"  - {metric_name}: {value:.2f} IOPS")
                else:
                    print(f"  - {metric_name}: {value:.2f}")
            else:
                print(f"  - {metric_name}: No data")

    # 使用例: 時間範囲内のメトリクスを取得
    time_range_metrics = get_rds_metrics_over_time(180)  # 過去60分間のデータを取得
    for instance_metrics in time_range_metrics:
        print(f"RDSインスタンスID: {instance_metrics['db_instance_identifier']}")
        for metric in instance_metrics["metrics"]:
            print(f"  {metric} at {metric['timestamp']}")
    print(time_range_metrics)
