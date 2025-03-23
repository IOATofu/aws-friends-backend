import * as dotenv from 'dotenv';
import * as path from 'path';
import * as cdk from 'aws-cdk-lib';

// .envファイルを読み込む
dotenv.config({
  path: path.resolve(__dirname, '../.env')
});
import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import * as codepipeline_actions from 'aws-cdk-lib/aws-codepipeline-actions';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as codestarconnections from 'aws-cdk-lib/aws-codestarconnections';
import { Construct } from 'constructs';

interface PipelineStackProps extends cdk.StackProps {
  ecrRepository: ecr.IRepository;
  ecsService: ecs.FargateService;
  ecsCluster: ecs.Cluster;
}

export class PipelineStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: PipelineStackProps) {
    super(scope, id, props);

    // GitHub接続の作成
    const githubConnection = new codestarconnections.CfnConnection(this, 'GitHubConnection', {
      connectionName: 'GitHubConnection',
      providerType: 'GitHub',
    });

    // ビルドパイプラインの作成
    const buildPipeline = new codepipeline.Pipeline(this, 'BuildPipeline', {
      pipelineName: 'EcsBuildPipeline',
    });

    // ソースステージ（GitHubソース）
    const sourceOutput = new codepipeline.Artifact();
    const sourceAction = new codepipeline_actions.CodeStarConnectionsSourceAction({
      actionName: 'GitHub',
      owner: 'IOATofu',
      repo: 'aws-friends-backend',
      branch: 'main',
      connectionArn: githubConnection.attrConnectionArn,
      output: sourceOutput,
      triggerOnPush: true,
      // 監視するファイルパスを指定
      codeBuildCloneOutput: true,
    });

    const pushFilterJson = {
      Branches: {
        Includes: ['main'],
      },
      FilePaths: {
        Includes: ['api/*', 'docker/api/*'],
      },
    };
    const cfnPipeline = buildPipeline.node.defaultChild as codepipeline.CfnPipeline;
    // Triggers プロパティを上書き
    cfnPipeline.addPropertyOverride('Triggers', [
      {
        GitConfiguration: {
          Push: [pushFilterJson],
          SourceActionName: sourceAction.actionProperties.actionName,
        },
        ProviderType: 'CodeStarSourceConnection',
      },
    ]);

    // mainブランチのpushのみを検知するイベントルール
    const sourceRule = new events.Rule(this, 'SourceRule', {
      eventPattern: {
        source: ['aws.codestar-connections'],
        detailType: ['CodeStarSourceConnection Repository State Change'],
        detail: {
          referenceType: ['branch'],
          referenceName: ['main'],
          repositoryName: ['aws-friends-backend'],
          path: ['api/*', 'docker/api/*'],
          state: ['push']
        }
      }
    });

    // ビルドプロジェクトの設定を更新
    const buildProject = new codebuild.PipelineProject(this, 'BuildProject', {
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_5_0,
        privileged: true,
      },
      cache: codebuild.Cache.local(
        codebuild.LocalCacheMode.DOCKER_LAYER,
        codebuild.LocalCacheMode.CUSTOM
      ),
      buildSpec: codebuild.BuildSpec.fromObject({
        version: '0.2',
        phases: {
          pre_build: {
            commands: [
              'echo Checking if API files changed...',
              'git diff --name-only HEAD^ HEAD > changes.txt',
              'if ! grep -q -E "^(api/|docker/api/)" changes.txt; then echo "No changes in API files. Skipping build."; exit 0; fi',
              'echo API files changed. Proceeding with build...',
              'echo Logging in to Amazon ECR...',
              'aws ecr get-login-password --region ${AWS_DEFAULT_REGION} | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com',
              'REPOSITORY_URI=${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com/${ECR_REPOSITORY_NAME}',
              'IMAGE_TAG=$(echo $CODEBUILD_RESOLVED_SOURCE_VERSION | cut -c 1-7)'
            ]
          },
          build: {
            commands: [
              'echo Build started on `date`',
              'echo Building the Docker image...',
              'docker build -t ${REPOSITORY_URI}:${IMAGE_TAG} -f docker/api/Dockerfile .',
              'docker tag ${REPOSITORY_URI}:${IMAGE_TAG} ${REPOSITORY_URI}:latest'
            ]
          },
          post_build: {
            commands: [
              'echo Build completed on `date`',
              'echo Pushing the Docker images...',
              'docker push ${REPOSITORY_URI}:${IMAGE_TAG}',
              'docker push ${REPOSITORY_URI}:latest'
            ]
          }
        },
        cache: {
          paths: [
            '/root/.cache/pip/**/*',
            '/root/.docker/buildkit'
          ]
        }
      }),
      environmentVariables: {
        'AWS_ACCOUNT_ID': {
          value: process.env.CDK_DEFAULT_ACCOUNT || this.account
        },
        'AWS_DEFAULT_REGION': {
          value: process.env.CDK_DEFAULT_REGION || this.region
        },
        'ECR_REPOSITORY_NAME': {
          value: props.ecrRepository.repositoryName
        }
      }
    });

    // イベントルールのターゲットとしてビルドパイプラインを追加
    sourceRule.addTarget(new targets.CodePipeline(buildPipeline));

    props.ecrRepository.grantPullPush(buildProject);

    const buildAction = new codepipeline_actions.CodeBuildAction({
      actionName: 'BuildAndPushImage',
      project: buildProject,
      input: sourceOutput,
    });

    // ビルドパイプラインのステージ設定
    buildPipeline.addStage({ stageName: 'Source', actions: [sourceAction] });
    buildPipeline.addStage({ stageName: 'Build', actions: [buildAction] });

    // デプロイパイプラインの作成
    const deployPipeline = new codepipeline.Pipeline(this, 'DeployPipeline', {
      pipelineName: 'EcsDeployPipeline',
    });

    // デプロイ用のビルドプロジェクト
    const deployProject = new codebuild.PipelineProject(this, 'DeployProject', {
      buildSpec: codebuild.BuildSpec.fromObject({
        version: '0.2',
        phases: {
          build: {
            commands: [
              'echo Creating image definitions file...',
              'echo "[{\\"name\\":\\"ApiContainer\\",\\"imageUri\\":\\"${ECR_REPOSITORY_URI}:latest\\"}]" > imageDefinitions.json',
              'cat imageDefinitions.json'
            ]
          }
        },
        artifacts: {
          files: [
            'imageDefinitions.json'
          ]
        }
      }),
      environmentVariables: {
        'ECR_REPOSITORY_URI': {
          value: props.ecrRepository.repositoryUri
        }
      }
    });

    const deployOutput = new codepipeline.Artifact();

    // ECSデプロイアクション
    const deployAction = new codepipeline_actions.EcsDeployAction({
      actionName: 'Deploy',
      service: props.ecsService,
      imageFile: deployOutput.atPath('imageDefinitions.json'),
    });

    // デプロイパイプラインのステージ設定
    const ecrSourceOutput = new codepipeline.Artifact();
    const ecrSourceAction = new codepipeline_actions.EcrSourceAction({
      actionName: 'ECR',
      repository: props.ecrRepository,
      imageTag: 'latest',
      output: ecrSourceOutput,
    });

    const createImageDefAction = new codepipeline_actions.CodeBuildAction({
      actionName: 'CreateImageDefinitions',
      project: deployProject,
      input: ecrSourceOutput,
      outputs: [deployOutput],
    });

    // ステージの追加
    deployPipeline.addStage({ stageName: 'Source', actions: [ecrSourceAction] });
    deployPipeline.addStage({ stageName: 'CreateImageDef', actions: [createImageDefAction] });
    deployPipeline.addStage({ stageName: 'Deploy', actions: [deployAction] });

    // ECRイメージ更新時のイベントルール作成
    const ecrImageRule = new events.Rule(this, 'EcrImageUpdateRule', {
      eventPattern: {
        source: ['aws.ecr'],
        detailType: ['ECR Image Action'],
        detail: {
          'action-type': ['PUSH'],
          'image-tag': ['latest'],
          'repository-name': [props.ecrRepository.repositoryName],
          result: ['SUCCESS']
        }
      }
    });

    // デプロイパイプラインの実行権限を持つロールを作成
    const pipelineExecutionRole = new iam.Role(this, 'PipelineExecutionRole', {
      assumedBy: new iam.ServicePrincipal('events.amazonaws.com'),
    });

    // パイプライン実行権限を付与
    pipelineExecutionRole.addToPolicy(new iam.PolicyStatement({
      actions: ['codepipeline:StartPipelineExecution'],
      resources: [deployPipeline.pipelineArn],
    }));

    // イベントルールのターゲットとしてデプロイパイプラインを追加
    ecrImageRule.addTarget(new targets.CodePipeline(deployPipeline));

    // パイプライン失敗監視用のDynamoDBテーブル
    const failureCountTable = new dynamodb.Table(this, 'PipelineFailureCountTable', {
      partitionKey: { name: 'pipelineName', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY
    });

    // パイプライン状態通知ハンドラー
    const pipelineFailureHandler = new lambda.Function(this, 'PipelineStateHandler', {
      runtime: lambda.Runtime.NODEJS_20_X,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('lambda/pipeline-notification'),
      environment: {
        FAILURE_COUNT_TABLE: failureCountTable.tableName,
        MAX_FAILURES: '3',
        DISCORD_WEBHOOK_URL: process.env.DISCORD_WEBHOOK_URL || '',
        DISCORD_MENTION_USER_ID: process.env.DISCORD_MENTION_USER_ID || ''
      },
      description: 'Lambda function for pipeline state notifications. Required environment variables: DISCORD_WEBHOOK_URL, DISCORD_MENTION_USER_ID',
      timeout: cdk.Duration.seconds(30)
    });

    // Lambda関数にCodePipelineの更新権限を付与
    pipelineFailureHandler.addToRolePolicy(new iam.PolicyStatement({
      actions: ['codepipeline:UpdatePipeline', 'codepipeline:GetPipeline'],
      resources: [buildPipeline.pipelineArn, deployPipeline.pipelineArn]
    }));

    // DynamoDBテーブルへのアクセス権限を付与
    failureCountTable.grantReadWriteData(pipelineFailureHandler);

    // パイプラインの状態変更を監視するイベントルール
    const pipelineStateRule = new events.Rule(this, 'PipelineStateRule', {
      eventPattern: {
        source: ['aws.codepipeline'],
        detailType: ['CodePipeline Pipeline Execution State Change'],
        detail: {
          state: ['SUCCEEDED', 'FAILED'],
          pipeline: [buildPipeline.pipelineName, deployPipeline.pipelineName]
        }
      }
    });

    // Lambda関数をターゲットとして追加
    pipelineStateRule.addTarget(new targets.LambdaFunction(pipelineFailureHandler));

    // パイプライン名の出力
    new cdk.CfnOutput(this, 'BuildPipelineName', {
      value: buildPipeline.pipelineName,
      description: 'Build CodePipeline name',
    });

    new cdk.CfnOutput(this, 'DeployPipelineName', {
      value: deployPipeline.pipelineName,
      description: 'Deploy CodePipeline name',
    });
  }
}
