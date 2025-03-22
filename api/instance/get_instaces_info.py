import boto3
from .ec2 import get_latest_ec2_metrics
from .rds import get_latest_rds_metrics
from .alb import get_latest_alb_metrics
from .calc_state import calc_ec2, calc_rds,calc_alb


def getInfo():
    metrics_data = []
    # セッションからリージョンを取得
    session = boto3.Session()
    region = session.region_name

    # STS クライアントを作成してアカウントIDを取得
    sts_client = boto3.client('sts')
    response = sts_client.get_caller_identity()
    account_id = response['Account']

    ec2_metrics = get_latest_ec2_metrics()
    for metric in ec2_metrics:
        instance_id = metric['instance_id']
        metrics_data.append(
            {
                "type": "ec2",
                "arn": f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}",
                "state": calc_ec2(metric["cpu_utilization"]),
            }
        )

    rds_metrics = get_latest_rds_metrics()
    for metric in rds_metrics:
        db_name = metric['db_instance_identifier']
        metrics_data.append(
            {
                "type": "rds",
                "arn": f"arn:aws:rds:{region}:{account_id}:db:{db_name}",
                "state": calc_rds(metric["metrics"]["cpu_utilization"]),
            }
        )

    alb_metrics = get_latest_alb_metrics()
    for metric in alb_metrics:
        metrics_data.append(
            {
                "type": "alb",
                "arn": metric["load_balancer_arn"],
                "state": calc_alb(),
            }
        )
    return metrics_data

if __name__ == "__main__":
    print(getInfo())
