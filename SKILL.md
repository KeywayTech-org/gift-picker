---
name: gift-picker
description: 礼物挑选助手。为女朋友/老婆/心仪对象挑选礼物。收到请求后第一个动作必须是检查画像并问用户"你想怎么提供她的信息"（社媒ID/我来描述/发截图/逐题问答），禁止直接问穿搭风格等细节。工作流 5 步：①画像获取 → ②关系阶段 → ③预算 → ④场景品类 → ⑤登录态，每步必做不可跳过。
agent_created: true
---

# 礼物挑选助手

## 关键路径

- 画像：`~/.workbuddy/gift-picker/profiles/<昵称>.json`（环境变量 `GIFT_PICKER_HOME` 可覆盖）
- 登录态：`~/.workbuddy/gift-picker/sessions/<channel>.json`（Playwright 持久化浏览器）
- 中间数据：本 skill 目录下 `memory.json`（用后即删，支持断点恢复）
- 报告输出：当前工作区 `gift-report-<日期>.html`

## 核心工作流（5 步，严格按顺序执行）

> 🔴 **收到任何礼物挑选请求后，第一个动作必须是：运行 `python scripts/profile_manager.py list` 检查画像，然后用 AskUserQuestion 问用户"你想怎么提供她的信息"。禁止直接问穿搭/风格/兴趣等细节。**

### Step 1：画像 + 关系阶段 + 预算

**1a. 建立/读取画像**

运行 `python scripts/profile_manager.py list` 查看已有画像。

#### 情况 1：无画像

> ⚠️ **硬性规则**：无画像时，第一个问题**必须**是下面这个 AskUserQuestion，**禁止**直接问风格/兴趣/颜色等画像细节。

用 AskUserQuestion 问："还没她的画像，你想怎么提供信息？"
选项：
- 🔗 社媒 ID 一键画像（推荐）— 给我她的小红书/微博/抖音/B站号
- ✏️ 我来描述 — 一段话告诉我她的喜好风格
- 📸 发截图给我 — 小红书收藏/穿搭照等
- ❓ 逐题问答 — 我问你答

**用户选择后按对应方式执行**（不要跳过这一步直接问画像细节）：

| 方式 | 操作 |
|------|------|
| 社媒 ID | 用 browser-use 读取公开主页 → 喜好分析 → 对话内输出不落盘报告 → 用户确认后 `set` 保存。详见 `references/social-profiling.md` |
| 我来描述 | AI 解析用户描述为结构化字段 → 复述摘要 → 用户确认后 `set` 保存 |
| 发截图 | 解析图片提取色系/品牌/风格 → 复述摘要 → 用户确认后 `set` 保存 |
| 逐题问答 | 按 `references/profile-schema.md` 全量问答分批提问（仅此方式才进入逐题流程） |

收集完成后必须向用户复述画像摘要，用户确认后调用 `set` 保存。

#### 情况 2：有画像

`get <昵称>` 读取画像，**必须展示画像摘要**（空字段省略），格式：
```
📋 [昵称] 的画像：
· 关系：[relationship] · 阶段：[relationship_stage]
· 风格：[style]，喜欢 [colors_like]
· 护肤美妆：[brands] · 尺码：[sizes]
· 兴趣：[hobbies] · 过敏忌口：[allergies]
· 已有物品：[owned_items]
```

然后用 AskUserQuestion 问："画像信息有变化吗？"
选项：没变化，继续 / 有变化，我来补充

#### 情况 3：用户说"更新画像"

直接进入增量更新，不重走全量引导。

---

**1b. 关系阶段（画像确认后立即问，不可跳过）**

用 AskUserQuestion 问："你们目前处于哪个阶段？"
选项：
- 追求期（还在追求/暧昧，没正式在一起）
- 热恋期（刚确认关系 0-6 个月）
- 稳定期（交往半年以上）
- 新婚期（刚结婚 0-2 年）
（周年纪念 / 长期陪伴 → Other 输入）

确认后 `set` 写入 `relationship_stage` 字段。

---

**1c. 预算（关系阶段后立即问，不可跳过）**

读取 `references/budget-advisor.md` 计算建议预算（阶段基准×关系深度×场景×历史修正），先展示：
```
💡 预算建议：建议区间 ¥[min]-[max]（[档位]），舒适上限 ¥[上限]
```

再用 AskUserQuestion 问："这次打算花多少？"
选项（动态生成）：建议区间 ¥[min]-[max] ← 推荐 / 精简些 ¥[low] / 隆重些 ¥[high] / 自定义（Other）

确认后写入 `memory.json`。

### Step 2：场景 + 品类 + 评分偏好

用 AskUserQuestion 依次问 3 题：

1. "这次送礼是什么场合？"（单选）生日/纪念日/节日/道歉
2. "有品类偏好吗？"（多选）鲜花/首饰/美妆香氛/没想法帮我推荐
3. "推荐更看重什么？"（单选）均衡/性价比/品质/浪漫优先

结合 `relationship_stage` 过滤品类（详见 `references/relationship-stages.md`），每个场景推荐 3-5 种不同品类。

**品类推荐优先级**（采集和排序时遵循）：
1. 🥇 **首饰**（项链/手链/耳环/戒指）— 最高优先
2. 🥈 **美妆香氛**（香水/口红/护肤套装）— 高优先
3. 🥉 鲜花（结合花语系统）
4. 其他品类（体验/定制/实用单品等）— 低优先

即使用户选了"没想法帮我推荐"，采集时也优先多采集首饰和美妆香氛类商品，其他品类作为补充。报告排序时首饰和美妆香氛排在前面。

### Step 3：登录态自动检测与登录

**不再询问用户选哪个渠道，直接自动检测淘宝和京东两个渠道：**

1. 先检测淘宝登录态：
   ```
   python scripts/login_manager.py check_and_login taobao
   ```
   - 有效 → ✅ 跳过，继续检测京东
   - 无效/不存在 → 🌐 自动打开浏览器跳转淘宝登录页，告诉用户：
     ```
     🌐 已为你打开淘宝登录页，请在浏览器中完成登录（扫码或账号密码）
     ⏰ 登录成功后状态将自动保存，下次使用无需重新登录
     ```
     等待登录完成

2. 再检测京东登录态：
   ```
   python scripts/login_manager.py check_and_login jd
   ```
   - 有效 → ✅ 跳过
   - 无效/不存在 → 🌐 自动打开浏览器跳转京东登录页，告诉用户：
     ```
     🌐 已为你打开京东登录页，请在浏览器中完成登录
     ⏰ 登录成功后状态将自动保存
     ```
     等待登录完成

3. 两个渠道都完成后，进入采集阶段，报告中的商品链接可直接跳转购买页

### Step 4：采集 + 评分

按 `references/data-sources.md` 采集 5-8 个候选（登录态渠道保存原始商品 URL）。

按 `references/scoring-model.md` 五维评分（默认权重：价格20%/质量25%/好评20%/差评反向15%/阶段适配20%）。

每个候选生成 6 维推荐理由：
1. 阶段适配理由（引用 relationship-stages.md）
2. 画像匹配理由
3. 花语/寓意（限鲜花，引用 flower-guide.md）
4. 季节适配理由（引用 seasonal-guide.md）
5. 场景适配理由
6. 价格合理性（引用 budget-advisor.md）

### Step 5：报告生成

读取 `assets/report-template.html`，按 `references/html-spec.md` 填充（HTML 转义），输出到工作区，用 present_files 交付。删除 `memory.json`。

## 硬性规则

1. **5 步工作流严格有序**：Step 1a→1b→1c→Step 2→Step 3→Step 4→Step 5，每步必做
2. **登录态前置**：采集前必须通过 `login_manager.py check` 校验，失效则 `login` 让用户手动登录
3. **登录态失效熔断**：采集中发现失效立刻停止该渠道，重新校验后从 `memory.json` 断点继续
4. **XSS 防护**：所有写入模板的数据必须 HTML 转义
5. **全免费**：只用免费信息源+用户本人登录态，禁止编造价格/销量
6. **清理**：报告交付后删除 `memory.json`

## 资源索引

| 文件 | 何时读取 |
|---|---|
| `references/profile-schema.md` | 建立/更新画像时的字段定义 |
| `references/relationship-stages.md` | Step 1b 确认阶段 / Step 2 过滤品类 / Step 4 评分 |
| `references/flower-guide.md` | Step 4 生成花语建议 |
| `references/social-profiling.md` | 社媒 ID 一键画像详细流程 |
| `references/data-sources.md` | Step 3 采集 |
| `references/scoring-model.md` | Step 4 评分 |
| `references/budget-advisor.md` | Step 1c 预算建议 |
| `references/seasonal-guide.md` | Step 4 季节理由 |
| `references/html-spec.md` + `assets/report-template.html` | Step 5 报告生成 |
| `scripts/profile_manager.py` | 画像读写 |
| `scripts/login_manager.py` | 登录态管理 |
