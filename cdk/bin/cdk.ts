#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { DevopsStack } from '../lib/devops-stack';
import { ApiStack } from '../lib/api-stack';
import { PipelineStack } from '../lib/pipeline-stack';
import { DemoStack } from '../lib/demo-stack';

const app = new cdk.App();

// 共通のスタックProps
const commonProps = {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION
  },
  tags: {
    Environment: 'development',
    Project: 'progate-hackathon',
    ManagedBy: 'cdk'
  }
};

// デモスタック（EC2、RDS、ALBの作成）
new DemoStack(app, 'ProgateHackathonDemoStack', commonProps);

// DevOpsスタック（ECRリポジトリの作成）
const devopsStack = new DevopsStack(app, 'ProgateHackathonDevopsStack', commonProps);

// APIスタック（ECSサービスの作成）
const apiStack = new ApiStack(app, 'ProgateHackathonApiStack', {
  ...commonProps,
  ecrRepository: devopsStack.ecrRepository,
  domainName: 'aws-friends.k1h.dev',
  // Cloudfrontで利用する証明書はus-east-1に作成
  certificateArn: 'arn:aws:acm:us-east-1:520070710501:certificate/7e655e9a-5962-4f69-9e89-b997b3b29e61',
});

// パイプラインスタック（CI/CDパイプラインの作成）
new PipelineStack(app, 'ProgateHackathonPipelineStack', {
  ...commonProps,
  ecrRepository: devopsStack.ecrRepository,
  ecsService: apiStack.service,
  ecsCluster: apiStack.cluster,
});
