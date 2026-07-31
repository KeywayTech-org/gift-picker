---
name: gift-picker
description: 礼物挑选助手。当男性用户需要为女朋友、老婆或心仪之人挑选礼物时使用本 skill，例如"帮我给女朋友挑生日礼物""七夕送什么给老婆""挑个道歉礼物"。能力：恋人画像配置与持久化、多渠道免费信息源商品搜索（小红书/淘宝/京东/搜索引擎）、四维评分（价格/质量/优质好评度/差评率）+ 画像匹配度分析、生成含图片/评分图表/AI 分析/多渠道比价与购买链接的 HTML 礼物清单。
agent_created: true
---

# 礼物挑选助手（gift-picker）

帮助用户为恋人挑选礼物：读取/建立恋人画像 → 解析本次送礼需求 → 多渠道免费信息源采集候选商品 → 四维评分 + 画像匹配 → 生成 HTML 礼物清单报告。

## 关键路径

- 画像存储（持久，跨会话）：`~/.workbuddy/gift-picker/profiles/<昵称>.json`
- 存储路径可通过环境变量 `GIFT_PICKER_HOME` 覆盖
- 登录态存储（持久，跨会话）：`~/.workbuddy/gift-picker/sessions/<channel>.json` + `*_profile/`
- 登录态管理脚本：`scripts/login_manager.py`（基于 Playwright 的持久化浏览器上下文）
- 中间数据（单次任务，用后即删）：本 skill 目录下 `memory.json`（JSON 格式，支持断点恢复）
- 报告输出：当前工作区 `gift-report-<日期>.html`
- 分发说明：本 skill 可独立打包发售。纯免费路径零依赖、开箱即用，无需任何密钥、付费 Token 或付费账户。密钥与运行时数据已被 `.gitignore` 排除。

## 硬性规则（必须遵守）

1. **登录态前置检查**：任何需要登录态的渠道（如淘宝）在任务开始采集前，必须先通过 `login_manager.py check <channel>` 校验登录态。若已保存有效状态则直接复用；若无或失效则执行 `login_manager.py login <channel>` 让用户手动登录后保存。校验通过后才开始采集。
2. **登录态失效熔断**：采集过程中一旦发现登录态失效（跳转登录页、风控验证码、返回未登录内容），必须立刻停止该渠道全部抓取，明确告知用户并等待其重新登录；用户确认后重新执行 `login_manager.py check <channel>` 校验，再从 `memory.json` 记录的断点继续。禁止带着失效登录态硬爬。
3. **中间数据记录**：任务开始时在本 skill 目录内创建 `memory.json`，全过程持续追加。格式为 JSON 对象，结构为：
   ```json
   {
     "version": 1,
     "task_id": "UUID",
     "started_at": "ISO-8601",
     "stage": "profile_check | requirement_parsing | login_check | collection | scoring | report_generation",
     "profile_snapshot": {...},
     "requirements": {...},
     "checkpoints": [
       {"channel": "xiaohongshu", "status": "completed", "items_collected": 5, "timestamp": "..."}
     ],
     "candidates": [...],
     "scoring_results": {...}
   }
   ```
   任何中断（含登录失效）后都从 `memory.json` 恢复，不重复采集。
4. **清理**：最终 HTML 报告生成并交付后，删除本 skill 目录内 `memory.json`（仅此文件，不动 skill 其他文件与用户画像）。
5. **全免费、零依赖**：只用免费信息源与用户本人浏览器登录态（browser-use + WebSearch），满足"全免费"约束。不依赖任何付费 API、付费 Token 或付费账户。禁止编造价格、销量、评价。
6. **XSS 防护**：所有写入 HTML 报告模板的数据（商品名、店铺名、评价内容、链接描述等）必须经过 HTML 转义（`<` → `&lt;`, `>` → `&gt;`, `&` → `&amp;`, `"` → `&quot;`, `'` → `&#39;`），防止注入恶意脚本。

## 工作流

### 阶段 0：画像检查（每次必做）

1. 运行 `python scripts/profile_manager.py list` 查看已有画像。
2. 无画像 → 按 `references/profile-schema.md` 的画像获取策略收集信息，优先级：**社媒 ID 一键画像（小红书/微博/抖音/B站号；用 browser-use 读取对方公开主页，见 `references/social-profiling.md`：自动检索公开媒体→喜好分析→对话内输出不落盘的喜好报告→用户确认后才进入礼物检索）> 截图解析 > 一段话速写 > 逐题问答**；问答仅补必答缺口（过敏忌口、预算），需要问答时用交互式提问 UI（AskUserQuestion），一次只问 1 个问题，每题附 2~4 个默认选项。画像是否持久化由用户确认后 `set` 保存。
3. 有画像 → `get <昵称>` 读取；用交互式提问确认关键信息是否有变化（尺码、过敏、近期新增兴趣），有变化则增量 `set` 更新。
4. 用户说"更新画像/改一下她的信息"时，直接进入增量更新，不重走全量引导。

### 阶段 1：需求解析

明确：场景（生日/纪念日/节日/道歉/日常惊喜）、预算区间、品类倾向或排除项（同样逐题交互式提问，附默认选项）。与画像合并，生成 3~5 组搜索关键词。在 skill 目录创建 `memory.json` 并写入本次任务头信息。

### 阶段 2：登录态检查（涉及登录渠道时）

1. 列出本次需要登录的渠道（如淘宝）。
2. 对每个渠道执行 `python scripts/login_manager.py check <channel>` 校验当前登录态。
3. 若状态有效 → 在 `memory.json` 记录"渠道 X 登录态 OK + 保存时间"，继续下一渠道。
4. 若状态失效或不存在 → 执行 `python scripts/login_manager.py login <channel>`，弹出浏览器让用户手动登录，等待登录成功后自动保存状态。
5. 所有渠道校验/登录完成后，开始采集。用户明确表示"不登录/跳过淘宝"时，走 `references/data-sources.md` 的降级路径并在 `memory.json` 记录。

### 阶段 3：多渠道采集

按 `references/data-sources.md` 执行：小红书口碑挖掘 → 搜索引擎品类调研 → 淘宝/京东价格与评价 → 可选补充源。目标产出 5~8 个候选商品，每个至少 2 个渠道报价。所有原始数据边采边写入 `memory.json`。

### 阶段 4：评分

按 `references/scoring-model.md` 计算四维评分（默认权重：价格 25% / 质量 30% / 优质好评度 25% / 差评率反向 20%）与画像匹配度，含置信度标注。用户可在阶段 1 选择评分偏好预设（均衡/性价比优先/品质优先/口碑优先），权重随之调整。中间结果写入 `memory.json`。

### 阶段 5：报告生成与清理

1. 读取 `assets/report-template.html`，按 `references/html-spec.md` 填充数据，**所有填充值必须经过 HTML 转义**（硬性规则 6），输出到工作区。
2. 用 present_files 交付 HTML。
3. 删除本 skill 目录内 `memory.json`。

## 资源索引

| 文件 | 何时读取 |
|---|---|
| `references/profile-schema.md` | 首次建立或更新画像时 |
| `references/social-profiling.md` | 用户提供社媒 ID 做一键画像时 |
| `references/data-sources.md` | 阶段 2~3，采集与登录检查前 |
| `references/scoring-model.md` | 阶段 4 评分前 |
| `references/html-spec.md` + `assets/report-template.html` | 阶段 5 生成报告前 |
| `scripts/profile_manager.py` | 画像读写（用托管 Python 绝对路径运行） |
| `scripts/login_manager.py` | 登录态管理（login/check/list/clear） |
| `README.md` / `LICENSE` | 对外发售说明与非商业（Non-Commercial）许可 |

## 评分权重预设

| 预设 | 价格 | 质量 | 好评 | 差评反向 | 适用场景 |
|------|------|------|------|----------|----------|
| 均衡（默认） | 25% | 30% | 25% | 20% | 大多数场景 |
| 性价比优先 | 40% | 25% | 20% | 15% | 预算有限 |
| 品质优先 | 15% | 45% | 20% | 20% | 送礼重品质 |
| 口碑优先 | 15% | 25% | 40% | 20% | 怕踩雷 |