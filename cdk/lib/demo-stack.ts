import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as targets from 'aws-cdk-lib/aws-elasticloadbalancingv2-targets';
import * as autoscaling from 'aws-cdk-lib/aws-autoscaling';
import { Construct } from 'constructs';

export class DemoStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // VPCの作成
    const vpc = new ec2.Vpc(this, 'DemoVpc', {
      maxAzs: 2,
      natGateways: 1,
    });

    // EC2のセキュリティグループ
    const ec2SecurityGroup = new ec2.SecurityGroup(this, 'EC2SecurityGroup', {
      vpc,
      description: 'Security group for EC2 instance',
      allowAllOutbound: true,
    });

    // ALBからのトラフィックを許可
    ec2SecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(80),
      'Allow HTTP traffic from ALB'
    );

    // SSHアクセスを許可
    ec2SecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(22),
      'Allow SSH access'
    );

    // RDSのセキュリティグループ
    const dbSecurityGroup = new ec2.SecurityGroup(this, 'DBSecurityGroup', {
      vpc,
      description: 'Security group for Aurora cluster',
      allowAllOutbound: true,
    });

    // EC2からのアクセスを許可
    dbSecurityGroup.addIngressRule(
      ec2SecurityGroup,
      ec2.Port.tcp(3306),
      'Allow MySQL access from EC2'
    );

    // Aurora クラスターの作成
    const cluster = new rds.DatabaseCluster(this, 'DemoDatabase', {
      engine: rds.DatabaseClusterEngine.auroraMysql({ version: rds.AuroraMysqlEngineVersion.VER_3_08_1 }),
      credentials: rds.Credentials.fromGeneratedSecret('admin'),
      instanceProps: {
        instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MEDIUM),
        vpcSubnets: {
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        },
        vpc,
        securityGroups: [dbSecurityGroup],
      },
      instances: 2,
      port: 3306,
    });

    // Launch Templateの作成
    const userData = ec2.UserData.forLinux();
    userData.addCommands(
      // SSHの設定
      'mkdir -p /home/ec2-user/.ssh',
      'echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINQsrFjdkCPP3TxdRbBbf+ix4KKM0ZHKQ/Ix5BbhrKNw" >> /home/ec2-user/.ssh/authorized_keys',
      'chmod 700 /home/ec2-user/.ssh',
      'chmod 600 /home/ec2-user/.ssh/authorized_keys',
      'chown -R ec2-user:ec2-user /home/ec2-user/.ssh',

      // 必要なパッケージのインストール
      'yum update -y',
      'yum install -y git python3 python3-pip',

      // アプリケーションのデプロイ
      'cd /home/ec2-user',
      'git clone https://github.com/IOATofu/aws-friends-backend.git',
      'cd aws-friends-backend/demo-app/backend',
      'pip3 install -r requirements.txt',

      // 環境変数の設定
      'export DATABASE_URL="mysql://admin:${cluster.secret?.secretValueFromJson(\'password\').toString()}@${cluster.clusterEndpoint.hostname}:3306/awsfriends"',
      'export HOST="0.0.0.0"',
      'export PORT="80"',

      // アプリケーションの起動
      'sudo -E python3 main.py > /var/log/app.log 2>&1 &'
    );

    // Auto Scaling Groupの作成
    const asg = new autoscaling.AutoScalingGroup(this, 'DemoASG', {
      vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PUBLIC,
      },
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
      machineImage: new ec2.AmazonLinuxImage({
        generation: ec2.AmazonLinuxGeneration.AMAZON_LINUX_2,
      }),
      userData,
      securityGroup: ec2SecurityGroup,
      minCapacity: 1,
      maxCapacity: 3,
      desiredCapacity: 1,
      healthCheck: autoscaling.HealthCheck.elb({ grace: cdk.Duration.seconds(60) }),
    });

    // CPU使用率ベースのスケーリングポリシーを追加
    asg.scaleOnCpuUtilization('CpuScaling', {
      targetUtilizationPercent: 70,
      cooldown: cdk.Duration.seconds(300),
    });

    // ALBの作成
    const alb = new elbv2.ApplicationLoadBalancer(this, 'DemoALB', {
      vpc,
      internetFacing: true,
    });

    // ALBのリスナーとターゲットグループの作成
    const listener = alb.addListener('Listener', {
      port: 80,
    });

    // ターゲットグループの作成
    const targetGroup = new elbv2.ApplicationTargetGroup(this, 'EC2TargetGroup', {
      vpc,
      port: 80,
      protocol: elbv2.ApplicationProtocol.HTTP,
      healthCheck: {
        path: '/',
        unhealthyThresholdCount: 2,
        healthyThresholdCount: 5,
        interval: cdk.Duration.seconds(30),
      },
      targetType: elbv2.TargetType.INSTANCE,
    });

    // Auto Scaling Groupをターゲットグループに追加
    targetGroup.addTarget(asg);

    // リスナーにターゲットグループを追加
    listener.addTargetGroups('DefaultTargetGroup', {
      targetGroups: [targetGroup],
    });

    // 出力の追加
    new cdk.CfnOutput(this, 'DatabaseEndpoint', {
      value: cluster.clusterEndpoint.hostname,
      description: 'Aurora cluster endpoint',
    });

    new cdk.CfnOutput(this, 'AutoScalingGroupName', {
      value: asg.autoScalingGroupName,
      description: 'Auto Scaling Group name',
    });

    new cdk.CfnOutput(this, 'LoadBalancerDNS', {
      value: alb.loadBalancerDnsName,
      description: 'Application Load Balancer DNS name',
    });
  }
}
