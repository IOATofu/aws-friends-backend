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

    // パイプライン失敗ハンドラー
    const pipelineFailureHandler = new lambda.Function(this, 'PipelineFailureHandler', {
      runtime: lambda.Runtime.NODEJS_20_X,
      handler: 'index.handler',
      code: lambda.Code.fromInline(`
        const AWS = require('aws-sdk');
        const https = require('https');
        const codepipeline = new AWS.CodePipeline();
        const dynamodb = new AWS.DynamoDB.DocumentClient();
        
        const sendDiscordNotification = async (message, color) => {
          const webhookUrl = process.env.DISCORD_WEBHOOK_URL;
          console.log('Discord Webhook URL:', webhookUrl ? '設定されています' : '設定されていません');
          
          if (!webhookUrl) {
            console.error('Discord Webhook URLが設定されていません。環境変数 DISCORD_WEBHOOK_URL を設定してください。');
            return;
          }

          if (!webhookUrl.startsWith('https://discord.com/api/webhooks/')) {
            console.error('Discord Webhook URLが不正です。正しいWebhook URLを設定してください。');
            return;
          }

          const data = JSON.stringify({
            embeds: [{
              title: 'ECSタスク更新通知',
              description: message,
              color: color,
              timestamp: new Date().toISOString()
            }]
          });

          const options = {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Content-Length': data.length,
            }
          };

          console.log('Discord通知を送信します:', {
            message,
            color,
            webhookUrl: webhookUrl.substring(0, 30) + '...' // URLの一部のみログ出力
          });

          const maxRetries = 3;
          const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));

          const sendRequest = async (retryCount = 0) => {
            console.log('Discord通知を送信します (試行回数: ' + (retryCount + 1) + '/' + maxRetries + ')');

            return new Promise((resolve, reject) => {
              const req = https.request(webhookUrl, options, (res) => {
                let responseData = '';
                res.on('data', (chunk) => { responseData += chunk; });
                res.on('end', () => {
                  const response = {
                    statusCode: res.statusCode,
                    headers: res.headers,
                    body: responseData,
                    timestamp: new Date().toISOString()
                  };

                  console.log('Discord APIレスポンス:', response);

                  if (res.statusCode >= 200 && res.statusCode < 300) {
                    console.log('Discord通知の送信に成功しました (試行回数: ' + (retryCount + 1) + ')');
                    resolve(response);
                  } else if (res.statusCode === 429 && retryCount < maxRetries) {
                    // レート制限に引っかかった場合
                    const retryAfter = parseInt(res.headers['retry-after'] || '5', 10);
                    console.log('レート制限により待機します: ' + retryAfter + '秒');
                    throw new Error('RATE_LIMIT');
                  } else {
                    console.error('Discord通知の送信に失敗しました:', {
                      statusCode: res.statusCode,
                      response: responseData,
                      attempt: retryCount + 1
                    });
                    reject(new Error('Discord API error: ' + res.statusCode));
                  }
                });
              });
              
              req.on('error', (error) => {
                console.error('Discord通知でエラーが発生しました (試行回数: ' + (retryCount + 1) + '):', {
                  error: error.message,
                  stack: error.stack
                });
                reject(error);
              });
              
              req.write(data);
              req.end();
            });
          };

          try {
            for (let i = 0; i < maxRetries; i++) {
              try {
                return await sendRequest(i);
              } catch (error) {
                if (error.message === 'RATE_LIMIT') {
                  await delay(5000); // 5秒待機
                  continue;
                }
                if (i === maxRetries - 1) throw error;
                await delay(1000 * Math.pow(2, i)); // 指数バックオフ
              }
            }
          } catch (error) {
            console.error('Discord通知の送信が最終的に失敗しました:', error);
            throw error;
          }
        };
        
        exports.handler = async (event) => {
          const pipelineName = event.detail.pipeline;
          const executionId = event.detail['execution-id'];
          const state = event.detail.state;
          
          console.log(\`Pipeline \${pipelineName} execution \${executionId} state: \${state}\`);
          
          // 成功時の通知
          if (state === 'SUCCEEDED') {
            await sendDiscordNotification(
              \`✅ パイプライン \${pipelineName} のタスク更新が成功しました\n実行ID: \${executionId}\`,
              0x00ff00 // 緑色
            );
            return;
          }
          
          // 失敗時の処理
          const params = {
            TableName: process.env.FAILURE_COUNT_TABLE,
            Key: { pipelineName: pipelineName }
          };
          
          const data = await dynamodb.get(params).promise();
          const failureCount = (data.Item ? data.Item.count : 0) + 1;
          
          console.log(\`Current failure count: \${failureCount}\`);
          
          await dynamodb.put({
            TableName: process.env.FAILURE_COUNT_TABLE,
            Item: { pipelineName: pipelineName, count: failureCount }
          }).promise();
          
          // Discord通知（失敗）
          await sendDiscordNotification(
            \`❌ パイプライン \${pipelineName} のタスク更新が失敗しました\n実行ID: \${executionId}\n失敗回数: \${failureCount}\`,
            0xff0000 // 赤色
          );
          
          if (failureCount >= parseInt(process.env.MAX_FAILURES)) {
            console.log(\`Disabling pipeline \${pipelineName} after \${failureCount} failures\`);
            
            await codepipeline.updatePipeline({
              pipeline: {
                name: pipelineName,
                disabled: true
              }
            }).promise();
            
            console.log(\`Pipeline \${pipelineName} has been disabled\`);
            
            await dynamodb.put({
              TableName: process.env.FAILURE_COUNT_TABLE,
              Item: { pipelineName: pipelineName, count: 0 }
            }).promise();
            
            // パイプライン無効化の通知
            await sendDiscordNotification(
              \`⚠️ パイプライン \${pipelineName} が連続失敗により無効化されました\n実行ID: \${executionId}\`,
              0xffa500 // オレンジ色
            );
          }
        }
      `),
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

    // パイプライン失敗時のイベントルール作成
    const buildPipelineFailureRule = new events.Rule(this, 'BuildPipelineFailureRule', {
      eventPattern: {
        source: ['aws.codepipeline'],
        detailType: ['CodePipeline Pipeline Execution State Change'],
        detail: {
          state: ['FAILED'],
          pipeline: [buildPipeline.pipelineName]
        }
      }
    });

    const deployPipelineFailureRule = new events.Rule(this, 'DeployPipelineFailureRule', {
      eventPattern: {
        source: ['aws.codepipeline'],
        detailType: ['CodePipeline Pipeline Execution State Change'],
        detail: {
          state: ['FAILED'],
          pipeline: [deployPipeline.pipelineName]
        }
      }
    });
    // パイプライン成功時のイベントルール作成
    const buildPipelineSuccessRule = new events.Rule(this, 'BuildPipelineSuccessRule', {
      eventPattern: {
        source: ['aws.codepipeline'],
        detailType: ['CodePipeline Pipeline Execution State Change'],
        detail: {
          state: ['SUCCEEDED'],
          pipeline: [buildPipeline.pipelineName]
        }
      }
    });

    const deployPipelineSuccessRule = new events.Rule(this, 'DeployPipelineSuccessRule', {
      eventPattern: {
        source: ['aws.codepipeline'],
        detailType: ['CodePipeline Pipeline Execution State Change'],
        detail: {
          state: ['SUCCEEDED'],
          pipeline: [deployPipeline.pipelineName]
        }
      }
    });

    buildPipelineFailureRule.addTarget(new targets.LambdaFunction(pipelineFailureHandler));
    deployPipelineFailureRule.addTarget(new targets.LambdaFunction(pipelineFailureHandler));
    buildPipelineSuccessRule.addTarget(new targets.LambdaFunction(pipelineFailureHandler));
    deployPipelineSuccessRule.addTarget(new targets.LambdaFunction(pipelineFailureHandler));

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
