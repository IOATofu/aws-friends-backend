from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import ECS, ECR, Fargate
from diagrams.aws.network import (
    VPC,
    PrivateSubnet,
    PublicSubnet,
    InternetGateway,
    NATGateway,
    ELB,
    CloudFront,
)
from diagrams.aws.security import IAM, CertificateManager
from diagrams.aws.storage import S3
from diagrams.aws.general import Users
from diagrams.aws.devtools import Codebuild, Codepipeline
from diagrams.onprem.vcs import Github
from diagrams.aws.ml import Bedrock
from diagrams.aws.management import Cloudwatch
from diagrams.aws.cost import CostExplorer
from diagrams.onprem.client import Client

# ダイアグラムを作成
with Diagram(
    "AWS Architecture", show=True, filename="aws_architecture", outformat="png"
):

    # ユーザーは削除（フィードバックに基づく）

    # Unity クライアント
    unity = Client("Unity\nクライアント")

    # Certificate Manager
    acm = CertificateManager("Certificate\nManager")

    # CloudFront
    cloudfront = CloudFront("CloudFront\nディストリビューション")

    # S3バケット（アクセスログ用）
    logs_bucket = S3("CloudFront\nアクセスログ")

    with Cluster("VPC"):
        # インターネットゲートウェイ
        igw = InternetGateway("Internet\nGateway")

        # ALB
        alb = ELB("Application\nLoad Balancer")

        with Cluster("Public Subnets"):
            # NATゲートウェイ
            nat = NATGateway("NAT\nGateway")

            # パブリックサブネット
            public_subnet1 = PublicSubnet("Public\nSubnet AZ1")
            public_subnet2 = PublicSubnet("Public\nSubnet AZ2")

        with Cluster("Private Subnets"):
            # プライベートサブネット
            private_subnet1 = PrivateSubnet("Private\nSubnet AZ1")
            private_subnet2 = PrivateSubnet("Private\nSubnet AZ2")

            with Cluster("ECS Cluster"):
                # ECSクラスター
                ecs_cluster = ECS("ECS\nCluster")

                # Fargateサービス
                fargate = Fargate("Fargate\nService")

                # ECSサービス（ECSServiceクラスが利用できないため、ECSで代用）
                ecs_service = ECS("ECS Service\n(2 tasks)")

    # IAMロール
    iam_role = IAM(
        "IAM Role\n(CloudWatch, EC2, ALB,\nRDS, Cost Explorer,\nPricing API, Bedrock)"
    )

    # ECRリポジトリ
    ecr = ECR("ECR\nRepository")

    # GitHub リポジトリ
    github = Github("GitHub\nRepository")

    # AWS Bedrock
    bedrock = Bedrock("Amazon Bedrock")

    # CloudWatch
    cloudwatch = Cloudwatch("CloudWatch\nメトリクス")

    # Cost Explorer
    costexplorer = CostExplorer("Cost Explorer &\nPricing API")

    # CI/CDパイプライン
    with Cluster("CI/CD Pipeline"):
        # CodeBuild
        build = Codebuild("CodeBuild")

        # CodePipeline
        pipeline = Codepipeline("CodePipeline")

    # 接続関係を定義
    cloudfront >> alb
    cloudfront >> logs_bucket

    igw >> alb
    alb >> ecs_service

    nat >> Edge(color="brown", style="dashed") >> igw

    private_subnet1 - ecs_service
    private_subnet2 - ecs_service

    ecs_service >> fargate
    ecs_service >> ecs_cluster

    ecs_service << ecr
    ecs_service >> Edge(color="red", style="dotted") >> iam_role

    # パイプラインの接続関係
    github >> Edge(label="Push") >> build
    build >> Edge(label="Build") >> ecr
    ecr >> Edge(label="Trigger") >> pipeline
    pipeline >> Edge(label="Deploy") >> ecs_service

    # 外部サービスとの接続
    ecs_service >> Edge(label="API呼び出し", style="dashed") >> bedrock
    ecs_service >> Edge(label="メトリクス収集", style="dashed") >> cloudwatch
    ecs_service >> Edge(label="コスト情報取得", style="dashed") >> costexplorer

    # Unityクライアントとの接続
    unity >> Edge(label="API呼び出し") >> cloudfront

    # Certificate Managerとの接続
    acm >> Edge(label="SSL証明書") >> cloudfront
