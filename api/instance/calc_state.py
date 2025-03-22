# リソース状態計算モジュール


def calc_cpu_state(cpu_utilization):
    """
    CPU使用率から状態を計算する共通関数

    引数:
        cpu_utilization: CPU使用率（パーセント）

    戻り値:
        "low", "medium", "high"のいずれか
    """
    if cpu_utilization is None:
        return "unknown"  # データがない場合は不明とする

    # CPU使用率に基づく状態判定
    if cpu_utilization < 30:
        return "low"  # 30%未満: 低負荷
    elif cpu_utilization < 70:
        return "medium"  # 30%以上70%未満: 中負荷
    else:
        return "high"  # 70%以上: 高負荷


def calc_ec2(cpu_utilization, instance_state=None):
    """
    EC2インスタンスの状態を計算

    引数:
        cpu_utilization: CPU使用率（パーセント）
        instance_state: インスタンスの状態（"running"など）

    戻り値:
        "low", "medium", "high", "unknown"のいずれか
    """
    # 実行中のインスタンスはCPU使用率で判定
    return calc_cpu_state(cpu_utilization)


def calc_rds(cpu_utilization, instance_state=None):
    """
    RDSインスタンスの状態を計算

    引数:
        cpu_utilization: CPU使用率（パーセント）
        instance_state: インスタンスの状態（"available"など）

    戻り値:
        "low", "medium", "high", "unknown"のいずれか
    """
    # 利用可能なインスタンスはCPU使用率で判定
    return calc_cpu_state(cpu_utilization)


def calc_alb(response_time, status=None):
    """
    ALBの状態を計算

    引数:
        response_time: レスポンス時間（秒）
        status: ALBのステータス

    戻り値:
        "low", "medium", "high", "unknown"のいずれか
    """
    # レスポンス時間がない場合
    if response_time is None:
        return "unknown"

    # レスポンス時間に基づく状態判定
    if response_time < 0.5:
        return "low"  # 0.5秒未満: 低負荷
    elif response_time < 2:
        return "medium"  # 0.5秒以上2秒未満: 中負荷
    else:
        return "high"  # 2秒以上: 高負荷
