import * as cdk from 'aws-cdk-lib';
import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import * as codepipeline from 'aws-cdk-lib/aws-codepipeline';
import * as codepipeline_actions from 'aws-cdk-lib/aws-codepipeline-actions';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as iam from 'aws-cdk-lib/aws-iam';
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
    const sourceAction = new codepipeline_actions.EcrSourceAction({
      actionName: 'ECR',
      repository: props.ecrRepository,
      imageTag: 'latest',
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
          build: {
            commands: [
              'echo Creating image definitions file',
              `echo '[{"name":"ApiContainer","imageUri":"${props.ecrRepository.repositoryUri}:latest"}]' > imageDefinitions.json`,
              'cat imageDefinitions.json',
            ],
          },
        },
        artifacts: {
          files: ['imageDefinitions.json'],
        },
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
      imageFile: buildOutput.atPath('imageDefinitions.json'),
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

    // 出力の追加
    new cdk.CfnOutput(this, 'PipelineName', {
      value: pipeline.pipelineName,
      description: 'CodePipeline name',
    });
  }
}
