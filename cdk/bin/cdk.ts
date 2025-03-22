#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { DevopsStack } from '../lib/devops-stack';
import { ApiStack } from '../lib/api-stack';
import { PipelineStack } from '../lib/pipeline-stack';

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

// DevOpsスタック（ECRリポジトリの作成）
const devopsStack = new DevopsStack(app, 'ProgateHackathonDevopsStack', commonProps);

// APIスタック（ECSサービスの作成）
const apiStack = new ApiStack(app, 'ProgateHackathonApiStack', {
  ...commonProps,
  ecrRepository: devopsStack.ecrRepository,
  domainName: 'aws-friends.k1h.dev',
  certificateArn: 'arn:aws:acm:us-west-2:520070710501:certificate/55ce4986-b2e0-4780-8862-c34d1a85beb8',
});

// パイプラインスタック（CI/CDパイプラインの作成）
new PipelineStack(app, 'ProgateHackathonPipelineStack', {
  ...commonProps,
  ecrRepository: devopsStack.ecrRepository,
  ecsService: apiStack.service,
  ecsCluster: apiStack.cluster,
});
