"""조사 조치의 위험도 하한은 서버 규칙으로 고정합니다."""
RISK_ORDER = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def server_risk(*values):
    return max(("MEDIUM", *values), key=RISK_ORDER.index)
