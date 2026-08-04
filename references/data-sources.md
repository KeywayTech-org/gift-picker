# 信息源策略（全免费）

## 渠道总览与优先级

| 优先级 | 渠道 | 获取方式 | 是否需登录 | 用途 |
|---|---|---|---|---|
| P0 | 小红书 | browser-use 读取公开主页/笔记/评论（**免费默认**） | 否（公开内容免登；部分笔记需登录可见，降级为搜索引擎 `site:xiaohongshu.com` 快照） | 真实口碑、种草款发现、差评挖掘 |
| P0 | 免费搜索引擎 | WebSearch 或 multi-search-engine skill | 否 | 品类调研、榜单、比价线索、测评文章 |
| P1 | 淘宝/天猫 | browser-use 浏览器自动化（用户本机登录态） | **是** | 价格、销量、评价区、购买链接 |
| P1 | 京东 | browser-use（商品页多数免登可看） | 部分 | 第二比价渠道、自营质量参考 |
| P2 | 什么值得买 / B站 / 微博 | 搜索引擎 `site:` 定向检索 | 否 | 历史低价、视频测评口碑 |

## 登录态技术实现

### 底层机制

本 Skill 使用 **Playwright 持久化浏览器上下文** 管理登录态，通过 `scripts/login_manager.py` 统一管理：

1. **持久化 Profile 目录**：每个渠道使用独立的浏览器用户数据目录（`sessions/<channel>_profile/`），存储 Cookie、LocalStorage、Service Worker 等全部浏览器状态
2. **手动登录流程**：Agent 调用 `login_manager.py login <channel>` → Playwright 以有头模式（`headless=False`）打开浏览器 → 用户在浏览器中手动完成登录 → 脚本轮询检测登录成功信号 → 保存状态
3. **登录态复用**：下次采集时 `login_manager.py check <channel>` 直接加载持久化 Profile，无需重新登录
4. **状态文件**：同时生成 `<channel>.json` Storage State 文件（cookies + localStorage），作为 Profile 的快速备份

### 登录管理脚本用法

```bash
# 查看所有已保存的登录态
python scripts/login_manager.py list

# 启动浏览器登录淘宝（300秒超时）
python scripts/login_manager.py login taobao

# 检查淘宝登录态是否有效
python scripts/login_manager.py check taobao

# 清除淘宝登录态
python scripts/login_manager.py clear taobao --confirm
```

### 支持的渠道

| 渠道 | 配置键 | 登录页 URL | 校验方式 |
|------|--------|-----------|----------|
| 淘宝/天猫 | `taobao` | `login.taobao.com` | 检查首页用户信息元素 |
| 京东 | `jd` | `passport.jd.com` | 检查首页用户信息元素 |
| 小红书 | `xiaohongshu` | `xiaohongshu.com` | 检查首页登录状态 |

### 登录态校验流程

```
阶段 2：登录态检查
  │
  ├─ 1. 对需登录的渠道逐个执行：
  │     python scripts/login_manager.py check <channel>
  │
  ├─ 2. 检查逻辑（login_manager.py 内部）：
  │     ├─ 加载持久化 Profile / Storage State
  │     ├─ 以 headless 模式打开渠道首页
  │     ├─ 检测正向信号（用户信息元素、非登录页 URL）
  │     ├─ 检测负向信号（登录页 URL、"请登录"文本）
  │     └─ 返回结果：ok / expired / unknown
  │
  ├─ 3. 状态判定：
  │     ├─ status=ok → 在 memory.json 记录，继续下一渠道
  │     ├─ status=expired → 执行 login 命令重新登录
  │     └─ status=unknown → 降级或尝试重新登录
  │
  └─ 4. 登录流程（login 命令）：
        ├─ 以 headed 模式打开登录页
        ├─ 轮询检测登录成功信号（每3秒检查一次）
        ├─ 成功后保存 Profile + Storage State
        └─ 超时则提示用户重试
```

### 登录态信号检测

每个渠道在 `login_manager.py` 的 `CHANNEL_CONFIG` 中定义了两组信号：

**正向信号（任一满足即视为登录成功）**：
- URL 不包含登录域（如 `login.taobao.com`）
- 页面存在用户昵称/头像元素
- 页面包含"你好"等问候文本

**负向信号（任一满足即视为失效）**：
- URL 跳转至登录域
- 页面出现"请登录"提示
- 登录框元素存在

### 登录态失效熔断

采集过程中 Agent 持续监控登录态，失效信号包括：
- 页面 URL 跳转包含 `login`、`captcha`、`verify` 等关键词
- 页面 DOM 出现"登录"按钮且无用户信息
- 接口返回 `{code: -1, message: "请登录"}` 类结构
- 出现滑块验证码/人机验证页面

**熔断动作**：
1. 立即停止该渠道的所有后续抓取（不重试、不换姿势硬爬）
2. 在 `memory.json` 记录断点（已完成的商品、待采集清单）
3. 告知用户"淘宝登录态已失效，请重新登录后告诉我"
4. 用户确认后执行 `login_manager.py check <channel>` 或 `login <channel>`
5. 校验通过后从 `memory.json` 记录的断点继续

## 各渠道采集要点

### 小红书（口碑层）
- 用关键词搜索笔记（如"<品类> 送女友""<品牌><品类> 真实测评""<品类> 踩雷"）。
- 正反两面都要搜：种草词 + "踩雷/避雷/翻车"词，读评论区提炼真实差评点。
- 产出：候选商品名单、口碑摘要（好评点/差评点各 2~3 条）、热度参考（点赞/收藏量）。
- 登录说明：小红书公开内容免登可读。Step 5 不自动检测小红书登录态（与淘宝/京东不同）。如果遇到需要登录才能查看的笔记，降级为搜索引擎 `site:xiaohongshu.com` 快照检索，不影响采集流程。

### 搜索引擎（调研层）
- 品类榜单："2026 <品类> 推荐""<预算>元 送女友 <场景> 礼物"。
- 定向检索：`site:smzdm.com <商品名>`（历史价格）、`site:zhihu.com <商品名> 值得买吗`。

### 淘宝/天猫（交易层，需登录）
- browser-use 搜索商品 → 按销量排序取头部 2~3 家店 → 记录：到手价、券后价、月销、店铺类型（旗舰/专营）、评价区"最新+差评"各抽 5~10 条、**商品主图直接图片地址**、**商品详情页直接 URL**。
- 节流：每页面操作间隔 2~3 秒，单渠道单任务不超过 ~15 个页面，降低风控概率。
- 🔴 **链接规则**：商品页 URL 必须是详情页直接链接（如 `https://detail.tmall.com/item.htm?id=...`、`https://item.taobao.com/item.htm?id=...`），禁止使用搜索页链接（`https://s.taobao.com/search?q=...`）。图片地址必须是 `<img src="...">` 的值（如 `https://img.alicdn.com/imgextra/...`），不是页面 URL。

### 京东（比价层）
- 商品页免登可读价格与部分评价；需登录内容缺失时只取价格与链接。
- 🔴 **链接规则**：商品页 URL 必须是详情页直接链接（如 `https://item.jd.com/100028813901.html`），禁止使用搜索页链接（`https://search.jd.com/Search?keyword=...`）。图片地址必须是 `<img src="...">` 或 `data-lazy-img` 的值（如 `https://img10.360buyimg.com/n1/jfs/...`）。

## 降级路径

- 淘宝不可用 → 京东 + 搜索引擎聚合价（标注"非实时价，置信度低"）。
- 小红书接口不可用 → 搜索引擎 `site:xiaohongshu.com` 快照检索。
- 图片抓取失败 → HTML 报告中使用内置 SVG 占位图（已在模板中实现）。
- 任一维度数据不足 → 按 scoring-model.md 的置信度规则降权，禁止编造。

## 合规红线

- 只读采集，不做任何下单、加购、评论、点赞等写操作。
- 不绕过验证码/风控，不使用他人账号，不采集卖家/买家个人信息。
- 采集数据仅用于本次报告，随 memory.json 清理。
- 本 skill 仅用免费公开信息源与用户本人浏览器登录态，不含任何付费接口或密钥，分发包亦不含任何真实密钥。