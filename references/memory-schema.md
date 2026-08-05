# memory.json Schema

`memory.json` 是单次任务的中间数据，支持断点恢复，报告交付后删除（见 SKILL.md Step 7）。

## 字段定义

```json
{
  "task_id": "YYYYMMDD-HHmm",
  "profile_nickname": "使用的画像昵称",
  "relationship_stage": "pursuit|honeymoon|stable|newlywed|anniversary|longterm",
  "budget": {"min": 0, "max": 0, "comfortable_upper": 0, "tier": "L1-L6"},
  "occasion": "festival|birthday|anniversary|apology|celebration|daily",
  "occasion_raw": "用户原始表述",
  "login_status": {
    "taobao": "ready|expired|skipped|failed",
    "jd": "ready|expired|skipped|failed",
    "confidence": "high|mid|low"
  },
  "xiaohongshu": {
    "status": "opened|fallback|unavailable",
    "notes": [{"url": "", "title": "", "likes": 0, "signals": []}],
    "positive_signals": [],
    "negative_signals": []
  },
  "candidates": [
    {
      "id": "g1",
      "name": "",
      "category": "",
      "brand": "",
      "img_url": "",
      "detail_url_taobao": "",
      "detail_url_jd": "",
      "prices": {"taobao": 0, "jd": 0, "min": 0},
      "scores": {"price": 0, "quality": 0, "praise": 0, "lowbad": 0, "stage": 0, "total": 0},
      "match_score": 0,
      "match_points": [],
      "reasons": [],
      "reviews": [{"nick": "", "rating": 0, "summary": "", "tag": ""}],
      "risk_note": "",
      "source_urls": []
    }
  ],
  "breakpoint": {
    "current_stage": "xiaohongshu|search|ecommerce|supplement|scoring|report",
    "completed_items": [],
    "pending_items": []
  },
  "gift_history_entry": {"date": "", "gift": "", "feedback": "positive|neutral|negative"}
}
```

## 写入时机

- Step 2 完成：写 `relationship_stage`
- Step 3 完成：写 `budget`
- Step 4 完成：写 `occasion`
- Step 5 完成：写 `login_status`
- Step 6 每阶段完成：写 `xiaohongshu` / `candidates` 增量 + `breakpoint`
- Step 7 交付前：写 `gift_history_entry`（待用户反馈后用于画像更新）
- Step 7 交付后：删除整个文件

## 写入约束

- 必须用**原子写入**（先写 `memory.json.tmp`，成功后 `os.replace` 替换原文件），避免崩溃导致 `memory.json` 损坏无法断点恢复。参考实现见 `scripts/profile_manager.py` 的 `_atomic_write`。
- 每个采集阶段开头设置硬超时（约 5 分钟），超时后降级到下一阶段并在 `breakpoint` 记录未完成项。
