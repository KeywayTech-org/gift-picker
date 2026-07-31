# Changelog

所有重要变更将记录在此文件中。

## [1.2.0] - 2026-07-31

### 新增
- **Playwright 登录态管理**：新增 `scripts/login_manager.py`，基于 Playwright 持久化浏览器上下文实现登录态管理
  - `login` 命令：启动有头浏览器让用户手动登录，自动检测成功并保存状态
  - `check` 命令：无头模式校验登录态有效性
  - `list` 命令：列出所有已保存的登录态
  - `clear` 命令：清除指定渠道的登录态
  - 支持淘宝、京东、小红书三个渠道
  - 自动检测正向/负向登录信号（URL、DOM元素、文本内容）
- **SKILL.md 集成**：登录态检查流程从依赖 browser-use 改为 Playwright login_manager.py
- **data-sources.md 重写**：登录态技术实现全面更新为 Playwright 架构
- **.gitignore 更新**：增加 `sessions/` 目录排除

## [1.1.0] - 2026-07-30

### 新增
- **画像 Schema 版本管理**：新增 `schema_version` 字段和 `migrate` 命令，支持旧版画像自动迁移
- **环境变量配置**：存储路径可通过 `GIFT_PICKER_HOME` 环境变量覆盖
- **评分权重预设**：新增 4 种评分偏好预设（均衡/性价比优先/品质优先/口碑优先），用户可按需选择
- **登录态技术文档**：`data-sources.md` 新增完整的登录态底层机制、校验流程和熔断策略说明
- **断点 JSON 化**：`memory.md` 升级为 `memory.json`，结构化存储任务状态，支持可靠的断点恢复
- **离线兜底**：HTML 模板在 Chart.js 加载失败时显示友好提示

### 修复
- **P0 安全：路径遍历防护**：`_path()` 增加 `..` 和点前缀检查，限制昵称长度 50 字符
- **P0 安全：XSS 防护**：HTML 模板注释明确要求所有占位符数据必须 HTML 转义；模板内嵌图片加载失败的 SVG fallback
- **P0 数据：写入备份**：`cmd_set()` 写入前自动备份，写入失败自动恢复
- **P0 数据：原子写入**：用 `tempfile` + `os.replace` 实现原子写入，防止中断损坏
- **P1 健壮：错误处理**：`_atomic_write()` 捕获 OSError，`cmd_set()` 捕获 json-file 读取异常
- **P1 逻辑：深度合并**：`_deep_merge()` 对 `colors_like`、`allergies` 等数组字段采用 extend+去重合并，而非整体替换
- **P1 逻辑：cmd_list 简化**：消除重复的目录存在性检查
- **P2 体验：图片 fallback**：`onerror` 替换为 SVG 占位图 + CSS 错误样式

## [1.0.0] - 2026-07-29

### 初始版本
- 恋人画像管理（持久化 + 增量合并）
- 社媒 ID 一键画像（小红书/微博/B站/抖音）
- 多渠道采集（小红书口碑 + 搜索引擎 + 淘宝/京东）
- 四维评分模型（价格/质量/好评/差评反向）
- HTML 礼物清单报告（含雷达图 + 多渠道比价 + AI 分析）
- Agent Skills 开放标准兼容