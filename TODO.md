# gift-picker Skill 修复 TODO

> 基于 2026-08-05 全面审查产出。共 40 条问题，分 4 个阶段执行。
> 修复原则：**P0 优先单独提交，P1 分两批，P2 后续迭代**。每阶段结束跑一次端到端验证。

---

## 0. 概览

| 阶段 | 范围 | 任务数 | 预估工作量 | 风险 |
|------|------|--------|------------|------|
| 阶段 1 | P0 紧急修复（功能正确性） | 4 | 小（约 30 分钟） | 低，改动明确 |
| 阶段 2 | P1 第一批：逻辑/文档一致性 | 11 | 中（约 2 小时） | 中，需同步多处文档 |
| 阶段 3 | P1 第二批：稳定性与配置外置 | 11 | 大（约 4 小时） | 中，涉及脚本重构 |
| 阶段 4 | P2 优化迭代 | 14 | 小（按需） | 低 |

**全局约束**：
- 每阶段独立 git commit，commit message 用 `taozhuowei <876593497@qq.com>` 身份
- 修改 SKILL.md 后必须同步检查所有 references 中重复信息
- 修改脚本后必须手动跑一次 `python scripts/profile_manager.py list` 和 `python scripts/login_manager.py list` 验证
- 不破坏既有画像数据格式（schema_version=1 保持兼容）

---

## 阶段 1：P0 紧急修复

> 目标：消除功能正确性阻断问题。完成后 skill 能在标准环境下跑通基本流程。

### 任务 1.1 — 修正 SKILL.md 选项数描述（L1）

- **文件**：`SKILL.md`
- **位置**：L115
- **当前**：`> 🔴 **硬性规则：问题和选项必须与下方完全一致，禁止修改问题文本、禁止替换选项内容、禁止自行编造其他问法（如"女朋友/未婚妻/已婚"等）。只能使用以下 4 个选项 + Other。**`
- **问题**：实际下方 L117-124 列出 6 个选项（追求/热恋/稳定/新婚/周年/长期陪伴），与"4 个"自相矛盾
- **修复**：将"4 个选项 + Other"改为"6 个选项 + Other"
- **验收**：grep `4 个选项` 应无结果

### 任务 1.2 — 统一 `relationship_stage` 字段值命名（L2）

- **文件**：`scripts/profile_manager.py`、`references/profile-schema.md`、`references/relationship-stages.md`、`references/scoring-model.md`、`references/budget-advisor.md`
- **位置**：profile_manager.py L47 `STAGE_CN` 字典 key
- **当前**：脚本用 `long_term`，所有文档用 `longterm`
- **修复**：
  1. profile_manager.py L47 `"long_term": "陪伴"` → `"longterm": "陪伴"`
  2. 全项目 grep `long_term` 确认无遗漏（脚本内 `long_term` 仅作为 STAGE_CN key，无其他引用）
- **数据迁移**：已存在的画像 JSON 若包含 `"relationship_stage": "long_term"`，需在 profile_manager.py 加迁移逻辑（migrate 命令中转换）
- **验收**：`python scripts/profile_manager.py migrate` 后旧画像 `long_term` 自动转为 `longterm`

### 任务 1.3 — 明确 `relationship_stage` 存储位置（L3）

- **文件**：`SKILL.md`、`references/profile-schema.md`、`scripts/profile_manager.py`
- **当前矛盾**：
  - SKILL.md L130 "将解析结果或用户确认结果通过 `set` 写入 `relationship_stage` 字段"（写入画像）
  - profile-schema.md L93 "预算、关系阶段属于本次任务参数，不在画像问答中提问"
- **决策**：采用方案 A——阶段作为**画像持久字段**（因为画像的 stage 决定 budget-advisor 阶段基准，跨会话复用有价值），同时本次任务可临时覆盖
- **修复**：
  1. SKILL.md Step 2 完成标志保持"写入画像 `relationship_stage` 字段"
  2. profile-schema.md L93 删除"关系阶段属于本次任务参数"那句，改为"关系阶段在画像中持久化（见 SKILL.md Step 2），每次任务可确认或更新"
  3. profile-schema.md L127 "本次任务参数"列表中删除"关系阶段"行
  4. SKILL.md Step 2 开头加注："若画像已有 `relationship_stage`，作为默认值带出确认；首条消息明示新阶段则直接覆盖"
- **验收**：三处文档表述一致，无"任务参数 vs 画像字段"矛盾

### 任务 1.4 — login_manager.py 添加 Playwright import 容错（S1）

- **文件**：`scripts/login_manager.py`
- **位置**：L25 `from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout`
- **修复**：
  ```python
  try:
      from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
  except ImportError:
      print("❌ 未安装 Playwright。请运行：pip install playwright && playwright install chromium")
      print("   或使用 '跳过登录，用公开数据' 模式继续（置信度低）")
      sys.exit(2)
  ```
- **附加**：在 SKILL.md Step 5 开头加注："若运行时无 Playwright，直接走'跳过登录用公开数据'路径"
- **验收**：卸载 playwright 后跑 `python scripts/login_manager.py list` 应输出友好提示而非 traceback

---

## 阶段 2：P1 第一批 — 逻辑/文档一致性

> 目标：消除文档与实现的逻辑矛盾，定义缺失的 schema。完成后模型执行时不再因歧义纠结。

### 任务 2.1 — 形式化"首条明示阶段"判定词列表（L4）

- **文件**：`SKILL.md`、`references/relationship-stages.md`
- **当前**：L22/L111 说"已明确给出阶段直接跳过提问"，L109 说"女朋友/老婆不足以推断"。判定边界模糊
- **修复**：
  1. 在 relationship-stages.md "阶段检测方式"小节增加"明示触发词表"：
     ```
     | 阶段 | 明示触发词（正则/关键词） |
     |------|---------------------------|
     | pursuit | 追求中、暧昧、还没在一起、暗恋 |
     | honeymoon | 热恋、刚在一起、交往.*月、确认关系.*月 |
     | stable | 稳定、交往.*年、长期 |
     | newlywed | 新婚、刚结婚、婚后.*年 |
     | anniversary | 周年、纪念.*年、N 周年 |
     | longterm | 相伴.*年、10 年、老夫老妻 |
     ```
  2. SKILL.md L109 改为："仅当首条消息命中上表触发词时直接采用；'女朋友/老婆/心仪对象'本身不算明示，必须提问"
- **验收**：6 个阶段的触发词表存在于 relationship-stages.md

### 任务 2.2 — 定义 memory.json schema（L6）

- **文件**：新建 `references/memory-schema.md`
- **内容**：
  ```markdown
  # memory.json Schema

  memory.json 是单次任务的中间数据，支持断点恢复，报告交付后删除。

  ## 字段定义

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

  ## 写入时机
  - Step 2 完成：写 relationship_stage
  - Step 3 完成：写 budget
  - Step 4 完成：写 occasion
  - Step 5 完成：写 login_status
  - Step 6 每阶段完成：写 xiaohongshu / candidates 增量 + breakpoint
  - Step 7 交付前：写 gift_history_entry（待用户反馈后用于画像更新）
  - Step 7 交付后：删除整个文件
  ```
- **附加**：SKILL.md 资源索引表新增一行引用此文件
- **验收**：references/memory-schema.md 存在且字段定义完整

### 任务 2.3 — 修正 Step 6 双渠道报价要求（L7）

- **文件**：`SKILL.md`
- **位置**：L283 `每个候选商品必须获取 **淘宝 + 京东** 双渠道报价`
- **修复**：改为
  ```
  每个候选商品按已就绪渠道采集报价：
  - 双渠道就绪：必须采集淘宝 + 京东双报价，置信度=高
  - 单渠道就绪：仅采集该渠道报价，另一渠道标注 N/A，置信度=中
  - 无渠道就绪：用搜索引擎聚合价（标注"非实时价"），置信度=低
  禁止用搜索页链接冒充商品详情页链接
  ```
- **验收**：SKILL.md L283 不再出现"必须获取双渠道"的绝对表述

### 任务 2.4 — 调整 memory.json 删除与 gift_history 写入时序（L8）

- **文件**：`SKILL.md` Step 7
- **当前**：L351"交付后删除 memory.json" → L355"用户反馈写入 gift_history"
- **修复**：调整顺序为
  ```
  Step 7 交付流程：
  1. 生成 HTML 报告 + 纯文本摘要
  2. 用 AskUserQuestion 收集反馈（满意/换一批/调预算/已拥有）
  3. 将反馈写入 memory.json 的 gift_history_entry 字段
  4. 调用 profile_manager.py set <昵称> --json-file <从 memory.json 提取的 gift_history patch>
  5. 画像更新成功后删除 memory.json
  6. 告知用户报告位置
  ```
- **验收**：删除 memory.json 的步骤在 gift_history 写入之后

### 任务 2.5 — profile_manager.py list 输出机器可解析格式（L9）

- **文件**：`scripts/profile_manager.py`、`SKILL.md`
- **当前**：cmd_list 输出 `- {n}  (关系: {rel}, 更新: {updated})`，SKILL.md L77-82 期望纯名称列表
- **修复**：
  1. cmd_list 改为双段输出：
     ```python
     # 机器可解析行（首行）
     print(f"NICKNAMES:{','.join(names)}")
     # 人类可读详情（后续行）
     for n in names:
         d = _load(PROFILE_DIR / f"{n}.json")
         ...
     ```
  2. SKILL.md Step 1 情况 2 改为："解析首行 `NICKNAMES:` 获取列表，展示给用户"
- **验收**：`python scripts/profile_manager.py list` 首行以 `NICKNAMES:` 开头

### 任务 2.6 — 画像完整度算法（L5）

- **文件**：`references/profile-schema.md`、`scripts/profile_manager.py`
- **修复**：
  1. profile-schema.md 增加"字段权重表"：
     ```
     | 权重 | 字段 |
     |------|------|
     | 必填(各 15%) | nickname, relationship, relationship_stage, allergies |
     | 重要(各 10%) | colors_like, style, hobbies, skincare_brands |
     | 辅助(各 5%) | scent, sizes, makeup_brands, owned_items |
     | 可选(0%) | notes, gift_history, budget_habit |
     ```
  2. profile_manager.py 增加 `cmd_completeness` 子命令或在 list 输出中附加完整度百分比
  3. SKILL.md L101 改为："运行 `python scripts/profile_manager.py completeness <昵称>` 获取完整度分数"
- **验收**：`profile_manager.py completeness <昵称>` 输出 0-100 的数字

### 任务 2.7 — `dict | None` 改为 `Optional[dict]`（C1）

- **文件**：`scripts/login_manager.py`
- **位置**：L116 `def _load_storage_state(channel: str) -> dict | None:`
- **修复**：
  ```python
  from typing import Optional
  def _load_storage_state(channel: str) -> Optional[dict]:
  ```
- **附加**：requirements.txt 改为 `# Python 3.9+`（Optional 兼容 3.9）
- **验收**：Python 3.9 下无 SyntaxError

### 任务 2.8 — login_manager.py L433 加 None 判空（C2）

- **文件**：`scripts/login_manager.py`
- **位置**：L433 `if state.get("cookies"):`
- **修复**：在 L403 后加 `if state is None: state = {}`，或将 L433 改为 `(state or {}).get("cookies")`
- **验收**：state 为 None 时不抛 AttributeError

### 任务 2.9 — login_manager.py 加 Windows 编码兼容（C3）

- **文件**：`scripts/login_manager.py`
- **位置**：顶部 import 后
- **修复**：复制 profile_manager.py L24-27 的编码兼容块
  ```python
  if sys.platform == "win32":
      sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
      sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
  ```
- **附加**：抽到 `scripts/_compat.py` 共享（见任务 4.4）
- **验收**：Windows cmd 下中文输出无乱码

### 任务 2.10 — 统一登录信号检测文档与实现（C8）

- **文件**：`scripts/login_manager.py`、`references/data-sources.md`
- **当前矛盾**：
  - login_manager.py L182-202 注释说"任一匹配即失效"+"≥2 个成功信号才算 ok"
  - data-sources.md L79-80 说"正向信号任一满足即视为登录成功"
- **修复**：
  1. data-sources.md L79-80 改为："正向信号需≥2 个匹配才视为登录成功（避免误判）"
  2. login_manager.py `_check_login_status` 函数 docstring 与 data-sources.md 表述对齐
- **验收**：两处文档表述一致

### 任务 2.11 — 更新 README.md 目录结构（M9）

- **文件**：`README.md`
- **位置**：L107-122
- **当前**：列出 5 个 references 文件，实际 9 个
- **修复**：补全为
  ```
  references/
  ├── profile-schema.md
  ├── social-profiling.md
  ├── data-sources.md
  ├── scoring-model.md
  ├── html-spec.md
  ├── budget-advisor.md          # 新增
  ├── relationship-stages.md     # 新增
  ├── seasonal-guide.md          # 新增
  ├── flower-guide.md            # 新增
  └── memory-schema.md           # 新增（任务 2.2 产出）
  ```
- **附加**：scripts 目录补 `login_manager.py`（README 当前只列了 profile_manager.py）
- **验收**：README 目录结构与 `ls` 实际一致

---

## 阶段 3：P1 第二批 — 稳定性与配置外置

> 目标：提升脚本健壮性，外置硬编码配置，增加并发与原子性保护。

### 任务 3.1 — `_atomic_write` 捕获 PermissionError（E3）

- **文件**：`scripts/profile_manager.py`
- **位置**：L127-139
- **修复**：
  ```python
  def _atomic_write(p: Path, data: dict, max_retries: int = 3):
      for attempt in range(max_retries):
          tmp_fd, tmp_path = tempfile.mkstemp(dir=str(p.parent), suffix=".json.tmp")
          try:
              with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                  json.dump(data, f, ensure_ascii=False, indent=2)
              os.replace(tmp_path, str(p))
              return
          except PermissionError:
              try: os.unlink(tmp_path)
              except OSError: pass
              if attempt == max_retries - 1:
                  raise
              time.sleep(0.5 * (attempt + 1))
          except Exception:
              try: os.unlink(tmp_path)
              except OSError: pass
              raise
  ```
- **验收**：模拟文件占用场景，重试 3 次后才抛错

### 任务 3.2 — 登录态文件加并发锁（E4）

- **文件**：`scripts/login_manager.py`
- **修复**：在 cmd_login 和 cmd_check_and_login 入口加锁
  ```python
  import portalocker  # 需加到 requirements.txt
  LOCK_FILE = SESSION_DIR / ".login.lock"

  def _acquire_lock(channel: str, timeout: int = 30):
      SESSION_DIR.mkdir(parents=True, exist_ok=True)
      lock_path = SESSION_DIR / f"{channel}.lock"
      f = open(lock_path, "w")
      try:
          portalocker.lock(f, portalocker.LOCK_EX | portalocker.LOCK_NB)
          return f
      except portalocker.LockException:
          f.close()
          print(f"⚠️  {channel} 渠道正在被其他进程操作，等待 {timeout} 秒...")
          # 简单等待重试
          ...
  ```
- **备选方案**：若不愿加 portalocker 依赖，用 `msvcrt.locking`（Windows）/ `fcntl.flock`（Unix）原生实现
- **验收**：两个进程同时 `check_and_login taobao` 时第二个等待而非损坏 Profile

### 任务 3.3 — symlink 下 memory.json 路径用 realpath（E7）

- **文件**：`scripts/profile_manager.py`
- **位置**：L268 `skill_dir = Path(__file__).parent.parent`
- **修复**：
  ```python
  skill_dir = Path(os.path.realpath(__file__)).parent.parent
  ```
- **附加**：增加环境变量 `GIFT_PICKER_MEMORY_PATH` 显式指定 memory.json 路径，优先级最高
- **验收**：通过 symlink 加载 skill 时 memory.json 写入真实 skill 根目录

### 任务 3.4 — 规范 `gift_history.feedback` 为枚举（E8）

- **文件**：`references/profile-schema.md`、`scripts/profile_manager.py`、`references/budget-advisor.md`
- **修复**：
  1. profile-schema.md L37 改为：`"gift_history": [{"date": "YYYY-MM-DD", "gift": "礼物", "feedback": "positive|neutral|negative", "note": "可选备注"}]`
  2. profile_manager.py 在 `_deep_merge` 中校验 feedback 字段值，非法值降级为 `neutral` 并警告
  3. budget-advisor.md L72 "收到正面反馈 +10%"改为"feedback=positive 时 +10%"
- **验收**：写入非法 feedback 值时被规范化为 neutral

### 任务 3.5 — Step 6 阶段 1 加无浏览器降级路径（E9）

- **文件**：`SKILL.md` Step 6 阶段 1
- **修复**：在阶段 1 开头加：
  ```
  > 🔧 **运行时能力检测**：若当前 Agent 无 browser-use 能力（如 Codex/Claude Code 无浏览器工具），
  > 直接执行降级路径：用 WebSearch 做 `site:xiaohongshu.com <品类> 送女友` 检索，
  > 将 xiaohongshu.status 记为 `fallback`，报告 SOURCES_NOTE 注明"小红书口碑仅搜索引擎快照"。
  ```
- **验收**：无浏览器运行时下 Step 6 阶段 1 不再卡住

### 任务 3.6 — 画像 JSON 损坏恢复机制（S5）

- **文件**：`scripts/profile_manager.py`
- **位置**：L118-124 `_load` 函数
- **修复**：
  ```python
  def _load(p: Path, corrupt_tolerant: bool = False) -> dict:
      if not p.exists():
          return {}
      try:
          return json.loads(p.read_text(encoding="utf-8"))
      except json.JSONDecodeError:
          if not corrupt_tolerant:
              sys.exit(f"错误：{p} 内容损坏，请人工检查后再操作（未做任何修改）")
          # 损坏容错模式：备份原文件 + 返回空画像
          backup = p.with_suffix(f".json.corrupt.{int(time.time())}")
          p.rename(backup)
          print(f"⚠️  画像 {p.stem} 损坏，已备份到 {backup}，本次按空画像处理")
          return {}
  ```
- **附加**：cmd_list 调用时用 `corrupt_tolerant=True`，避免一个损坏画像阻塞整个 list
- **验收**：损坏画像存在时 `list` 命令仍能输出其他画像

### 任务 3.7 — 采集阶段硬超时（S6）

- **文件**：`SKILL.md` Step 6
- **修复**：在每个阶段开头加：
  ```
  > ⏱️ **阶段超时**：本阶段最多 5 分钟。超时后自动降级到下一阶段，
  > 在 memory.json.breakpoint 记录未完成项，报告 SOURCES_NOTE 注明数据不全。
  ```
- **验收**：SKILL.md Step 6 每个阶段都有超时说明

### 任务 3.8 — memory.json 原子写入（S7）

- **文件**：`SKILL.md` Step 6
- **修复**：在 Step 6 开头加注：
  ```
  > 🔴 **memory.json 写入必须用原子写入**：先写临时文件 `memory.json.tmp`，
  > 成功后 `os.replace` 替换原文件。避免崩溃导致 memory.json 损坏无法断点恢复。
  > 参考实现：scripts/profile_manager.py 的 `_atomic_write` 函数。
  ```
- **验收**：SKILL.md 明确要求 memory.json 原子写入

### 任务 3.9 — 登录重试上限（S3）

- **文件**：`SKILL.md` Step 5
- **修复**：L237 选项"我再试一次登录"后加注：
  ```
  > 🔴 **重试上限**：单渠道最多重试 2 次。第 3 次仍失败则强制跳过该渠道，
  > 标记为 failed，置信度降级。
  ```
- **验收**：SKILL.md Step 5 有明确的重试次数上限

### 任务 3.10 — 配置外置：channels.json（M1）

- **文件**：新建 `assets/channels.json`、修改 `scripts/login_manager.py`
- **修复**：
  1. 抽取 `CHANNEL_CONFIG` 到 `assets/channels.json`
  2. login_manager.py 改为：
     ```python
     CONFIG_PATH = Path(__file__).parent.parent / "assets" / "channels.json"
     with open(CONFIG_PATH, encoding="utf-8") as f:
         CHANNEL_CONFIG = json.load(f)
     ```
  3. SKILL.md 资源索引新增 `assets/channels.json` 引用
- **验收**：修改 channels.json 后无需改代码即可新增渠道

### 任务 3.11 — 配置外置：stages.json（M5）

- **文件**：新建 `references/stages.json`、修改 `scripts/profile_manager.py`、`references/profile-schema.md`、`references/relationship-stages.md`、`references/scoring-model.md`、`references/budget-advisor.md`
- **修复**：
  1. 新建 `references/stages.json`：
     ```json
     {
       "stages": [
         {"key": "pursuit", "cn": "追求期", "budget_range": [80, 300], "depth_coef": 0.7, ...},
         {"key": "honeymoon", "cn": "热恋期", "budget_range": [200, 800], ...},
         ...
       ]
     }
     ```
  2. profile_manager.py 的 `STAGE_CN` 改为从 stages.json 读取
  3. 各 reference 文档改为"详见 stages.json"而非硬编码表格
- **验收**：新增/修改阶段只需改 stages.json 一处

---

## 阶段 4：P2 优化迭代

> 目标：性能优化、代码清理、可读性提升。按需迭代，不阻断主流程。

### 任务 4.1 — `cmd_set` 拆分为小函数（M7）

- **文件**：`scripts/profile_manager.py`
- 拆分 `cmd_set`（L197-287）为：`_parse_patch(args)` / `_backup_profile(p)` / `_apply_merge_and_save(p, patch, nickname)` / `_cleanup_tmp(json_file_path)` / `_cleanup_memory_if_new()`
- **验收**：每个子函数 < 30 行

### 任务 4.2 — `_auto_nickname` 去 random（L11）

- **文件**：`scripts/profile_manager.py` L86-89
- 改为确定性兜底：基于 patch 内容的 hash 选后缀，或固定为"新画像"
- **验收**：同 patch 两次调用生成相同昵称

### 任务 4.3 — `_deep_merge` 用 set 优化去重（P5）

- **文件**：`scripts/profile_manager.py` L157
- 改为：
  ```python
  elif k in EXTEND_LIST_FIELDS and isinstance(v, list) and isinstance(base.get(k), list):
      existing = set(base[k])
      base[k].extend(item for item in v if item not in existing)
  ```
- **验收**：gift_history 100 条时合并耗时 < 10ms

### 任务 4.4 — 抽取共享 `_compat.py`（M4）

- **文件**：新建 `scripts/_compat.py`
- 内容：Windows 编码兼容块 + 通用工具函数（如 `_atomic_write`）
- profile_manager.py 和 login_manager.py 都 import
- **验收**：两脚本顶部不再重复编码兼容代码

### 任务 4.5 — `_path` 边界校验增强（E2）

- **文件**：`scripts/profile_manager.py` L108-114
- 增加：`if safe.endswith(".") or safe != safe.strip(): sys.exit(...)`
- **验收**：`"a."` / `" a"` 等边界输入被拒

### 任务 4.6 — `_sanitize_nickname` 处理 Unicode 控制字符（E11）

- **文件**：`scripts/profile_manager.py` L101-104
- 加 `unicodedata.normalize('NFKC', nickname)` + 过滤 `\u200b`/`\ufeff` 等
- **验收**：零宽空格等不可见字符被清理

### 任务 4.7 — `cmd_login` 删除重复 `browser.close()`（E6）

- **文件**：`scripts/login_manager.py` L278
- 删除该行，让 `with sync_playwright()` 自动管理
- **验收**：登录成功后无 "Cannot close already closed" 警告

### 任务 4.8 — `cmd_list` 仅读 `_meta` 优化 IO（P1）

- **文件**：`scripts/profile_manager.py` L182-186
- 改为只读文件首行或使用 `json.load` 流式解析
- **验收**：10 个画像时 list 耗时 < 100ms

### 任务 4.9 — 登录轮询改指数退避（P6）

- **文件**：`scripts/login_manager.py` L250
- `time.sleep(3)` 改为 `time.sleep(min(1 + checked * 0.5, 3))`
- **验收**：用户登录后检测延迟 < 1.5 秒

### 任务 4.10 — SKILL.md emoji 精简（M8）

- **文件**：`SKILL.md`
- 保留真正硬性规则的 🔴（约 5 处），其余 🔴 降为普通 `**` 加粗
- ⚠️ 保留警告类，删除重复警告
- **验收**：`grep "🔴" SKILL.md | wc -l` < 10

### 任务 4.11 — SKILL.md 与 references 去重（M2）

- **文件**：`SKILL.md`、`references/relationship-stages.md`、`references/profile-schema.md`
- SKILL.md Step 2 选项文本改为"见 relationship-stages.md"，不重复列出
- profile-schema.md 全量问答表改为"见 SKILL.md Step 1 情况 1"，不重复
- **验收**：选项文本只在一处定义

### 任务 4.12 — 补充 `migrate` / `clear` 命令文档（M10/M11）

- **文件**：`SKILL.md`
- Step 1 情况 2 加注："若 list 输出 schema 异常，先跑 `python scripts/profile_manager.py migrate`"
- Step 5 末尾加"清除登录态"小节，明确 `python scripts/login_manager.py clear <channel> --confirm`
- **验收**：两个命令在 SKILL.md 中有明确使用场景说明

### 任务 4.13 — 增加单元测试（M6）

- **文件**：新建 `scripts/test_profile_manager.py`
- 覆盖：`_deep_merge`（list 合并/dict 递归/null 删除）、`_auto_nickname`（各分支）、`_sanitize_nickname`（非法字符/长度）、`_path`（边界校验）
- **验收**：`python -m pytest scripts/test_profile_manager.py` 全过

### 任务 4.14 — 验证 report-template.html 占位符一致性（M12）

- **文件**：`assets/report-template.html`、`references/html-spec.md`
- diff 模板中的 `{{...}}` 占位符与 html-spec.md A/B/C 三类列表
- 补齐遗漏占位符或删除冗余
- **验收**：模板占位符与 html-spec.md 100% 匹配

---

## 文件改动矩阵

| 文件 | 阶段 1 | 阶段 2 | 阶段 3 | 阶段 4 | 总改动次数 |
|------|--------|--------|--------|--------|------------|
| SKILL.md | 1.1, 1.3, 1.4 | 2.1, 2.3, 2.4, 2.5, 2.6 | 3.5, 3.7, 3.8, 3.9 | 4.10, 4.11, 4.12 | 14 |
| scripts/profile_manager.py | 1.2 | 2.5, 2.6 | 3.1, 3.3, 3.4, 3.6, 3.11 | 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.8, 4.13 | 17 |
| scripts/login_manager.py | 1.4 | 2.7, 2.8, 2.9, 2.10 | 3.2, 3.10 | 4.4, 4.7, 4.9 | 11 |
| references/profile-schema.md | 1.3 | 2.6, 2.11 | 3.4, 3.11 | 4.11 | 7 |
| references/relationship-stages.md | - | 2.1 | 3.11 | 4.11 | 3 |
| references/data-sources.md | - | 2.10 | - | - | 1 |
| references/budget-advisor.md | - | - | 3.4, 3.11 | - | 2 |
| references/scoring-model.md | - | - | 3.11 | - | 1 |
| references/memory-schema.md（新建） | - | 2.2 | - | - | 1 |
| references/stages.json（新建） | - | - | 3.11 | - | 1 |
| assets/channels.json（新建） | - | - | 3.10 | - | 1 |
| scripts/_compat.py（新建） | - | - | - | 4.4 | 1 |
| scripts/test_profile_manager.py（新建） | - | - | - | 4.13 | 1 |
| README.md | - | 2.11 | - | - | 1 |
| requirements.txt | - | 2.7 | 3.2 | - | 2 |

---

## 验收标准

### 阶段 1 验收
- [ ] `grep "4 个选项" SKILL.md` 无结果
- [ ] `grep "long_term" scripts/ references/ -r` 无结果
- [ ] SKILL.md / profile-schema.md 关于 relationship_stage 存储位置表述一致
- [ ] 卸载 playwright 后 `python scripts/login_manager.py list` 输出友好提示

### 阶段 2 验收
- [ ] relationship-stages.md 含明示触发词表
- [ ] references/memory-schema.md 存在且字段完整
- [ ] SKILL.md L283 无"必须双渠道"绝对表述
- [ ] `python scripts/profile_manager.py list` 首行以 `NICKNAMES:` 开头
- [ ] Python 3.9 下 login_manager.py 无 SyntaxError
- [ ] state=None 时不抛 AttributeError
- [ ] Windows cmd 下 login_manager.py 中文输出无乱码
- [ ] data-sources.md 与 login_manager.py 信号检测描述一致
- [ ] README.md 目录结构与 `ls references/` 一致

### 阶段 3 验收
- [ ] 模拟文件占用，`_atomic_write` 重试 3 次后才抛错
- [ ] 两进程并发 `check_and_login taobao` 第二个等待
- [ ] symlink 加载时 memory.json 写入真实 skill 根
- [ ] 写入非法 feedback 值被规范化为 neutral
- [ ] 无浏览器运行时下 Step 6 阶段 1 走降级路径
- [ ] 损坏画像存在时 `list` 仍输出其他画像
- [ ] SKILL.md Step 6 每阶段有超时说明
- [ ] SKILL.md 要求 memory.json 原子写入
- [ ] SKILL.md Step 5 有重试上限
- [ ] channels.json / stages.json 存在且脚本读取

### 阶段 4 验收
- [ ] `cmd_set` 各子函数 < 30 行
- [ ] 同 patch 两次调用 `_auto_nickname` 结果一致
- [ ] gift_history 100 条合并 < 10ms
- [ ] `scripts/_compat.py` 存在且两脚本 import
- [ ] `"a."` / `" a"` 等边界昵称被拒
- [ ] 零宽空格昵称被清理
- [ ] 登录成功无 "Cannot close" 警告
- [ ] 10 画像 list < 100ms
- [ ] 用户登录后检测延迟 < 1.5 秒
- [ ] `grep "🔴" SKILL.md | wc -l` < 10
- [ ] 选项文本只在 relationship-stages.md 定义一次
- [ ] `python -m pytest scripts/test_profile_manager.py` 全过
- [ ] report-template.html 占位符与 html-spec.md 100% 匹配

---

## 执行建议

1. **阶段 1 单独一个 commit**：4 条改动独立、低风险，先合入主干
2. **阶段 2 拆两个 commit**：①文档一致性（2.1/2.3/2.4/2.10/2.11）；②脚本与 schema（2.2/2.5/2.6/2.7/2.8/2.9）
3. **阶段 3 拆三个 commit**：①脚本健壮性（3.1/3.3/3.6）；②并发与超时（3.2/3.7/3.8/3.9）；③配置外置（3.4/3.5/3.10/3.11）
4. **阶段 4 按需迭代**：每次 2-3 条，配合实际使用反馈优化

每个 commit 后跑一次端到端验证：`python scripts/profile_manager.py list && python scripts/profile_manager.py migrate && python scripts/login_manager.py list`
