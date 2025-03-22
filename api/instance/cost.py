import aioboto3
import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, List

# リージョンコードから Pricing API 用の location 名のマッピング例
REGION_TO_LOCATION = {
    "us-east-1": "US East (N. Virginia)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    # 必要に応じて追加
}

# 価格情報のキャッシュ
ec2_price_cache = {}
rds_price_cache = {}
alb_price_cache = {}


async def get_instance_costs(days: int = 30):
    """
    指定された日数分のインスタンスのコストを取得する関数
    Args:
        days: 取得する期間（日数）。デフォルトは30日
    Returns:
        コスト情報のリスト
    """
    # 現時点では日数は使用せずに、現在稼働中のリソースの料金を返す
    return await estimate_realtime_cost_by_arn()


async def get_ec2_price(
    instance_type: str, location: str, operating_system: str = "Linux"
) -> float:
    """
    Pricing API を用いて、EC2 の指定インスタンスタイプのオンデマンド料金（USD/時）を取得する。
    """
    # キャッシュをチェック
    cache_key = f"{instance_type}:{location}:{operating_system}"
    if cache_key in ec2_price_cache:
        return ec2_price_cache[cache_key]

    session = aioboto3.Session()
    async with session.client("pricing", region_name="us-east-1") as pricing:
        try:
            response = await pricing.get_products(
                ServiceCode="AmazonEC2",
                Filters=[
                    {
                        "Type": "TERM_MATCH",
                        "Field": "instanceType",
                        "Value": instance_type,
                    },
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
                on_demand = next(iter(price_item["terms"]["OnDemand"].values()))
                price_dimensions = next(iter(on_demand["priceDimensions"].values()))
                price_per_hour = float(price_dimensions["pricePerUnit"]["USD"])
                # キャッシュに保存
                ec2_price_cache[cache_key] = price_per_hour
                return price_per_hour
        except Exception as e:
            print(f"EC2 料金取得エラー: {e}")
        return 0.0


async def get_rds_price(
    instance_class: str, location: str, engine: str = "MySQL"
) -> float:
    """
    Pricing API を用いて、RDS の指定インスタンスクラスのオンデマンド料金（USD/時）を取得する。
    ※ ここでは Single-AZ、Linux/UNIX の場合を想定。
    """
    # キャッシュをチェック
    cache_key = f"{instance_class}:{location}:{engine}"
    if cache_key in rds_price_cache:
        return rds_price_cache[cache_key]

    session = aioboto3.Session()
    async with session.client("pricing", region_name="us-east-1") as pricing:
        try:
            response = await pricing.get_products(
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
                # キャッシュに保存
                rds_price_cache[cache_key] = price_per_hour
                return price_per_hour
        except Exception as e:
            print(f"RDS 料金取得エラー: {e}")
        return 0.0


async def get_alb_price(location: str) -> float:
    """
    Pricing API を用いて、ALB（Application Load Balancer）の基本料金（USD/時）を取得する。
    ※ ALB の料金は従量課金（LCU やリクエスト数など）もあるため、ここではベース料金のみを概算。
    """
    # キャッシュをチェック
    if location in alb_price_cache:
        return alb_price_cache[location]

    session = aioboto3.Session()
    async with session.client("pricing", region_name="us-east-1") as pricing:
        try:
            response = await pricing.get_products(
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
                # キャッシュに保存
                alb_price_cache[location] = price_per_hour
                return price_per_hour
        except Exception as e:
            print(f"ALB 料金取得エラー: {e}")
        return 0.0


async def estimate_realtime_cost_by_arn() -> List[Dict]:
    """
    現在稼働中の EC2、RDS、ALB の各リソースごとに、ARN をキーとして
    インスタンスの稼働時間に応じた概算コスト（USD）を算出します。

    EC2: 起動時間から現在までの経過時間
    RDS: インスタンス作成時間から現在までの経過時間
    ALB: ロードバランサー作成時間から現在までの経過時間

    Returns:
        List[Dict]: 各リソースごとの情報と概算コストのリスト
    """
    results = []
    now = datetime.now(timezone.utc)  # UTCで現在時刻を取得

    session = aioboto3.Session()
    async with session.client("sts") as sts:
        account_id = (await sts.get_caller_identity())["Account"]
        current_region = sts.meta.region_name or "us-east-1"
        location = REGION_TO_LOCATION.get(current_region, current_region)

    async def process_ec2():
        async with session.client("ec2", region_name=current_region) as ec2:
            # 全てのEC2インスタンスを取得（フィルタリングなし）
            ec2_resp = await ec2.describe_instances()
            for reservation in ec2_resp.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    instance_id = instance.get("InstanceId")
                    instance_type = instance.get("InstanceType")

                    # インスタンスの起動時間を取得
                    launch_time = instance.get("LaunchTime")
                    if launch_time:
                        # 起動時間から現在までの経過時間（時間単位）を計算
                        instance_hours = (now - launch_time).total_seconds() / 3600
                    else:
                        # 起動時間が取得できない場合は24時間とする
                        instance_hours = 24.0

                    hourly_rate = await get_ec2_price(instance_type, location)
                    cost = hourly_rate * instance_hours
                    instance_arn = f"arn:aws:ec2:{current_region}:{account_id}:instance/{instance_id}"
                    results.append(
                        {
                            "instance_arn": instance_arn,
                            "service_type": "ec2",
                            "instance_type": instance_type,
                            "cost": round(cost, 4),
                            "hours_elapsed": round(instance_hours, 2),
                        }
                    )

    async def process_rds():
        async with session.client("rds", region_name=current_region) as rds:
            rds_resp = await rds.describe_db_instances()
            for db_instance in rds_resp.get("DBInstances", []):
                if db_instance.get("DBInstanceStatus") == "available":
                    instance_class = db_instance.get("DBInstanceClass")
                    instance_arn = db_instance.get("DBInstanceArn")
                    if not instance_arn:
                        db_instance_identifier = db_instance.get("DBInstanceIdentifier")
                        instance_arn = f"arn:aws:rds:{current_region}:{account_id}:db:{db_instance_identifier}"

                    # インスタンスの作成時間を取得
                    instance_create_time = db_instance.get("InstanceCreateTime")
                    if instance_create_time:
                        # 作成時間から現在までの経過時間（時間単位）を計算
                        instance_hours = (
                            now - instance_create_time
                        ).total_seconds() / 3600
                    else:
                        # 作成時間が取得できない場合は24時間とする
                        instance_hours = 24.0

                    hourly_rate = await get_rds_price(instance_class, location)
                    cost = hourly_rate * instance_hours
                    results.append(
                        {
                            "instance_arn": instance_arn,
                            "service_type": "rds",
                            "instance_type": instance_class,
                            "cost": round(cost, 4),
                            "hours_elapsed": round(instance_hours, 2),
                        }
                    )

    async def process_alb():
        async with session.client("elbv2", region_name=current_region) as elbv2:
            elb_resp = await elbv2.describe_load_balancers()
            alb_price = await get_alb_price(location)
            for lb in elb_resp.get("LoadBalancers", []):
                lb_arn = lb.get("LoadBalancerArn")

                # ロードバランサーの作成時間を取得
                created_time = lb.get("CreatedTime")
                if created_time:
                    # 作成時間から現在までの経過時間（時間単位）を計算
                    lb_hours = (now - created_time).total_seconds() / 3600
                else:
                    # 作成時間が取得できない場合は24時間とする
                    lb_hours = 24.0

                cost = alb_price * lb_hours
                results.append(
                    {
                        "instance_arn": lb_arn,
                        "service_type": "alb",
                        "instance_type": "N/A",
                        "cost": round(cost, 4),
                        "hours_elapsed": round(lb_hours, 2),
                    }
                )

    # 並列で各サービスの処理を実行
    await asyncio.gather(process_ec2(), process_rds(), process_alb())

    return results


if __name__ == "__main__":
    import asyncio

    cost_by_arn = asyncio.run(estimate_realtime_cost_by_arn())
    print("各リソースARNごとの概算リアルタイムコスト:")
    for item in cost_by_arn:
        print(item)
