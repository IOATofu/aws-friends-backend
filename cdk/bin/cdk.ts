#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { DevopsStack } from '../lib/devops-stack';
import { ApiStack } from '../lib/api-stack';

const app = new cdk.App();

// DevOpsスタック
const devopsStack = new DevopsStack(app, 'ProgateHackathonDevopsStack', {
  /* 環境を指定しない場合、このスタックは環境に依存しません。
   * アカウント/リージョンに依存する機能やコンテキストの参照は機能しませんが、
   * 生成されたテンプレートはどこにでもデプロイできます。 */

  // 現在のCLI設定から暗黙的に決定されるAWSアカウントとリージョンを使用
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION
  },

  // タグを追加（オプション）
  tags: {
    Environment: 'development',
    Project: 'progate-hackathon',
    ManagedBy: 'cdk'
  }
});

// APIスタック
new ApiStack(app, 'ProgateHackathonApiStack', {
  ecrRepository: devopsStack.ecrRepository,
  domainName: 'aws-friends.k1h.dev',
  // コンソール上で作業して、AWS Certificate Managerで取得した証明書のARNを指定
  certificateArn: 'arn:aws:acm:us-west-2:520070710501:certificate/55ce4986-b2e0-4780-8862-c34d1a85beb8',
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION
  },
  tags: {
    Environment: 'development',
    Project: 'progate-hackathon',
    ManagedBy: 'cdk'
  }
});
