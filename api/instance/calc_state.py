# CPU使用率から計算
def calc_ec2(cpu_utilization):
    if cpu_utilization != None:
        if cpu_utilization < 10:
            return "low"
        elif cpu_utilization < 30:
            return "medium"
        else:
            return "high"
    else:
        return "low"

# CPU使用率から計算
def calc_rds(cpu_utilization):
    if cpu_utilization != None:
        if cpu_utilization < 10:
            return "low"
        elif cpu_utilization < 30:
            return "medium"
        else:
            return "high"
    else:
        return "low"

# レスポンス数で計算
def calc_alb():
    return "low"
"""
    if cpu_utilization != None:
        if cpu_utilization < 10:
            return "low"
        elif cpu_utilization < 30:
            return "medium"
        else:
            return "high"
    else:
        return "low"
"""
