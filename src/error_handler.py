"""#005 上游失败下游容错机制."""

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 确保路径相对于项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
STATUS_DIR = PROJECT_ROOT / "knowledge/status"
MAX_RETRIES = 3
RETRY_INTERVAL = 300  # 5 分钟
WAIT_TIMEOUT = 1800  # 30 分钟

# Agent 上下游依赖关系
DEPENDENCIES = {
    "collector": None,
    "analyzer": "collector",
    "organizer": "analyzer",
}

VALID_STATES = {"pending", "running", "success", "failed", "skipped", "partial"}


def get_status_file(date: str) -> Path:
    """获取状态文件路径."""
    return STATUS_DIR / f"{date}.json"


def read_status(date: str) -> dict:
    """读取状态文件."""
    status_file = get_status_file(date)
    if not status_file.exists():
        return {"date": date, "collector": {}, "analyzer": {}, "organizer": {}}

    with open(status_file, encoding="utf-8") as f:
        return json.load(f)


def write_status(data: dict) -> None:
    """写入状态文件."""
    status_file = get_status_file(data["date"])
    status_file.parent.mkdir(parents=True, exist_ok=True)
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_agent_status(data: dict, agent: str) -> dict:
    """获取指定 Agent 的状态."""
    return data.get(agent, {})


def set_agent_status(data: dict, agent: str, status: str, items: int = 0, error: dict = None) -> None:
    """设置指定 Agent 的状态."""
    data[agent] = {
        "status": status,
        "started_at": data[agent].get("started_at", datetime.now(timezone.utc).isoformat()),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "items_processed": items,
    }
    if error:
        data[agent]["error"] = error


def check_upstream_status(date: str, agent: str) -> tuple[str, str]:
    """检查上游 Agent 状态.
    
    Returns:
        (upstream_status, upstream_agent_name)
    """
    upstream = DEPENDENCIES.get(agent)
    if upstream is None:
        return "success", ""

    data = read_status(date)
    upstream_data = get_agent_status(data, upstream)
    return upstream_data.get("status", "pending"), upstream


def wait_for_upstream(date: str, agent: str) -> bool:
    """等待上游 Agent 完成.
    
    Returns:
        True: 上游成功或部分成功，可以继续
        False: 上游失败或超时，应跳过
    """
    start_time = time.time()
    
    while time.time() - start_time < WAIT_TIMEOUT:
        status, upstream_name = check_upstream_status(date, agent)
        
        if status in ("success", "partial"):
            logger.info(f"上游 {upstream_name} 状态: {status}，继续执行")
            return True
        elif status == "failed":
            logger.warning(f"上游 {upstream_name} 失败，跳过 {agent}")
            return False
        elif status == "skipped":
            logger.warning(f"上游 {upstream_name} 被跳过，跳过 {agent}")
            return False
        
        logger.info(f"上游 {upstream_name} 状态: {status}，等待中...")
        time.sleep(30)

    logger.error(f"等待上游 {upstream_name} 超时（{WAIT_TIMEOUT}秒）")
    return False


def should_retry(date: str, agent: str) -> bool:
    """检查是否应该重试."""
    data = read_status(date)
    agent_data = get_agent_status(data, agent)
    retry_count = agent_data.get("retry_count", 0)
    return retry_count < MAX_RETRIES


def increment_retry(date: str, agent: str) -> int:
    """增加重试计数."""
    data = read_status(date)
    agent_data = get_status(data, agent)
    agent_data["retry_count"] = agent_data.get("retry_count", 0) + 1
    write_status(data)
    return agent_data["retry_count"]


def check_consecutive_failures(agent: str, days: int = 3) -> bool:
    """检查连续失败天数."""
    today = datetime.now(timezone.utc)
    consecutive = 0

    for i in range(days):
        date = (today - timedelta(days=i)).strftime("%Y%m%d")
        data = read_status(date)
        agent_data = get_agent_status(data, agent)
        status = agent_data.get("status")
        
        if status == "failed":
            consecutive += 1
        else:
            break

    return consecutive >= days


def send_alert(agent: str, message: str) -> None:
    """发送告警通知（占位实现）."""
    logger.critical(f"[ALERT] {agent}: {message}")
    # TODO: 接入飞书/邮件等通知渠道


def handle_upstream_failure(date: str, agent: str) -> bool:
    """处理上游失败.
    
    Returns:
        True: 可以继续执行
        False: 应该跳过
    """
    status, upstream_name = check_upstream_status(date, agent)

    if status in ("success", "partial"):
        return True
    elif status == "failed":
        logger.warning(f"上游 {upstream_name} 失败，记录 {agent} 为 skipped")
        data = read_status(date)
        set_agent_status(data, agent, "skipped", error={
            "code": "upstream_failed",
            "message": f"上游 {upstream_name} 执行失败"
        })
        write_status(data)

        if check_consecutive_failures(agent):
            send_alert(agent, f"连续 3 天失败，请检查系统状态")

        return False
    elif status in ("pending", "running"):
        if wait_for_upstream(date, agent):
            return True
        return False

    return False


def run_with_retry(date: str, agent: str, func, *args, **kwargs) -> dict:
    """带重试的执行包装器."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            # 检查上游状态
            if not handle_upstream_failure(date, agent):
                logger.info(f"{agent} 跳过执行（上游失败）")
                return {"status": "skipped", "reason": "upstream_failed"}

            # 执行实际任务
            result = func(*args, **kwargs)
            return result

        except Exception as e:
            retry_count = increment_retry(date, agent)
            logger.error(f"{agent} 执行失败 (尝试 {retry_count}/{MAX_RETRIES}): {e}")

            if retry_count < MAX_RETRIES:
                logger.info(f"等待 {RETRY_INTERVAL} 秒后重试...")
                time.sleep(RETRY_INTERVAL)
            else:
                data = read_status(date)
                set_agent_status(data, agent, "failed", error={
                    "code": "max_retries_exceeded",
                    "message": str(e)
                })
                write_status(data)

                if check_consecutive_failures(agent):
                    send_alert(agent, f"连续 3 天失败，请检查系统状态")

                raise

    return {"status": "failed", "reason": "max_retries_exceeded"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 测试：检查今天状态
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    print(f"检查日期: {today}")
    print(f"Collector 状态: {check_upstream_status(today, 'analyzer')}")
    print(f"Analyzer 状态: {check_upstream_status(today, 'organizer')}")
    print(f"连续失败检查: {check_consecutive_failures('collector')}")
