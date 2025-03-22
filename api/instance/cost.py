import boto3
import json
from datetime import datetime
from typing import Dict, List

# リージョンコードから Pricing API 用の location 名のマッピング例
REGION_TO_LOCATION = {
    "us-east-1": "US East (N. Virginia)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    # 必要に応じて追加
}
def get_instance_costs():
    return 0

def get_ec2_price(
    instance_type: str, location: str, operating_system: str = "Linux"
) -> float:
    """
    Pricing API を用いて、EC2 の指定インスタンスタイプのオンデマンド料金（USD/時）を取得する。
    """
    pricing = boto3.client("pricing", region_name="us-east-1")
    try:
        response = pricing.get_products(
            ServiceCode="AmazonEC2",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                {
                    "Type": "TERM_MATCH",
                    "Field": "operatingSystem",
                    "Value": operating_system,
                },
                {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
                {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
            ],
            FormatVersion="aws_v1",
            MaxResults=1,
        )
        if response.get("PriceList"):
            price_item = json.loads(response["PriceList"][0])
            # 最初の OnDemand の要素を取り出す
            on_demand = next(iter(price_item["terms"]["OnDemand"].values()))
            price_dimensions = next(iter(on_demand["priceDimensions"].values()))
            price_per_hour = float(price_dimensions["pricePerUnit"]["USD"])
            return price_per_hour
    except Exception as e:
        print(f"EC2 料金取得エラー: {e}")
    return 0.0


def get_rds_price(instance_class: str, location: str, engine: str = "MySQL") -> float:
    """
    Pricing API を用いて、RDS の指定インスタンスクラスのオンデマンド料金（USD/時）を取得する。
    ※ ここでは Single-AZ、Linux/UNIX の場合を想定。
    """
    pricing = boto3.client("pricing", region_name="us-east-1")
    try:
        response = pricing.get_products(
            ServiceCode="AmazonRDS",
            Filters=[
                {
                    "Type": "TERM_MATCH",
                    "Field": "instanceType",
                    "Value": instance_class,
                },
                {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                {"Type": "TERM_MATCH", "Field": "databaseEngine", "Value": engine},
                {
                    "Type": "TERM_MATCH",
                    "Field": "deploymentOption",
                    "Value": "Single-AZ",
                },
            ],
            FormatVersion="aws_v1",
            MaxResults=1,
        )
        if response.get("PriceList"):
            price_item = json.loads(response["PriceList"][0])
            on_demand = next(iter(price_item["terms"]["OnDemand"].values()))
            price_dimensions = next(iter(on_demand["priceDimensions"].values()))
            price_per_hour = float(price_dimensions["pricePerUnit"]["USD"])
            return price_per_hour
    except Exception as e:
        print(f"RDS 料金取得エラー: {e}")
    return 0.0


def get_alb_price(location: str) -> float:
    """
    Pricing API を用いて、ALB（Application Load Balancer）の基本料金（USD/時）を取得する。
    ※ ALB の料金は従量課金（LCU やリクエスト数など）もあるため、ここではベース料金のみを概算。
    """
    pricing = boto3.client("pricing", region_name="us-east-1")
    try:
        response = pricing.get_products(
            ServiceCode="AWSELB",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "location", "Value": location},
                {
                    "Type": "TERM_MATCH",
                    "Field": "productFamily",
                    "Value": "Load Balancer",
                },
            ],
            FormatVersion="aws_v1",
            MaxResults=1,
        )
        if response.get("PriceList"):
            price_item = json.loads(response["PriceList"][0])
            on_demand = next(iter(price_item["terms"]["OnDemand"].values()))
            price_dimensions = next(iter(on_demand["priceDimensions"].values()))
            price_per_hour = float(price_dimensions["pricePerUnit"]["USD"])
            return price_per_hour
    except Exception as e:
        print(f"ALB 料金取得エラー: {e}")
    return 0.0


def estimate_realtime_cost_by_arn() -> List[Dict]:
    """
    現在稼働中の EC2、RDS、ALB の各リソースごとに、ARN をキーとして
    今日の午前0時から現在までの経過時間に応じた概算コスト（USD）を算出します。

    Returns:
        List[Dict]: 各リソースごとの情報と概算コストのリスト
        例:
        [
          {
            "instance_arn": "arn:aws:ec2:us-east-1:123456789012:instance/i-0123456789abcdef",
            "service_type": "ec2",
            "instance_type": "t2.micro",
            "cost": 0.23,
            "hours_elapsed": 12.5
          },
          ...
        ]
    """
    results = []
    now = datetime.now()
    start_of_day = datetime(now.year, now.month, now.day)
    elapsed_hours = (now - start_of_day).total_seconds() / 3600

    session = boto3.session.Session()
    current_region = session.region_name or "us-east-1"
    # STS からアカウントIDを取得
    sts = boto3.client("sts")
    account_id = sts.get_caller_identity()["Account"]
    location = REGION_TO_LOCATION.get(current_region, current_region)

    # ----- EC2 の処理 -----
    ec2 = boto3.client("ec2", region_name=current_region)
    ec2_resp = ec2.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    )
    ec2_price_cache: Dict[str, float] = {}

    for reservation in ec2_resp.get("Reservations", []):
        for instance in reservation.get("Instances", []):
            instance_id = instance.get("InstanceId")
            instance_type = instance.get("InstanceType")
            if instance_type not in ec2_price_cache:
                hourly_rate = get_ec2_price(instance_type, location)
                ec2_price_cache[instance_type] = hourly_rate
            else:
                hourly_rate = ec2_price_cache[instance_type]
            cost = hourly_rate * elapsed_hours
            # EC2 の ARN は自前で生成
            instance_arn = (
                f"arn:aws:ec2:{current_region}:{account_id}:instance/{instance_id}"
            )
            results.append(
                {
                    "instance_arn": instance_arn,
                    "service_type": "ec2",
                    "instance_type": instance_type,
                    "cost": round(cost, 4),
                    "hours_elapsed": round(elapsed_hours, 2),
                }
            )

    # ----- RDS の処理 -----
    rds = boto3.client("rds", region_name=current_region)
    rds_resp = rds.describe_db_instances()
    rds_price_cache: Dict[str, float] = {}

    for db_instance in rds_resp.get("DBInstances", []):
        if db_instance.get("DBInstanceStatus") == "available":
            instance_class = db_instance.get("DBInstanceClass")
            instance_arn = db_instance.get("DBInstanceArn")
            if not instance_arn:
                # 通常は DBInstanceArn が返されるが、念のため構築
                db_instance_identifier = db_instance.get("DBInstanceIdentifier")
                instance_arn = f"arn:aws:rds:{current_region}:{account_id}:db:{db_instance_identifier}"
            if instance_class not in rds_price_cache:
                hourly_rate = get_rds_price(instance_class, location)
                rds_price_cache[instance_class] = hourly_rate
            else:
                hourly_rate = rds_price_cache[instance_class]
            cost = hourly_rate * elapsed_hours
            results.append(
                {
                    "instance_arn": instance_arn,
                    "service_type": "rds",
                    "instance_type": instance_class,
                    "cost": round(cost, 4),
                    "hours_elapsed": round(elapsed_hours, 2),
                }
            )

    # ----- ALB の処理 -----
    elbv2 = boto3.client("elbv2", region_name=current_region)
    elb_resp = elbv2.describe_load_balancers()
    alb_price = get_alb_price(location)

    for lb in elb_resp.get("LoadBalancers", []):
        lb_arn = lb.get("LoadBalancerArn")
        cost = alb_price * elapsed_hours
        results.append(
            {
                "instance_arn": lb_arn,
                "service_type": "alb",
                "instance_type": "N/A",
                "cost": round(cost, 4),
                "hours_elapsed": round(elapsed_hours, 2),
            }
        )

    return results


if __name__ == "__main__":
    cost_by_arn = estimate_realtime_cost_by_arn()
    print("各リソースARNごとの概算リアルタイムコスト:")
    for item in cost_by_arn:
        print(item)
