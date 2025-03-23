import boto3
import datetime
import concurrent.futures
from typing import Dict, List, Optional, Union
from datetime import timezone, timedelta


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
        ("RequestCount", "Count", "request_count", "Sum"),  # リクエスト数は合計値
        ("TargetResponseTime", "Seconds", "target_response_time", "Average"),
        ("HTTPCode_Target_4XX_Count", "Count", "http_code_target_4xx_count", "Average"),
        ("HTTPCode_Target_5XX_Count", "Count", "http_code_target_5xx_count", "Average"),
        ("HealthyHostCount", "Count", "healthy_host_count", "Average"),
    ]

    # 各ALBのメトリクスをバッチで取得
    alb_metrics = []

    # JSTタイムゾーンを定義
    JST = timezone(timedelta(hours=9))

    for alb in application_lbs:
        load_balancer_name = alb["LoadBalancerName"]
        load_balancer_arn = alb["LoadBalancerArn"]

        print(f"処理中のALB: {load_balancer_name}")

        # ARNからディメンション値を取得
        dimension_value = "/".join(load_balancer_arn.split("/")[1:])

        # バッチ処理用のメトリクスクエリを準備
        metric_queries = []
        for i, (metric_name, unit, _, stat) in enumerate(metric_configs):
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
                        "Stat": stat,
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
        for i, (_, _, metric_key, _) in enumerate(metric_configs):
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

        # ロードバランサーの状態を取得
        lb_state = alb.get("State", {}).get("Code", "unknown")

        # タイムスタンプをJSTに変換
        if latest_timestamp:
            latest_timestamp = latest_timestamp.astimezone(JST)

        alb_metrics.append(
            {
                "load_balancer_name": load_balancer_name,
                "load_balancer_arn": load_balancer_arn,
                "state": lb_state,  # ロードバランサーの状態を追加
                "metrics": metrics_data,
                "timestamp": latest_timestamp,
            }
        )

    print(f"{len(alb_metrics)}個のALBのメトリクスを取得しました")
    return alb_metrics


def get_alb_metrics_over_time(
    minutes_range: int = 15, delay_minutes: int = 0, interval_minutes: int = 10
) -> List[Dict[str, Union[str, List[Dict[str, Union[float, str]]]]]]:
    """
    すべてのApplication Load Balancerの指定された時間範囲内のメトリクスを取得します。

    引数:
        minutes_range (int): メトリクスを取得する過去の分数（デフォルト: 15）
        delay_minutes (int): 遅延を考慮して現在時刻から引く分数（デフォルト: 0）

    戻り値:
        List[Dict]: 各インスタンスのメトリクスを含む辞書のリスト:
            - instance_id (str): インスタンスID
            - metrics (List[Dict]): 各メトリクスのリスト:
                - 各メトリクス名 (float): メトリクスの値
                - timestamp (str): 測定のタイムスタンプ
    """
    elbv2 = boto3.client("elbv2")
    cloudwatch = boto3.client("cloudwatch")

    # 時間範囲を計算
    now = datetime.datetime.now(datetime.timezone.utc)
    end_time = now - datetime.timedelta(minutes=delay_minutes)
    start_time = end_time - datetime.timedelta(minutes=minutes_range)

    # すべてのALBを取得
    response = elbv2.describe_load_balancers()
    application_lbs = [
        alb for alb in response["LoadBalancers"] if alb["Type"] == "application"
    ]

    if not application_lbs:
        print("Application Load Balancerが見つかりませんでした")
        return []

    # 収集するメトリクス
    metric_configs = [
        ("RequestCount", "Count", "request_count"),
        ("TargetResponseTime", "Seconds", "target_response_time"),
        ("HTTPCode_Target_4XX_Count", "Count", "http_code_target_4xx_count"),
        ("HTTPCode_Target_5XX_Count", "Count", "http_code_target_5xx_count"),
        ("HealthyHostCount", "Count", "healthy_host_count"),
    ]

    alb_metrics = []

    # JSTタイムゾーンを定義
    JST = timezone(timedelta(hours=9))

    for alb in application_lbs:
        load_balancer_name = alb["LoadBalancerName"]
        dimension_value = "/".join(alb["LoadBalancerArn"].split("/")[1:])

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
        interval_data = {}
        for i, (_, _, metric_key) in enumerate(metric_configs):
            result = metrics_response["MetricDataResults"][i]
            for value, ts in zip(result["Values"], result["Timestamps"]):
                rounded_ts = ts - datetime.timedelta(
                    minutes=ts.minute % interval_minutes,
                    seconds=ts.second,
                    microseconds=ts.microsecond,
                )
                if rounded_ts not in interval_data:
                    interval_data[rounded_ts] = {"timestamp": rounded_ts}
                interval_data[rounded_ts][metric_key] = (
                    interval_data[rounded_ts].get(metric_key, 0) + value
                )

        # 各intervalの平均を計算し、データを整形
        metrics = []
        for rounded_ts, data in interval_data.items():
            # JSTに変換
            jst_ts = rounded_ts.astimezone(JST)
            formatted_data = {
                "timestamp": jst_ts.strftime("%Y-%m-%d %H:%M"),
            }
            for key, value in data.items():
                if key != "timestamp":
                    formatted_data[key] = round(value, 2)
            metrics.append(formatted_data)

        # タイムスタンプでソート
        metrics.sort(key=lambda x: x["timestamp"])

        # インスタンスIDを取得（仮にLoadBalancerNameをインスタンスIDとする）
        instance_id = load_balancer_name

        alb_metrics.append(
            {
                "instance_id": instance_id,
                "metrics": metrics,
            }
        )

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

    # 使用例: 時間範囲内のメトリクスを取得
    time_range_metrics = get_alb_metrics_over_time(60)  # 過去60分間のデータを取得
    for alb_metrics in time_range_metrics:
        print(f"ALB名: {alb_metrics['instance_id']}")
        for metric in alb_metrics["metrics"]:
            print(f"  {metric} at {metric['timestamp']}")
    print(time_range_metrics)
