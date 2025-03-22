import * as cdk from 'aws-cdk-lib';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as certificatemanager from 'aws-cdk-lib/aws-certificatemanager';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as s3 from 'aws-cdk-lib/aws-s3';
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
    // Cost Explorer APIとPricing APIの権限を追加
    taskRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'ce:GetCostAndUsage',
          'ce:GetTags',
          'pricing:GetProducts',
          'sts:GetCallerIdentity'
        ],
        resources: ['*'],
      })
    );

    // Amazon Bedrockの権限を追加
    taskRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'bedrock:InvokeModel',
          'bedrock:InvokeModelWithResponseStream',
          'bedrock:ListFoundationModels',
          'bedrock:GetFoundationModel'
        ],
        resources: ['*'],
      })
    );

    // Fargateタスク定義（リソースを増強）
    this.taskDefinition = new ecs.FargateTaskDefinition(this, 'ApiTaskDef', {
      memoryLimitMiB: 2048,  // 2GB
      cpu: 1024,            // 1 vCPU
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

    // CloudFrontのIPレンジからのトラフィックを許可
    // 注: CloudFrontの実際のIPプールを使用すると良いですが、管理簡略化のため全IPv4を許可
    albSg.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(80),
      'Allow HTTP traffic from CloudFront'
    );
    albSg.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(443),
      'Allow HTTPS traffic from CloudFront'
    );

    // 継続的にヘルスチェックを行うため、VPC内部からのアクセスも許可
    albSg.addIngressRule(
      ec2.Peer.ipv4(vpc.vpcCidrBlock),
      ec2.Port.allTraffic(),
      'Allow all traffic from within VPC'
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

    // HTTPリスナーの作成（CloudFrontからの接続用）
    const httpListener = alb.addListener('HttpListener', {
      port: 80,
      // CloudFrontからのリクエストを直接ターゲットグループに転送
      // HTTPSリダイレクトは不要（CloudFrontがHTTPSを処理するため）
    });

    // メインのターゲットグループを作成
    const targetGroup = httpListener.addTargets('ApiTarget', {
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
    httpListener.addAction('OptionsRule', {
      priority: 1,
      conditions: [
        elbv2.ListenerCondition.httpHeader('Access-Control-Request-Method', ['*']),
      ],
      action: elbv2.ListenerAction.fixedResponse(200, {
        contentType: 'text/plain',
        messageBody: '',
      }),
    });

    // CloudFrontからのリクエストを識別するためのリスナールールを追加
    httpListener.addAction('CloudFrontRule', {
      priority: 2,
      conditions: [
        elbv2.ListenerCondition.httpHeader('X-Origin-From-CloudFront', ['true']),
      ],
      action: elbv2.ListenerAction.forward([targetGroup]),
    });

    // CloudFrontのアクセスログ用のS3バケットを作成
    const accessLogBucket = new s3.Bucket(this, 'CloudFrontAccessLogsBucket', {
      removalPolicy: cdk.RemovalPolicy.RETAIN, // ログバケットは削除しない
      encryption: s3.BucketEncryption.S3_MANAGED, // SSE-S3暗号化を有効化
      enforceSSL: true, // HTTPSのみアクセスを許可
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL, // パブリックアクセスをブロック
      objectOwnership: s3.ObjectOwnership.OBJECT_WRITER, // ACLを有効化（CloudFrontがログを書き込めるようにするため）
      lifecycleRules: [
        {
          // 1年経過したログファイルを削除
          expiration: cdk.Duration.days(365),
          // 90日経過したログファイルをGlacierに移動
          transitions: [
            {
              storageClass: s3.StorageClass.GLACIER,
              transitionAfter: cdk.Duration.days(90),
            },
          ],
        },
      ],
    });

    // CloudFrontのログ記録用の権限を付与
    const cloudfrontLogDeliveryServicePrincipal = new iam.ServicePrincipal('delivery.logs.amazonaws.com');
    accessLogBucket.addToResourcePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        principals: [cloudfrontLogDeliveryServicePrincipal],
        actions: ['s3:GetBucketAcl', 's3:PutBucketAcl'],
        resources: [accessLogBucket.bucketArn],
      })
    );

    // CloudFrontディストリビューションの作成
    // キャッシュポリシーの設定（TTLを60秒に設定）
    const cachePolicy = new cloudfront.CachePolicy(this, 'ApiCachePolicy', {
      cachePolicyName: 'ApiCachePolicy',
      comment: 'Cache policy for API with 60 seconds TTL',
      defaultTtl: cdk.Duration.seconds(60),
      minTtl: cdk.Duration.seconds(1),
      maxTtl: cdk.Duration.seconds(120),
      enableAcceptEncodingGzip: true,
      enableAcceptEncodingBrotli: true,
      headerBehavior: cloudfront.CacheHeaderBehavior.allowList(
        'Authorization',
        'Origin',
        'Access-Control-Request-Method',
        'Access-Control-Request-Headers'
      ),
      cookieBehavior: cloudfront.CacheCookieBehavior.none(),
      queryStringBehavior: cloudfront.CacheQueryStringBehavior.all(),
    });

    // CloudFrontのオリジンとして設定
    const albOrigin = new origins.LoadBalancerV2Origin(alb, {
      protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY, // ALBはHTTPリスナーを使用
      customHeaders: {
        // CloudFrontからのリクエストであることを示すカスタムヘッダー
        'X-Origin-From-CloudFront': 'true',
      },
      connectionAttempts: 3, // 接続試行回数
      connectionTimeout: cdk.Duration.seconds(10), // 接続タイムアウト
    });

    // 正常系レスポンスをキャッシュするためのオリジンリクエストポリシー
    const apiOriginRequestPolicy = new cloudfront.OriginRequestPolicy(this, 'ApiOriginRequestPolicy', {
      originRequestPolicyName: 'ApiOriginRequestPolicy',
      comment: 'API origin request policy with headers needed for ALB',
      cookieBehavior: cloudfront.OriginRequestCookieBehavior.all(),
      headerBehavior: cloudfront.OriginRequestHeaderBehavior.allowList(
        'Host',
        // 'X-Origin-From-CloudFront' は削除 - オリジンカスタムヘッダーと競合するため
        'Origin',
        'Referer',
        'User-Agent'
        // 注: 'Authorization'ヘッダーはCachePolicyで処理する必要がある
      ),
      queryStringBehavior: cloudfront.OriginRequestQueryStringBehavior.all(),
    });

    // ALBをオリジンとするCloudFrontディストリビューションを作成
    const distribution = new cloudfront.Distribution(this, 'ApiDistribution', {
      defaultBehavior: {
        origin: albOrigin,
        cachePolicy: cachePolicy,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        originRequestPolicy: apiOriginRequestPolicy,
      },
      // 代替ドメイン名と証明書を追加（両方が指定されている場合のみ）
      // 注: CloudFrontの証明書はus-east-1リージョンに存在する必要があります
      ...(props.domainName && props.certificateArn ? {
        domainNames: [props.domainName],
        certificate: certificatemanager.Certificate.fromCertificateArn(
          this,
          'Certificate',
          props.certificateArn
        )
      } : {}),
      // ログ記録を有効化
      logBucket: accessLogBucket,
      logFilePrefix: 'cloudfront-logs/', // S3内のログファイルのプレフィックス
      logIncludesCookies: true, // クッキー情報も記録
      priceClass: cloudfront.PriceClass.PRICE_CLASS_100, // 北米・欧州・アジアの一部のみ（コスト削減）
      enabled: true,
      comment: 'CloudFront distribution for API with access logging enabled',
      minimumProtocolVersion: cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021, // 最新のTLSプロトコルを使用
    });

    // ALBをどこからでもアクセスできるように許可（テスト環境のみ）
    // 本番環境では実際のCloudFrontのIPレンジのみを許可するべき
    albSg.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.allTcp(),
      'Allow all TCP traffic from anywhere for testing'
    );

    // アクセスログバケットの出力を追加
    new cdk.CfnOutput(this, 'CloudFrontAccessLogsBucketName', {
      value: accessLogBucket.bucketName,
      description: 'CloudFront access logs bucket name',
      exportName: 'CloudFrontAccessLogsBucketName',
    });

    // 出力の追加
    new cdk.CfnOutput(this, 'AlbEndpoint', {
      value: alb.loadBalancerDnsName,
      description: 'Application Load Balancer endpoint',
      exportName: 'AlbEndpoint',
    });

    new cdk.CfnOutput(this, 'CloudFrontEndpoint', {
      value: distribution.distributionDomainName,
      description: 'CloudFront distribution endpoint',
      exportName: 'CloudFrontEndpoint',
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
