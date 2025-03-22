#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { DevopsStack } from '../lib/devops-stack';

const app = new cdk.App();
new DevopsStack(app, 'ProgateHackathonStack', {
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
