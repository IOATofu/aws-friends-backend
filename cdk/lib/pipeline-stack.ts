import * as cdk from 'aws-cdk-lib';
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
    });

    // Dockerイメージをビルドしてプッシュするビルドプロジェクト
    const buildProject = new codebuild.PipelineProject(this, 'BuildProject', {
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_5_0,
        privileged: true,
      },
      cache: codebuild.Cache.local(
        codebuild.LocalCacheMode.DOCKER_LAYER,
        codebuild.LocalCacheMode.CUSTOM
      ),
      buildSpec: codebuild.BuildSpec.fromSourceFilename('buildspec-build.yml'),
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

    props.ecrRepository.grantPullPush(buildProject);

    const buildAction = new codepipeline_actions.CodeBuildAction({
      actionName: 'BuildAndPushImage',
      project: buildProject,
      input: sourceOutput,
    });

    // ビルドパイプラインにステージを追加
    buildPipeline.addStage({
      stageName: 'Source',
      actions: [sourceAction],
    });

    buildPipeline.addStage({
      stageName: 'Build',
      actions: [buildAction],
    });

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

    // デプロイパイプラインのECRソース
    const ecrSourceOutput = new codepipeline.Artifact();
    const ecrSourceAction = new codepipeline_actions.EcrSourceAction({
      actionName: 'ECR',
      repository: props.ecrRepository,
      imageTag: 'latest',
      output: ecrSourceOutput,
    });

    // デプロイパイプラインにステージを追加
    deployPipeline.addStage({
      stageName: 'Source',
      actions: [ecrSourceAction],
    });

    // createImageDefActionのinputをECRソースに変更
    const createImageDefAction = new codepipeline_actions.CodeBuildAction({
      actionName: 'CreateImageDefinitions',
      project: deployProject,
      input: ecrSourceOutput,
      outputs: [deployOutput],
    });

    deployPipeline.addStage({
      stageName: 'CreateImageDef',
      actions: [createImageDefAction],
    });

    deployPipeline.addStage({
      stageName: 'Deploy',
      actions: [deployAction],
    });

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
        DISCORD_WEBHOOK_URL: process.env.DISCORD_WEBHOOK_URL || ''
      },
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

    // 出力の追加
    // 出力の追加
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
