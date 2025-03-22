import * as cdk from 'aws-cdk-lib';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as certificatemanager from 'aws-cdk-lib/aws-certificatemanager';
import { Construct } from 'constructs';

interface ApiStackProps extends cdk.StackProps {
  ecrRepository: ecr.IRepository;
  domainName?: string;
  certificateArn?: string;
}

export class ApiStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: ApiStackProps) {
    super(scope, id, props);

    // VPCの作成
    const vpc = new ec2.Vpc(this, 'ApiVpc', {
      maxAzs: 2,
      natGateways: 1,
    });

    // ECSクラスターの作成
    const cluster = new ecs.Cluster(this, 'ApiCluster', {
      vpc,
      clusterName: 'progate-hackathon-cluster',
    });

    // Fargateタスク定義
    const taskDefinition = new ecs.FargateTaskDefinition(this, 'ApiTaskDef', {
      memoryLimitMiB: 512,
      cpu: 256,
    });

    // コンテナの追加
    taskDefinition.addContainer('ApiContainer', {
      image: ecs.ContainerImage.fromEcrRepository(props.ecrRepository, 'latest'),
      portMappings: [{ containerPort: 8080 }], // FastAPIのデフォルトポート
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: 'ApiContainer' }),
    });

    // Fargateサービスの作成
    const service = new ecs.FargateService(this, 'ApiService', {
      cluster,
      taskDefinition,
      desiredCount: 2,
      assignPublicIp: false,
      minHealthyPercent: 100, // タスク更新中もサービスを100%稼働させる
    });

    // ALBの作成
    const alb = new elbv2.ApplicationLoadBalancer(this, 'ApiAlb', {
      vpc,
      internetFacing: true,
    });

    // セキュリティグループの設定
    const albSg = new ec2.SecurityGroup(this, 'AlbSecurityGroup', {
      vpc,
      description: 'Security group for ALB',
      allowAllOutbound: true,
    });

    // HTTP & HTTPSトラフィックを許可
    albSg.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(80),
      'Allow HTTP traffic'
    );
    albSg.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(443),
      'Allow HTTPS traffic'
    );

    const serviceSg = new ec2.SecurityGroup(this, 'ServiceSecurityGroup', {
      vpc,
      description: 'Security group for Fargate service',
      allowAllOutbound: true,
    });

    serviceSg.addIngressRule(
      albSg,
      ec2.Port.tcp(8080),
      'Allow traffic from ALB'
    );

    // セキュリティグループをALBとサービスに適用
    alb.addSecurityGroup(albSg);
    service.connections.addSecurityGroup(serviceSg);

    // HTTPリスナーの作成（HTTPSにリダイレクト）
    const httpListener = alb.addListener('HttpListener', {
      port: 80,
      defaultAction: elbv2.ListenerAction.redirect({
        protocol: 'HTTPS',
        port: '443',
        permanent: true,
      }),
    });

    // HTTPSリスナーの作成
    const httpsListener = alb.addListener('HttpsListener', {
      port: 443,
      protocol: elbv2.ApplicationProtocol.HTTPS,
      certificates: [
        certificatemanager.Certificate.fromCertificateArn(
          this,
          'Certificate',
          props.certificateArn as string
        ),
      ],
    });

    // メインのターゲットグループを作成
    const targetGroup = httpsListener.addTargets('ApiTarget', {
      port: 8080,
      targets: [service],
      healthCheck: {
        path: '/health',
        unhealthyThresholdCount: 2,
        healthyThresholdCount: 5,
        interval: cdk.Duration.seconds(30),
      },
      deregistrationDelay: cdk.Duration.seconds(30),
    });

    // OPTIONSリクエスト用のリスナールールを追加
    httpsListener.addAction('OptionsRule', {
      priority: 1,
      conditions: [
        elbv2.ListenerCondition.httpHeader('Access-Control-Request-Method', ['*']),
      ],
      action: elbv2.ListenerAction.fixedResponse(200, {
        contentType: 'text/plain',
        messageBody: '',
      }),
    });

    // 出力の追加
    new cdk.CfnOutput(this, 'AlbEndpoint', {
      value: alb.loadBalancerDnsName,
      description: 'Application Load Balancer endpoint',
      exportName: 'AlbEndpoint',
    });

    if (props.domainName) {
      new cdk.CfnOutput(this, 'CustomDomain', {
        value: props.domainName,
        description: 'Custom domain name',
      });
    }
  }
}
