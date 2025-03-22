import boto3
from instance.ec2 import get_latest_ec2_metrics
from instance.rds import get_latest_rds_metrics
from instance.alb import get_alb_list


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
                "name": "tmp",
                "arn": f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}",
            }
        )

    rds_metrics = get_latest_rds_metrics()
    for metric in rds_metrics:
        db_name = metric['db_instance_identifier']
        metrics_data.append(
            {
                "type": "rds",
                "name": "tmp",
                "arn": f"arn:aws:rds:{region}:{account_id}:db:{db_name}",
            }
        )

    alb_list = get_alb_list()
    for alb in alb_list:
        metrics_data.append(
            {
                "type": "alb",
                "name": "tmp",
                "arn": alb["arn"],
            }
        )
    return metrics_data

if __name__ == "__main__":
    print(getInfo())
