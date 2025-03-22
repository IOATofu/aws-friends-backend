import boto3
import datetime
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
    minutes_range: int = 30, delay_minutes: int = 2
) -> List[Dict[str, Union[str, float, datetime.datetime, Dict]]]:
    """
    すべてのApplication Load Balancerの最新メトリクスを取得します。

    引数:
        minutes_range (int): メトリクスを取得する過去の分数（デフォルト: 30）
        delay_minutes (int): 遅延を考慮して現在時刻から引く分数（デフォルト: 2）

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
            メトリクスが見つからない場合、metrics値はNoneになり、timestampもNoneになります
    """
    elbv2 = boto3.client("elbv2")
    cloudwatch = boto3.client("cloudwatch")

    # 時間範囲を計算
    now = datetime.datetime.now(datetime.timezone.utc)
    end_time = now - datetime.timedelta(minutes=delay_minutes)
    start_time = end_time - datetime.timedelta(minutes=minutes_range)

    # すべてのALBを取得
    response = elbv2.describe_load_balancers()
    alb_metrics = []

    # 収集するメトリクス
    metric_names = [
        "RequestCount",
        "TargetResponseTime",
        "HTTPCode_Target_4XX_Count",
        "HTTPCode_Target_5XX_Count",
        "HealthyHostCount",
    ]

    # 各ALBを処理
    for alb in response["LoadBalancers"]:
        if alb["Type"] != "application":
            continue

        load_balancer_name = alb["LoadBalancerName"]
        load_balancer_Arn = alb["LoadBalancerArn"],
        metrics_data = {
            "request_count": None,
            "target_response_time": None,
            "http_code_target_4xx_count": None,
            "http_code_target_5xx_count": None,
            "healthy_host_count": None,
        }
        latest_timestamp = None

        # 各メトリクス名のメトリクスを取得
        for metric_name in metric_names:
            metrics = cloudwatch.get_metric_statistics(
                Namespace="AWS/ApplicationELB",
                MetricName=metric_name,
                Dimensions=[
                    {
                        "Name": "LoadBalancer",
                        "Value": alb["LoadBalancerArn"].split("/")[-1],
                    },
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,  # 5分間隔
                Statistics=["Average"],
                Unit="Count" if metric_name != "TargetResponseTime" else "Seconds",
            )

            # メトリクスデータを処理
            datapoints = metrics["Datapoints"]
            print(datapoints)
            if datapoints:
                # タイムスタンプでソートして最新のものを取得
                datapoints.sort(key=lambda x: x["Timestamp"])
                latest = datapoints[-1]

                # メトリクスデータを更新
                metric_key = metric_name.lower()
                if metric_key == "requestcount":
                    metrics_data["request_count"] = latest["Average"]
                elif metric_key == "targetresponsetime":
                    metrics_data["target_response_time"] = latest["Average"]
                elif metric_key == "httpcode_target_4xx_count":
                    metrics_data["http_code_target_4xx_count"] = latest["Average"]
                elif metric_key == "httpcode_target_5xx_count":
                    metrics_data["http_code_target_5xx_count"] = latest["Average"]
                elif metric_key == "healthyhostcount":
                    metrics_data["healthy_host_count"] = latest["Average"]

                # これが最新の場合、タイムスタンプを更新
                if latest_timestamp is None or latest["Timestamp"] > latest_timestamp:
                    latest_timestamp = latest["Timestamp"]
        alb_metrics.append(
            {
                "load_balancer_name": load_balancer_name,
                "load_balancer_arn": load_balancer_Arn[0],
                "metrics": metrics_data,
                "timestamp": latest_timestamp,
            }
        )
    return alb_metrics


if __name__ == "__main__":
    # 使用例
    metrics = get_latest_alb_metrics()
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
