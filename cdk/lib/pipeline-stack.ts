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
import { Construct } from 'constructs';

interface PipelineStackProps extends cdk.StackProps {
  ecrRepository: ecr.IRepository;
  ecsService: ecs.FargateService;
  ecsCluster: ecs.Cluster;
}

export class PipelineStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: PipelineStackProps) {
    super(scope, id, props);

    // パイプラインの作成
    const pipeline = new codepipeline.Pipeline(this, 'DeployPipeline', {
      pipelineName: 'EcsDeployPipeline',
    });

    // ソースステージ（ECRソース）
    const sourceOutput = new codepipeline.Artifact();

    // ECRリポジトリからイメージダイジェストを取得するLambda関数
    const getImageDigestLambda = new lambda.Function(this, 'GetImageDigestLambda', {
      runtime: lambda.Runtime.NODEJS_18_X,
      handler: 'index.handler',
      code: lambda.Code.fromInline(`
        const AWS = require('aws-sdk');
        const ecr = new AWS.ECR();
        
        exports.handler = async () => {
          const params = {
            repositoryName: process.env.REPOSITORY_NAME,
            imageIds: [{ imageTag: 'latest' }]
          };
          
          try {
            const data = await ecr.describeImages(params).promise();
            if (data.imageDetails && data.imageDetails.length > 0) {
              const imageDigest = data.imageDetails[0].imageDigest;
              console.log('Image digest:', imageDigest);
              return {
                imageDigest: imageDigest
              };
            }
            throw new Error('No image found');
          } catch (error) {
            console.error('Error:', error);
            throw error;
          }
        }
      `),
      environment: {
        REPOSITORY_NAME: props.ecrRepository.repositoryName
      },
      timeout: cdk.Duration.seconds(30)
    });

    // Lambda関数にECRの読み取り権限を付与
    props.ecrRepository.grantRead(getImageDigestLambda);

    // ECRソースアクション（ダイジェストを使用）
    const sourceAction = new codepipeline_actions.EcrSourceAction({
      actionName: 'ECR',
      repository: props.ecrRepository,
      imageTag: 'latest', // 初期取得用にlatestを使用
      output: sourceOutput,
    });

    // イメージ定義ファイルを生成するCodeBuildプロジェクト
    const buildProject = new codebuild.PipelineProject(this, 'ImageDefinitionsProject', {
      environment: {
        buildImage: codebuild.LinuxBuildImage.STANDARD_5_0,
        privileged: true,
      },
      buildSpec: codebuild.BuildSpec.fromObject({
        version: '0.2',
        phases: {
          pre_build: {
            commands: [
              'echo Getting image digest from ECR...',
              'IMAGE_DIGEST=$(aws ecr describe-images --repository-name $(echo $ECR_REPOSITORY_URI | cut -d/ -f2) --image-ids imageTag=latest --query "imageDetails[0].imageDigest" --output text)',
              'echo Image digest: $IMAGE_DIGEST',
            ]
          },
          build: {
            commands: [
              'echo Creating image definitions file with digest',
              'echo \'[{"name":"ApiContainer","imageUri":"\'$ECR_REPOSITORY_URI\'@\'$IMAGE_DIGEST\'"}]\' > imageDefinitions.json',
              'cat imageDefinitions.json',
            ],
          },
        },
        artifacts: {
          files: ['imageDefinitions.json'],
        },
        env: {
          variables: {
            ECR_REPOSITORY_URI: props.ecrRepository.repositoryUri
          }
        }
      }),
    });

    const buildOutput = new codepipeline.Artifact();
    const buildAction = new codepipeline_actions.CodeBuildAction({
      actionName: 'CreateImageDefinitions',
      project: buildProject,
      input: sourceOutput,
      outputs: [buildOutput],
    });

    // ECSデプロイアクション
    const deployAction = new codepipeline_actions.EcsDeployAction({
      actionName: 'Deploy',
      service: props.ecsService,
      imageFile: buildOutput.atPath('imageDefinitions.json')
    });

    // パイプラインにステージを追加
    pipeline.addStage({
      stageName: 'Source',
      actions: [sourceAction],
    });

    pipeline.addStage({
      stageName: 'Build',
      actions: [buildAction],
    });

    pipeline.addStage({
      stageName: 'Deploy',
      actions: [deployAction],
    });

    // パイプラインが一定回数失敗したら自動的に停止する設定

    // DynamoDBテーブルを作成して失敗回数を追跡
    const failureCountTable = new dynamodb.Table(this, 'PipelineFailureCountTable', {
      partitionKey: { name: 'pipelineName', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY
    });

    // CloudWatchイベントルールを作成
    const pipelineFailureHandler = new lambda.Function(this, 'PipelineFailureHandler', {
      runtime: lambda.Runtime.NODEJS_14_X,
      handler: 'index.handler',
      code: lambda.Code.fromInline(`
        const AWS = require('aws-sdk');
        const codepipeline = new AWS.CodePipeline();
        const dynamodb = new AWS.DynamoDB.DocumentClient();
        
        exports.handler = async (event) => {
          const pipelineName = event.detail.pipeline;
          const executionId = event.detail['execution-id'];
          
          console.log(\`Pipeline \${pipelineName} execution \${executionId} failed\`);
          
          // DynamoDBから失敗回数を取得
          const params = {
            TableName: process.env.FAILURE_COUNT_TABLE,
            Key: { pipelineName: pipelineName }
          };
          
          const data = await dynamodb.get(params).promise();
          const failureCount = (data.Item ? data.Item.count : 0) + 1;
          
          console.log(\`Current failure count: \${failureCount}\`);
          
          // 失敗回数を更新
          await dynamodb.put({
            TableName: process.env.FAILURE_COUNT_TABLE,
            Item: { pipelineName: pipelineName, count: failureCount }
          }).promise();
          
          // 指定回数以上失敗した場合、パイプラインを無効化
          if (failureCount >= parseInt(process.env.MAX_FAILURES)) {
            console.log(\`Disabling pipeline \${pipelineName} after \${failureCount} failures\`);
            
            await codepipeline.updatePipeline({
              pipeline: {
                name: pipelineName,
                // パイプラインを無効化するための設定
                disabled: true
              }
            }).promise();
            
            console.log(\`Pipeline \${pipelineName} has been disabled\`);
            
            // 失敗カウントをリセット
            await dynamodb.put({
              TableName: process.env.FAILURE_COUNT_TABLE,
              Item: { pipelineName: pipelineName, count: 0 }
            }).promise();
          }
        }
      `),
      environment: {
        FAILURE_COUNT_TABLE: failureCountTable.tableName,
        MAX_FAILURES: '3' // 最大失敗回数
      },
      timeout: cdk.Duration.seconds(30)
    });

    // Lambda関数にCodePipelineの更新権限を付与
    pipelineFailureHandler.addToRolePolicy(new iam.PolicyStatement({
      actions: ['codepipeline:UpdatePipeline', 'codepipeline:GetPipeline'],
      resources: [pipeline.pipelineArn]
    }));

    // DynamoDBテーブルへのアクセス権限を付与
    failureCountTable.grantReadWriteData(pipelineFailureHandler);

    // CloudWatchイベントルールを作成
    const pipelineFailureRule = new events.Rule(this, 'PipelineFailureRule', {
      eventPattern: {
        source: ['aws.codepipeline'],
        detailType: ['CodePipeline Pipeline Execution State Change'],
        detail: {
          state: ['FAILED'],
          pipeline: [pipeline.pipelineName]
        }
      }
    });

    // Lambda関数をイベントターゲットとして追加
    pipelineFailureRule.addTarget(new targets.LambdaFunction(pipelineFailureHandler));

    // 出力の追加
    new cdk.CfnOutput(this, 'PipelineName', {
      value: pipeline.pipelineName,
      description: 'CodePipeline name',
    });
  }
}
