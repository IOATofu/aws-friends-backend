import boto3
import datetime
import concurrent.futures
from typing import Dict, List, Optional, Union


def get_alb_list() -> List[Dict[str, str]]:
    """
    すべてのApplication Load Balancerの一覧を取得します。

    戻り値:
        List[Dict]: ALBの情報を含む辞書のリスト:
            - name (str): ALB名
            - arn (str): ALBのARN
            - dns_name (str): ALBのDNS名
            - state (str): ALBの状態
    """
    elbv2 = boto3.client("elbv2")

    # すべてのALBを取得
    response = elbv2.describe_load_balancers()
    alb_list = []

    # 各ALBを処理
    for alb in response["LoadBalancers"]:
        if alb["Type"] != "application":
            continue

        alb_list.append(
            {
                "name": alb["LoadBalancerName"],
                "arn": alb["LoadBalancerArn"],
                "dns_name": alb["DNSName"],
                "state": alb["State"]["Code"],
            }
        )

    return alb_list


def get_latest_alb_metrics(
    minutes_range: int = 15, delay_minutes: int = 0
) -> List[Dict[str, Union[str, float, datetime.datetime, Dict]]]:
    """
    すべてのApplication Load Balancerの最新メトリクスを取得します。
    バッチ処理と並列処理を使用して高速化しています。
    最適化モード：短時間範囲、最小限のメトリクス、高速取得

    引数:
        minutes_range (int): メトリクスを取得する過去の分数（デフォルト: 15）
        delay_minutes (int): 遅延を考慮して現在時刻から引く分数（デフォルト: 0）

    戻り値:
        List[Dict]: ALBメトリクスを含む辞書のリスト:
            - load_balancer_name (str): ALB名
            - metrics (Dict): 以下を含む最新メトリクス:
                - request_count (float): リクエスト数
                - target_response_time (float): 平均ターゲット応答時間（秒）
                - http_code_target_4xx_count (float): ターゲットからの4XXエラー数
                - http_code_target_5xx_count (float): ターゲットからの5XXエラー数
                - healthy_host_count (float): 正常なホスト数
            - timestamp (datetime): 測定のタイムスタンプ
    """
    elbv2 = boto3.client("elbv2")
    cloudwatch = boto3.client("cloudwatch")

    # 時間範囲を計算
    now = datetime.datetime.now(datetime.timezone.utc)
    end_time = now - datetime.timedelta(minutes=delay_minutes)
    start_time = end_time - datetime.timedelta(minutes=minutes_range)

    # すべてのALBを取得
    print("ALB一覧を取得中...")
    response = elbv2.describe_load_balancers()

    # 処理対象のALBをフィルタリング
    application_lbs = [
        alb for alb in response["LoadBalancers"] if alb["Type"] == "application"
    ]

    if not application_lbs:
        print("Application Load Balancerが見つかりませんでした")
        return []

    print(f"{len(application_lbs)}個のALBを処理します")

    # 収集するメトリクス（全てのメトリクスを取得）
    metric_configs = [
        ("RequestCount", "Count", "request_count"),
        ("TargetResponseTime", "Seconds", "target_response_time"),
        ("HTTPCode_Target_4XX_Count", "Count", "http_code_target_4xx_count"),
        ("HTTPCode_Target_5XX_Count", "Count", "http_code_target_5xx_count"),
        ("HealthyHostCount", "Count", "healthy_host_count"),
    ]

    # 各ALBのメトリクスをバッチで取得
    alb_metrics = []

    for alb in application_lbs:
        load_balancer_name = alb["LoadBalancerName"]
        load_balancer_arn = alb["LoadBalancerArn"]

        print(f"処理中のALB: {load_balancer_name}")

        # ARNからディメンション値を取得
        dimension_value = "/".join(load_balancer_arn.split("/")[1:])

        # バッチ処理用のメトリクスクエリを準備
        metric_queries = []
        for i, (metric_name, unit, _) in enumerate(metric_configs):
            metric_queries.append(
                {
                    "Id": f"m{i}",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": "AWS/ApplicationELB",
                            "MetricName": metric_name,
                            "Dimensions": [
                                {"Name": "LoadBalancer", "Value": dimension_value}
                            ],
                        },
                        "Period": 60,  # 1分間隔（高速化）
                        "Stat": "Average",
                        "Unit": unit,
                    },
                }
            )

        # 一度のAPIコールで複数のメトリクスを取得
        print(f"{load_balancer_name}のメトリクスを一括取得中...")
        metrics_response = cloudwatch.get_metric_data(
            MetricDataQueries=metric_queries,
            StartTime=start_time,
            EndTime=end_time,
            ScanBy="TimestampDescending",  # 最新のデータから取得（高速化）
        )

        # メトリクスデータを処理
        metrics_data = {
            "request_count": None,
            "target_response_time": None,
            "http_code_target_4xx_count": None,
            "http_code_target_5xx_count": None,
            "healthy_host_count": None,
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
                    latest_timestamp = latest_ts

        alb_metrics.append(
            {
                "load_balancer_name": load_balancer_name,
                "load_balancer_arn": load_balancer_arn,
                "metrics": metrics_data,
                "timestamp": latest_timestamp,
            }
        )

    print(f"{len(alb_metrics)}個のALBのメトリクスを取得しました")
    return alb_metrics


if __name__ == "__main__":
    # 使用例 - 過去15分のデータを取得
    metrics = get_latest_alb_metrics(minutes_range=15)
    for metric in metrics:
        print(f"\nALB: {metric['load_balancer_name']}")
        print(f"Timestamp: {metric['timestamp']}")
        print("Metrics:")
        for metric_name, value in metric["metrics"].items():
            if value is not None:
                if metric_name == "target_response_time":
                    print(f"  - {metric_name}: {value:.3f} 秒")
                else:
                    print(f"  - {metric_name}: {value:.2f}")
            else:
                print(f"  - {metric_name}: データなし")
