# Dan Koe 每日内容推送

每天早上 8 点（GMT+8）自动推送 Dan Koe 深度洞察文章到飞书群聊。

## 文件说明

| 文件 | 说明 |
|------|------|
| `180day_calendar.json` | 180 天内容日历，按日期索引每天的主题和内容 ID |
| `adapted_content.json` | 改编后的中文文章内容，按 content_id 索引 |
| `push_log.json` | 推送历史记录，每次推送后自动更新 |
| `feishu_pusher_complete.py` | 推送脚本 |

## 运行方式

```bash
python3 feishu_pusher_complete.py <webhook_url> push-today
```
