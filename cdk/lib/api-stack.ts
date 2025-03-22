import * as cdk from 'aws-cdk-lib';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as certificatemanager from 'aws-cdk-lib/aws-certificatemanager';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

interface ApiStackProps extends cdk.StackProps {
  ecrRepository?: ecr.IRepository;
  domainName?: string;
  certificateArn?: string;
}

export class ApiStack extends cdk.Stack {
  public readonly service: ecs.FargateService;
  public readonly cluster: ecs.Cluster;
  private taskDefinition: ecs.FargateTaskDefinition;
  private ecrRepository?: ecr.IRepository;

  constructor(scope: Construct, id: string, props: ApiStackProps) {
    super(scope, id, props);

    this.ecrRepository = props.ecrRepository;

    // VPCの作成
    const vpc = new ec2.Vpc(this, 'ApiVpc', {
      maxAzs: 2,
      natGateways: 1,
    });

    // ECSクラスターの作成
    this.cluster = new ecs.Cluster(this, 'ApiCluster', {
      vpc,
      clusterName: 'progate-hackathon-cluster',
    });

    // CloudWatchメトリクス取得用のIAMロールを作成
    const taskRole = new iam.Role(this, 'ApiTaskRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      description: 'Role for API ECS tasks',
    });

    // CloudWatchメトリクス読み取り権限を追加
    taskRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName('CloudWatchReadOnlyAccess')
    );

    // EC2インスタンス情報取得用の権限を追加
    taskRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'ec2:DescribeInstances',
          'ec2:DescribeInstanceStatus',
          'elasticloadbalancing:DescribeLoadBalancers',
          'elasticloadbalancing:DescribeTargetGroups',
          'elasticloadbalancing:DescribeTargetHealth',
          'rds:DescribeDBInstances'
        ],
        resources: ['*'],
      })
    );

    // Cost Explorer APIの権限を追加
    taskRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'ce:GetCostAndUsage',
          'ce:GetTags'
        ],
        resources: ['*'],
      })
    );

    // Fargateタスク定義
    this.taskDefinition = new ecs.FargateTaskDefinition(this, 'ApiTaskDef', {
      memoryLimitMiB: 512,
      cpu: 256,
      taskRole: taskRole,
    });

    // コンテナの追加（ECRリポジトリが設定されていない場合は一時的なイメージを使用）
    const containerImage = this.ecrRepository
      ? ecs.ContainerImage.fromEcrRepository(this.ecrRepository, 'latest')
      : ecs.ContainerImage.fromRegistry('amazon/amazon-ecs-sample');

    this.taskDefinition.addContainer('ApiContainer', {
      image: containerImage,
      portMappings: [{ containerPort: 8080 }],
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: 'ApiContainer' }),
    });

    // Fargateサービスの作成
    this.service = new ecs.FargateService(this, 'ApiService', {
      cluster: this.cluster,
      taskDefinition: this.taskDefinition,
      desiredCount: 2,
      assignPublicIp: false,
      minHealthyPercent: 100,
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

    alb.addSecurityGroup(albSg);
    this.service.connections.addSecurityGroup(serviceSg);

    // HTTPリスナーの作成
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
      targets: [this.service],
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

  // ECRリポジトリを後から設定するメソッド
  public addEcrRepository(repository: ecr.IRepository) {
    this.ecrRepository = repository;

    // 新しいタスク定義を作成
    const newTaskDefinition = new ecs.FargateTaskDefinition(this, 'ApiTaskDefWithEcr', {
      memoryLimitMiB: 512,
      cpu: 256,
      taskRole: this.taskDefinition.taskRole,
    });

    // 新しいコンテナを追加
    newTaskDefinition.addContainer('ApiContainer', {
      image: ecs.ContainerImage.fromEcrRepository(repository, 'latest'),
      portMappings: [{ containerPort: 8080 }],
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: 'ApiContainer' }),
    });

    // サービスを新しいタスク定義で更新
    this.service.node.tryRemoveChild('TaskDefinition');
    this.service.node.addDependency(newTaskDefinition);
    this.taskDefinition = newTaskDefinition;
  }
}
