#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dan Koe Daily Pusher - GitHub 持久化 + AI 生成版本
每日定时触发：
  1. git pull 拉取最新主题计划
  2. 根据日期计算今天是第几天
  3. 调用 OpenAI 实时生成文章
  4. 推送到飞书
  5. 日志 git commit & push 回 GitHub
"""

import json
import os
import subprocess
import sys
import datetime
import requests
import pytz

# ─── 配置 ────────────────────────────────────────────────────────────────────
FEISHU_WEBHOOK = os.environ.get(
    "FEISHU_WEBHOOK",
    "https://open.feishu.cn/open-apis/bot/v2/hook/6d5e9d1c-a7f4-4b2e-8c3f-1d2e3f4a5b6c"
)
GITHUB_REPO = "zhenxishuai/dan-koe-daily"
REPO_DIR    = os.path.dirname(os.path.abspath(__file__))
TOPIC_FILE  = os.path.join(REPO_DIR, "topic_plan.json")
LOG_FILE    = os.path.join(REPO_DIR, "push_log.json")
START_DATE  = datetime.date(2026, 2, 20)   # Day 1 对应的日期
TIMEZONE    = "Asia/Shanghai"

# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def run(cmd, cwd=None):
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=cwd or REPO_DIR
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def ensure_repo():
    """确保本地仓库存在且是最新的"""
    if not os.path.isdir(os.path.join(REPO_DIR, ".git")):
        print("📥 克隆仓库...")
        parent = os.path.dirname(REPO_DIR)
        name   = os.path.basename(REPO_DIR)
        code, out, err = run(f"gh repo clone {GITHUB_REPO} {name}", cwd=parent)
        if code != 0:
            raise RuntimeError(f"克隆失败: {err}")
    else:
        print("🔄 拉取最新内容...")
        run("git pull --rebase 2>&1")

    run('git config user.email "manus-bot@daily.push"')
    run('git config user.name "Manus Daily Bot"')


def get_today_info():
    """返回 (today_date, day_number, today_str)"""
    tz    = pytz.timezone(TIMEZONE)
    today = datetime.datetime.now(tz).date()
    day_n = (today - START_DATE).days + 1
    return today, day_n, today.strftime("%Y-%m-%d")


def get_topic(day_number):
    """从 topic_plan.json 获取今天的主题"""
    with open(TOPIC_FILE, "r", encoding="utf-8") as f:
        topics = json.load(f)
    for t in topics:
        if t["day"] == day_number:
            return t
    return None


def already_pushed(today_str):
    """检查今天是否已推送"""
    if not os.path.exists(LOG_FILE):
        return False
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        logs = json.load(f)
    return any(e.get("date") == today_str for e in logs)


def generate_article(topic):
    """调用 OpenAI 生成当日文章，返回格式化文本"""
    try:
        from openai import OpenAI
        client = OpenAI()
    except Exception as e:
        print(f"⚠️  OpenAI 初始化失败: {e}")
        return None

    prompt = f"""你是一位有深度的中文内容创作者，为一个每日成长洞察专栏写文章。

今日信息：
- 主题：{topic['topic']}
- 核心角度：{topic['angle']}
- 入坑种子（参考方向，不要直接照搬）：{topic['hook_seed']}

写作要求：
1. 开头写一段60-80字的入坑引导，用一个让人有共鸣的真实场景开头，让读者觉得"这说的就是我"，想继续往下看。
2. 正文900-1100字，必须包含一个具体的例子或小故事让观点落地，不能全是道理。
3. 今日反思：一个让人真的会停下来想的问题，不超过50字。
4. 今日行动：一个今天就能做的具体行动，不超过80字，要有操作性。

风格要求（非常重要）：
- 彻底去掉 AI 味：不用"此外、至关重要、深入探讨、格局、织锦、见证、不仅……而且……、值得注意的是"等词
- 不提任何具体人名
- 口语化，有温度，像真实的人在说话，可以有情绪
- 混合长短句，节奏自然
- 用具体细节代替抽象概括
- 不用加粗标题，不用列表，用自然的段落
- 读完要让人想动起来，而不是点头称是然后关掉

输出格式（严格按照，不要有其他内容）：

【入坑】
（入坑引导段）

【正文】
（正文，段落之间空一行）

【今日反思】
（反思问题）

【今日行动】
（行动建议）"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
            max_tokens=2200
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️  OpenAI 调用失败: {e}")
        return None


def parse_article(article_text):
    """解析文章各部分"""
    parts = {"入坑": [], "正文": [], "今日反思": [], "今日行动": []}
    current = None
    for line in article_text.split("\n"):
        s = line.strip()
        if s == "【入坑】":
            current = "入坑"
        elif s == "【正文】":
            current = "正文"
        elif s == "【今日反思】":
            current = "今日反思"
        elif s == "【今日行动】":
            current = "今日行动"
        elif current is not None:
            parts[current].append(line)
    return {k: "\n".join(v).strip() for k, v in parts.items()}


def build_feishu_message(day_number, topic, article_text, today_str):
    """构建飞书纯文本消息"""
    lines = []
    lines.append(f"Day {day_number}  |  {today_str}")
    lines.append(f"今日主题：{topic['topic']}")
    lines.append("─" * 28)
    lines.append("")

    if article_text:
        p = parse_article(article_text)

        if p["入坑"]:
            lines.append(p["入坑"])
            lines.append("")

        if p["正文"]:
            lines.append(p["正文"])
            lines.append("")

        lines.append("─" * 28)
        lines.append("")

        if p["今日反思"]:
            lines.append("今日反思")
            lines.append(p["今日反思"])
            lines.append("")

        if p["今日行动"]:
            lines.append("今日行动")
            lines.append(p["今日行动"])
    else:
        # 备用内容（AI 失败时）
        lines.append(f"今天聊一个问题：{topic['hook_seed']}")
        lines.append("")
        lines.append(topic["angle"])

    return "\n".join(lines)


def push_feishu(message_text):
    """推送到飞书 Webhook"""
    payload = {"msg_type": "text", "content": {"text": message_text}}
    resp = requests.post(FEISHU_WEBHOOK, json=payload, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    if result.get("code") != 0:
        raise RuntimeError(f"飞书返回错误: {result}")
    return result


def save_log(today_str, day_number, topic, status, msg_len):
    """追加推送日志"""
    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            logs = json.load(f)
    tz = pytz.timezone(TIMEZONE)
    logs.append({
        "date":           today_str,
        "day":            day_number,
        "topic":          topic["topic"],
        "status":         status,
        "message_length": msg_len,
        "pushed_at":      datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    })
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)


def sync_to_github(today_str, day_number):
    """将日志提交并推送到 GitHub"""
    run("git add push_log.json")
    code, out, err = run(f'git commit -m "log: Day {day_number} pushed on {today_str}"')
    if code != 0:
        print(f"  git commit: {err or out}")
        return
    code, out, err = run("git push 2>&1")
    if code != 0:
        run("git push --set-upstream origin main 2>&1")
    print("✅ 日志已同步到 GitHub")


# ─── 主流程 ───────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("Dan Koe Daily Pusher 启动")

    # 1. 确保仓库最新
    ensure_repo()

    # 2. 计算今天
    today, day_number, today_str = get_today_info()
    print(f"📅 今天 {today_str}，Day {day_number}")

    # 3. 范围检查
    if day_number < 1 or day_number > 180:
        print(f"⚠️  Day {day_number} 超出范围，跳过")
        return

    # 4. 重复检查
    if already_pushed(today_str):
        print(f"✅ 今天已推送过，跳过")
        return

    # 5. 获取主题
    topic = get_topic(day_number)
    if not topic:
        print(f"⚠️  找不到 Day {day_number} 的主题")
        return
    print(f"📝 主题：{topic['topic']}")

    # 6. 生成文章
    print("🤖 生成文章中...")
    article_text = generate_article(topic)
    print(f"✅ 文章生成完成" if article_text else "⚠️  文章生成失败，使用备用内容")

    # 7. 构建消息
    message = build_feishu_message(day_number, topic, article_text, today_str)
    print(f"📨 消息长度：{len(message)} 字符")

    # 8. 推送飞书
    print("📤 推送飞书...")
    result = push_feishu(message)
    print(f"✅ 飞书推送成功：{result}")

    # 9. 记录日志
    save_log(today_str, day_number, topic, "success", len(message))

    # 10. 同步 GitHub
    sync_to_github(today_str, day_number)

    print(f"✅ Day {day_number} 完成！")
    print("=" * 50)


if __name__ == "__main__":
    main()
