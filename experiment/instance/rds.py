import boto3
import datetime
from typing import Dict, List, Optional, Union
from .utils import format_bytes


def get_latest_rds_metrics(
    minutes_range: int = 30, delay_minutes: int = 2
) -> List[Dict[str, Union[str, float, datetime.datetime, Dict]]]:
    """
    すべてのRDSインスタンスの最新メトリクスを取得します。

    引数:
        minutes_range (int): メトリクスを取得する過去の分数（デフォルト: 30）
        delay_minutes (int): 遅延を考慮して現在時刻から引く分数（デフォルト: 2）

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
            メトリクスが見つからない場合、metrics値はNoneになり、timestampもNoneになります
    """
    rds = boto3.client("rds")
    cloudwatch = boto3.client("cloudwatch")

    # 時間範囲を計算
    now = datetime.datetime.now(datetime.timezone.utc)
    end_time = now - datetime.timedelta(minutes=delay_minutes)
    start_time = end_time - datetime.timedelta(minutes=minutes_range)

    # すべてのRDSインスタンスを取得
    response = rds.describe_db_instances()
    rds_metrics = []

    # 単位付きで収集するメトリクス
    metric_configs = [
        ("CPUUtilization", "Percent"),
        ("FreeStorageSpace", "Bytes"),
        ("DatabaseConnections", "Count"),
        ("FreeableMemory", "Bytes"),
        ("ReadIOPS", "Count/Second"),
        ("WriteIOPS", "Count/Second"),
    ]

    # 各RDSインスタンスを処理
    for instance in response["DBInstances"]:
        db_instance_identifier = instance["DBInstanceIdentifier"]
        metrics_data = {
            "cpu_utilization": None,
            "free_storage_space": None,
            "database_connections": None,
            "freeable_memory": None,
            "read_iops": None,
            "write_iops": None,
        }
        latest_timestamp = None

        # 各メトリクス名のメトリクスを取得
        for metric_name, unit in metric_configs:
            metrics = cloudwatch.get_metric_statistics(
                Namespace="AWS/RDS",
                MetricName=metric_name,
                Dimensions=[
                    {
                        "Name": "DBInstanceIdentifier",
                        "Value": db_instance_identifier,
                    },
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,  # 5-minute periods
                Statistics=["Average"],
                Unit=unit,
            )

            # メトリクスデータを処理
            datapoints = metrics["Datapoints"]
            if datapoints:
                # タイムスタンプでソートして最新のものを取得
                datapoints.sort(key=lambda x: x["Timestamp"])
                latest = datapoints[-1]

                # メトリクスデータを更新
                metric_key = metric_name.lower()
                if metric_key == "cpuutilization":
                    metrics_data["cpu_utilization"] = latest["Average"]
                elif metric_key == "freestoragespace":
                    metrics_data["free_storage_space"] = latest["Average"]
                elif metric_key == "databaseconnections":
                    metrics_data["database_connections"] = latest["Average"]
                elif metric_key == "freeablememory":
                    metrics_data["freeable_memory"] = latest["Average"]
                elif metric_key == "readiops":
                    metrics_data["read_iops"] = latest["Average"]
                elif metric_key == "writeiops":
                    metrics_data["write_iops"] = latest["Average"]

                # これが最新の場合、タイムスタンプを更新
                if latest_timestamp is None or latest["Timestamp"] > latest_timestamp:
                    latest_timestamp = latest["Timestamp"]

        rds_metrics.append(
            {
                "db_instance_identifier": db_instance_identifier,
                "metrics": metrics_data,
                "timestamp": latest_timestamp,
            }
        )

    return rds_metrics


if __name__ == "__main__":
    # 使用例
    metrics = get_latest_rds_metrics()
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
