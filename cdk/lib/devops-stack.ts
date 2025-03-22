import * as cdk from 'aws-cdk-lib';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import { Construct } from 'constructs';
import { RemovalPolicy } from 'aws-cdk-lib';

export class DevopsStack extends cdk.Stack {
  public readonly ecrRepository: ecr.Repository;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Create ECR Repository
    this.ecrRepository = new ecr.Repository(this, 'ApiRepository', {
      repositoryName: 'progate-hackathon-api',
      removalPolicy: RemovalPolicy.DESTROY, // 開発/テスト環境ではDESTROY、本番環境ではRETAINを使用
      imageScanOnPush: true, // 脆弱性スキャンを有効化
      imageTagMutability: ecr.TagMutability.MUTABLE, // タグの上書きを許可
      lifecycleRules: [
        {
          maxImageCount: 5, // 最新の5つのイメージのみを保持
          rulePriority: 1,
        },
      ],
    });

    // Output ECR Repository URL
    new cdk.CfnOutput(this, 'ApiRepositoryUrl', {
      value: this.ecrRepository.repositoryUri,
    });
    // Output ECR Repository Name
    new cdk.CfnOutput(this, 'ApiRepositoryName', {
      value: this.ecrRepository.repositoryName,
    });
  }
}
