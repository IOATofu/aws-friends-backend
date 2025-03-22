# CPU使用率から計算
def calc_ec2(cpu_utilization):
    if cpu_utilization != None:
        if cpu_utilization < 50:
            return "low"
        elif cpu_utilization < 80:
            return "medium"
        else:
            return "high"
    else:
        return "low"

# CPU使用率から計算
def calc_rds(cpu_utilization):
    if cpu_utilization != None:
        if cpu_utilization < 50:
            return "low"
        elif cpu_utilization < 80:
            return "medium"
        else:
            return "high"
    else:
        return "low"

# レスポンス数で計算
def calc_alb(response_time):
    if response_time != None:
        if response_time < 1:
            return "low"
        elif response_time < 5:
            return "medium"
        else:
            return "high"
    else:
        return "low"
