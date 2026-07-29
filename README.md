# 礼物挑选助手（gift-picker）

帮男生为女朋友 / 老婆 / 心仪之人挑礼物的 AI skill。

一次配置恋人画像，输入预算与场景，自动从多渠道采集候选商品、做四维评分与画像匹配，
生成一份带图片、评分图表、AI 分析、多渠道比价与购买链接的 **HTML 礼物清单**。

---

## 核心能力

1. **恋人画像配置（持久化）**：颜色 / 护肤美妆品牌 / 穿衣风格 / 香调 / 尺码 / 兴趣 / 过敏忌口 / 已有物品避重。支持后续增量更新，存于用户目录 `~/.workbuddy/gift-picker/profiles/`，不随 skill 分发。
2. **社媒 ID 一键画像（最高优先级）**：给她的小红书 / 微博 / B站 / 抖音号，自动分析公开内容，先在**对话内**（不落盘）生成喜好报告，你确认后再进入选品。
3. **多渠道采集 + 四维评分**：价格 / 质量 / 优质好评度 / 差评率（反向）+ 独立的「画像匹配度」，数据不足时标注置信度，不编造。
4. **HTML 礼物清单**：礼物卡片（图 / 名 / 价）+ 评分雷达图与评分条 + AI 推荐理由与匹配逐条对照 + 多渠道比价表 + 购买链接。

---

## 安装

### 方式一：WorkBuddy 用户（最常见）

1. 把本目录软链 / 复制到 `~/.workbuddy/skills/gift-picker`。
2. 免费路径开箱即用，无需任何 Key 或付费账户。
3. 在对话中说：「帮我给女朋友挑生日礼物」即可触发。

### 方式二：独立 Python 环境

- 画像管理：`python scripts/profile_manager.py --help`
- 本 skill 的 AI 编排逻辑写在 `SKILL.md`，需由支持 skill 的 Agent 运行时解释执行。

---

## 在其他 Agent / 运行时中使用本 Skill

本 Skill 采用 **Agent Skills 开放标准**编写（一个含 `SKILL.md` 的目录，frontmatter 含 `name` / `description`），可被遵循该标准的多种 Agent 直接加载，无需重写。下面列出常见运行时的安装方式。

### WorkBuddy（原生运行时）
见上方「安装 → 方式一」。本 Skill 为 WorkBuddy 设计，所有能力（browser-use 采集、WebSearch、交互式提问、HTML 报告预览）开箱即用。

### Claude Code（Anthropic）
Claude Code 原生支持 Agent Skills，目录约定：
- 用户级（所有项目可用）：`~/.claude/skills/gift-picker/`（Windows：`C:\Users\<用户名>\.claude\skills\gift-picker\`）
- 项目级（仅当前仓库）：`<项目>/.claude/skills/gift-picker/`

```bash
# 方式 A：从 GitHub 克隆
git clone https://github.com/Keyway-tech/gift-picker ~/.claude/skills/gift-picker
# 方式 B：通用 skills CLI
npx skills add Keyway-tech/gift-picker -a claude
```
触发：在 Claude Code 中输入 `/gift-picker`，或描述任务让其按 `description` 自动匹配。

### Codex（OpenAI）
Codex 同样遵循 Agent Skills 标准，从 `.agents/skills` 发现技能：
- 用户级：`~/.agents/skills/gift-picker/`（Windows：`C:\Users\<用户名>\.agents\skills\gift-picker\`）
- 项目级：`<仓库>/.agents/skills/gift-picker/`
- 机器级：`/etc/codex/skills/`（Linux / macOS）

```bash
# 方式 A：通用 skills CLI（指定 codex）
npx skills add Keyway-tech/gift-picker -a codex -g
# 方式 B：Codex 会话内内置安装器
$skill-installer https://github.com/Keyway-tech/gift-picker
# 方式 C：手动克隆
git clone https://github.com/Keyway-tech/gift-picker ~/.agents/skills/gift-picker
```
触发：在 Codex 中输入 `$gift-picker`，或运行 `/skills` 浏览，或描述任务让其隐式匹配。

### 通用 skills CLI（70+ Agent 适用）
开源 `skills` CLI 支持 Codex、Claude Code、Cursor、OpenCode 等 70+ 编码 Agent，一条命令即可安装：
```bash
npx skills add Keyway-tech/gift-picker          # 项目级
npx skills add Keyway-tech/gift-picker -g       # 全局级
npx skills add Keyway-tech/gift-picker -a codex # 指定运行时
```
常用管理：`npx skills list` / `npx skills update` / `npx skills remove gift-picker`。

### ⚠️ 跨运行时兼容性注意
本 Skill 的**工作流逻辑（SKILL.md + references）是通用的**，但其中引用了若干 **WorkBuddy 专有能力**，在其他 Agent 中需作等价替换才能完整运行：

| WorkBuddy 专有 | 在他处替换为 |
|---|---|
| `browser-use`（读取对方公开主页） | 目标 Agent 的浏览器 / 网页读取工具 |
| `WebSearch` / 多搜索引擎 | 目标 Agent 的搜索工具 |
| 交互式提问 `AskUserQuestion` | 目标 Agent 的提问 / 表单能力或直接对话追问 |
| `present_files` 的 HTML 预览 | "写出 HTML 文件并交回用户" |
| `scripts/profile_manager.py` 运行方式 | 保持用本地 Python 执行，路径自行调整 |

若您仅需"参考工作流"在某 Agent 中复用，直接把 `SKILL.md` / `references/` 内容粘贴进对应 Agent 的 skill / 指令上下文即可。

---

## 数据来源与费用（务必阅读）

| 路径 | 费用 | 说明 |
|---|---|---|
| **全免费主路径** | 免费 | `browser-use` + `WebSearch`，用你**自己已登录**的浏览器读取公开主页 / 笔记 / 评论 / 比价。零依赖、开箱即用，满足"全免费"约束，无需任何密钥或付费账户。 |

> 本 skill **不内置任何密钥**，也不依赖任何付费接口；分发包即为完整可用的免费版本。

---

## 目录结构

```
gift-picker/
├── SKILL.md                      # 主入口：工作流总控、硬性规则、资源索引
├── README.md                     # 本文件
├── LICENSE                       # 非商业许可（不可免费商用）
├── .gitignore                    # 排除密钥与运行时数据
├── references/
│   ├── profile-schema.md         # 画像字段 + 获取策略（社媒ID>截图>速写>问答）
│   ├── social-profiling.md       # 社媒 ID 一键画像流程与 7 维分析
│   ├── data-sources.md           # 信息源策略 + 登录态协议 + 降级路径
│   ├── scoring-model.md          # 四维评分 + 画像匹配 + 置信度
│   └── html-spec.md              # 报告结构规范
├── assets/
│   └── report-template.html      # 礼物清单模板（卡片+Chart.js+比价表）
└── scripts/
    └── profile_manager.py        # 画像读写/合并/校验
```

---

## 隐私与合规

- **仅分析公开内容**：不登录对方账号、不采集私密收藏 / 私信 / 联系方式 / 可精确定位信息。
- **只读采集**：不做下单、加购、评论、点赞等任何写操作；不绕过风控；不使用他人账号。
- **中间数据自清**：任务中间数据写在 skill 目录 `memory.md`，报告交付后自动删除；恋人画像存于用户目录，不随包外泄。
- **免责声明**：本 skill 与小红书 / 微博 / B站 / 抖音 等平台**无隶属关系**；使用者须遵守各平台服务条款与所在地区法律法规；因使用本 skill 产生的任何行为后果由使用者自行承担。

---

## 许可

**非商业许可（Non-Commercial License）**——允许个人、非商业用途的使用、修改与再分发；**禁止任何商业使用**（含出售、转售、商业集成、商业再分发），商业使用须获得作者书面授权。详见 `LICENSE`。
