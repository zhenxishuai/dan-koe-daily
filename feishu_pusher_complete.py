#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dan Koe 每日内容推送到飞书 - GitHub 持久化版本
用法: python3 feishu_pusher_complete.py <webhook_url> push-today

工作流程：
1. 从 GitHub 仓库拉取最新数据（git pull）
2. 读取今天的日历条目和改编文章
3. 推送到飞书
4. 将推送记录写回 GitHub（git commit & push）
"""

import sys
import json
import os
import subprocess
import requests
from datetime import datetime
import pytz

# 仓库信息
REPO_NAME = "zhenxishuai/dan-koe-daily"
REPO_DIR = os.path.dirname(os.path.abspath(__file__))

# 文件路径
CALENDAR_FILE = os.path.join(REPO_DIR, "180day_calendar.json")
CONTENT_FILE = os.path.join(REPO_DIR, "adapted_content.json")
LOG_FILE = os.path.join(REPO_DIR, "push_log.json")


def get_today_date():
    """获取今天的日期（GMT+8）"""
    tz = pytz.timezone("Asia/Shanghai")
    now = datetime.now(tz)
    return now.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d %H:%M:%S")


def run_cmd(cmd, cwd=None):
    """执行 shell 命令，返回 (returncode, stdout, stderr)"""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=cwd or REPO_DIR
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def ensure_repo():
    """确保仓库存在并是最新状态"""
    # 检查是否在 git 仓库中
    code, out, err = run_cmd("git status")
    if code != 0:
        print(f"当前目录不是 git 仓库，尝试克隆...")
        parent = os.path.dirname(REPO_DIR)
        repo_basename = os.path.basename(REPO_DIR)
        code, out, err = run_cmd(
            f"gh repo clone {REPO_NAME} {repo_basename}", cwd=parent
        )
        if code != 0:
            print(f"克隆失败: {err}")
            return False
        # 配置 git 用户
        run_cmd("git config user.email 'bot@dankoe.local'")
        run_cmd("git config user.name 'Dan Koe Bot'")

    # 拉取最新内容
    print("从 GitHub 拉取最新数据...")
    code, out, err = run_cmd("git pull origin main 2>&1 || git pull origin master 2>&1")
    if code != 0:
        # 可能是空仓库或网络问题，继续使用本地文件
        print(f"git pull 提示: {err or out}（继续使用本地文件）")
    else:
        print(f"git pull: {out or '已是最新'}")
    return True


def load_json(filepath):
    """加载 JSON 文件"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(filepath, data):
    """保存 JSON 文件"""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_today_calendar_entry(calendar, today_date):
    """从日历中找到今天的条目"""
    for entry in calendar:
        if entry.get("date") == today_date:
            return entry
    return None


def format_message(calendar_entry, content_entry):
    """格式化飞书消息内容（纯文本，避免 Markdown 渲染问题）"""
    day = calendar_entry.get("day", "?")
    date = calendar_entry.get("date", "")
    theme = calendar_entry.get("theme", "")
    key_insight = calendar_entry.get("key_insight", "")

    title = content_entry.get("title", "")
    subtitle = content_entry.get("subtitle", "")
    body = content_entry.get("body", "")
    reflection = content_entry.get("reflection", "")
    action = content_entry.get("action", "")

    lines = []
    lines.append(f"Day {day} | {date}")
    lines.append(f"主题：{theme}")
    lines.append("")
    lines.append(f"【{title}】")
    lines.append(f"{subtitle}")
    lines.append("")
    lines.append(body)
    lines.append("")
    lines.append("─" * 20)
    lines.append("")
    lines.append(f"核心洞察：{key_insight}")
    lines.append("")
    lines.append(f"今日反思：{reflection}")
    lines.append("")
    lines.append(f"行动建议：{action}")
    lines.append("")
    lines.append("─" * 20)
    lines.append("Dan Koe 深度洞察 | 每日一篇")

    return "\n".join(lines)


def push_to_feishu(webhook_url, message_text):
    """通过 Webhook 推送消息到飞书"""
    payload = {
        "msg_type": "text",
        "content": {"text": message_text}
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(webhook_url, json=payload, headers=headers, timeout=15)
    return response.status_code, response.json()


def load_push_log():
    """加载推送日志"""
    if os.path.exists(LOG_FILE):
        return load_json(LOG_FILE)
    return []


def append_push_log(log_entry):
    """追加推送记录到日志"""
    logs = load_push_log()
    logs.append(log_entry)
    save_json(LOG_FILE, logs)


def commit_and_push_log(today_date):
    """将更新后的日志提交并推送到 GitHub"""
    print("将推送日志同步到 GitHub...")
    run_cmd("git add push_log.json")
    code, out, err = run_cmd(f'git commit -m "log: push {today_date}"')
    if code != 0:
        print(f"git commit: {err or out}")
        return False
    code, out, err = run_cmd("git push origin main 2>&1 || git push origin master 2>&1")
    if code != 0:
        # 尝试设置上游分支
        code, out, err = run_cmd("git push --set-upstream origin main 2>&1 || git push --set-upstream origin master 2>&1")
    if code == 0:
        print(f"日志已同步到 GitHub: {out or '成功'}")
        return True
    else:
        print(f"git push 失败: {err}")
        return False


def main():
    if len(sys.argv) < 3:
        print("用法: python3 feishu_pusher_complete.py <webhook_url> push-today")
        sys.exit(1)

    webhook_url = sys.argv[1]
    command = sys.argv[2]

    if command != "push-today":
        print(f"未知命令: {command}，仅支持 push-today")
        sys.exit(1)

    today_date, now_str = get_today_date()
    print(f"[{now_str}] 开始执行每日推送，日期：{today_date}")

    # 步骤 1：确保仓库最新
    ensure_repo()

    # 步骤 2：加载日历
    print("加载 180day_calendar.json ...")
    calendar = load_json(CALENDAR_FILE)

    calendar_entry = get_today_calendar_entry(calendar, today_date)
    if not calendar_entry:
        print(f"未找到 {today_date} 的日历条目，跳过推送。")
        sys.exit(0)

    print(f"找到今日条目：Day {calendar_entry['day']} - {calendar_entry['theme']}")

    # 步骤 3：加载改编内容
    print("加载 adapted_content.json ...")
    adapted = load_json(CONTENT_FILE)

    content_id = calendar_entry.get("content_id")
    content_entry = adapted.get(content_id)
    if not content_entry:
        print(f"未找到 content_id={content_id} 的改编内容，跳过推送。")
        sys.exit(0)

    print(f"找到改编文章：{content_entry['title']}")

    # 步骤 4：格式化并推送
    message_text = format_message(calendar_entry, content_entry)
    print(f"消息长度：{len(message_text)} 字符")
    print("推送到飞书 Webhook ...")
    status_code, resp_json = push_to_feishu(webhook_url, message_text)

    if status_code == 200 and resp_json.get("code") == 0:
        print(f"推送成功！飞书响应：{resp_json}")
        success = True
        error_msg = None
    else:
        print(f"推送失败！HTTP {status_code}，飞书响应：{resp_json}")
        success = False
        error_msg = str(resp_json)

    # 步骤 5：记录日志并同步到 GitHub
    log_entry = {
        "timestamp": now_str,
        "date": today_date,
        "day": calendar_entry.get("day"),
        "theme": calendar_entry.get("theme"),
        "title": content_entry.get("title"),
        "content_id": content_id,
        "success": success,
        "http_status": status_code,
        "feishu_response": resp_json,
        "error": error_msg
    }
    append_push_log(log_entry)
    print("推送记录已写入 push_log.json")

    # 同步日志到 GitHub
    commit_and_push_log(today_date)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
