# 搜索引擎 MCP

免费的多搜索引擎 API 工具，支持 Google、Bing、DuckDuckGo、Yahoo、百度五个搜索引擎。Google 使用 Playwright JS 渲染 + 语义结构解析（基于 h3 标题 + a 链接，不依赖 CSS 类名），其他引擎使用轻量 HTTP 请求。

## 功能特性

- **多引擎支持**：可在五个搜索引擎之间切换
- **结构化输出**：返回标题、链接、摘要的标准格式
- **完全免费**：无需 API 密钥或付费订阅
- **智能渲染**：Google 使用 Playwright JS 渲染，其他引擎使用 HTTP 请求

## 使用方法

### 搜索查询

使用 `search` 工具进行搜索：

**基本用法：**
```json
{
  "query": "深圳市天气",
  "engine": "duckduckgo",
  "max_results": 5
}
```

**参数说明：**
- `query`（必填）：搜索查询关键词
- `engine`（可选）：搜索引擎选择，默认 `duckduckgo`
  - `duckduckgo` - DuckDuckGo 搜索（推荐，稳定可靠，轻量 HTTP）
  - `bing` - Bing 搜索（中文效果好，轻量 HTTP）
  - `google` - Google 搜索（Playwright JS 渲染，结果最全但较慢）
  - `yahoo` - Yahoo 搜索（轻量 HTTP）
  - `baidu` - 百度搜索（中文内容搜索，轻量 HTTP）
- `max_results`（可选）：返回结果数量，默认 5，最大 10

### 列出搜索引擎

使用 `list_engines` 工具查看所有可用的搜索引擎：

```json
{}
```

### 获取网页内容

使用 `web_fetch` 工具获取指定 URL 的正文内容，自动转为 AI 友好的 Markdown 格式：

**基本用法：**
```json
{
  "url": "https://example.com/article"
}
```

**参数说明：**
- `url`（必填）：要获取的完整网页 URL
- `extract_mode`（可选）：输出格式，默认 `markdown`
  - `markdown` - 保留标题、链接、表格等 Markdown 格式（推荐）
  - `text` - 纯文本，无格式标记
- `render_mode`（可选）：渲染模式，默认 `auto`
  - `auto` - 先用轻量 HTTP 提取；检测到 JS-only 页面时自动 fallback 到浏览器渲染
  - `http` - 强制轻量 HTTP 模式，速度最快
  - `js` - 强制 Playwright/Chromium 渲染，适合 SPA 或需要 JavaScript 的页面
- `wait_until`（可选）：JS 渲染等待策略，默认 `networkidle`
  - 可选：`load`、`domcontentloaded`、`networkidle`、`commit`
- `timeout_ms`（可选）：请求或渲染超时时间，默认 `30000`，范围 3000-120000 毫秒

**特性：**
- 🧹 自动去除广告、导航栏、页脚等干扰内容
- 📝 智能提取正文，保留核心信息
- 🔗 支持保留超链接和表格结构
- 🧩 支持 JS 渲染页面（SPA / React / Vue 等）
- 📊 内容过长时自动截断（10 万字符上限）

## 使用场景

### 1. 获取实时信息

查询天气、新闻、股票等实时信息：

```json
{
  "query": "今天深圳天气",
  "engine": "duckduckgo"
}
```

### 4. 深入阅读搜索结果

先搜索找到相关页面，再获取完整内容：

**第一步：搜索**
```json
{
  "query": "Python asyncio 最佳实践",
  "engine": "duckduckgo",
  "max_results": 5
}
```

**第二步：获取感兴趣的文章全文**
```json
{
  "url": "https://搜索结果中的某个链接"
}
```

### 5. 获取纯文本（无格式）

适合需要纯文本分析的场景：

```json
{
  "url": "https://example.com/article",
  "extract_mode": "text"
}
```

### 6. 获取需要 JavaScript 渲染的网页

默认 `auto` 会自动检测并 fallback 到 JS 渲染；也可以强制使用 `js`：

```json
{
  "url": "https://example.com/spa-article",
  "render_mode": "js",
  "wait_until": "networkidle",
  "timeout_ms": 45000
}
```

**注意：** JS 渲染比 HTTP 模式更慢、更耗资源；遇到登录墙、强反爬、Cloudflare 等情况仍可能失败。

### 2. 技术问题查询

查询技术文档、解决方案：

```json
{
  "query": "Python asyncio 教程",
  "engine": "bing",
  "max_results": 10
}
```

### 3. 产品信息查询

查询产品评价、价格等信息：

```json
{
  "query": "iPhone 15 评测",
  "engine": "duckduckgo"
}
```

## 返回格式

搜索结果以 Markdown 格式返回，包含：

```
**DuckDuckGo 搜索结果：**

1. **标题**
   链接: https://example.com/...
   摘要: 搜索结果的摘要内容...

2. **标题**
   链接: https://example.com/...
   摘要: 搜索结果的摘要内容...
```

## 最佳实践

### 1. 选择合适的搜索引擎

- **DuckDuckGo**（推荐）：稳定可靠，轻量 HTTP，无 CAPTCHA，速度最快
- **Bing**：中文搜索效果好，轻量 HTTP，偶尔有 CAPTCHA
- **Google**：全球最全的搜索结果，使用 Playwright JS 渲染，较慢但成功率高
- **百度**：中文内容搜索效果好，适合国内搜索
- **Yahoo**：综合搜索，结果质量中等

**选择建议：**
- 日常快速查询 → DuckDuckGo 或 Bing
- 需要最全结果 → Google（接受较慢速度）
- 中文内容 → Bing 或百度

### 2. 优化搜索词

- 使用简洁明了的关键词
- 可以使用引号搜索精确短语：`"机器学习"`
- 可以使用减号排除关键词：`苹果 -手机`

### 3. 控制结果数量

- 日常查询：5 个结果足够
- 深度研究：10 个结果
- 快速查看：3 个结果

## 注意事项

### 使用限制

- ⚠️ **请求频率**：建议每次请求间隔 2-3 秒
- 📊 **结果数量**：每次最多返回 10 个结果
- 🌐 **网络要求**：需要能够访问国际网络

### 可能的问题

1. **搜索超时**
   - 检查网络连接
   - 尝试其他搜索引擎
   - 减少结果数量

2. **结果不准确**
   - 优化搜索关键词
   - 尝试不同的搜索引擎
   - 使用更具体的关键词

3. **页面结构变化**
   - 搜索引擎可能更新页面结构
   - 需要更新解析器（联系开发者）

## 技术细节

- **传输协议**：stdio（标准输入输出）
- **认证方式**：无认证（公开服务）
- **请求方式**：
  - DuckDuckGo/Bing/Yahoo/百度：HTTP 请求（httpx + selectolax）
  - Google：Playwright JS 渲染 + 语义结构解析
- **Google 解析策略**：基于 #main 容器 + h3 标题 + a 链接的语义结构，不依赖特定 CSS 类名（如 div.g, div.tF2Cxc 等）
  - `#main`：稳定的主容器（ID 属性，非 class），所有搜索结果都在此容器内
  - `h3`：Google 搜索结果标题始终使用 h3 标签
  - `a`：标题被包裹在 a 链接标签中
  - 自动提取真实 URL（处理 Google 重定向）
- **响应时间**：
  - HTTP 引擎：1-3 秒
  - Google（JS 渲染）：3-5 秒

## 集成示例

### 在 Craft Agent 中使用

用户：帮我查一下今天深圳的天气

Agent：我来帮您查询深圳的天气信息。

```json
{
  "query": "今天深圳天气",
  "engine": "duckduckgo",
  "max_results": 5
}
```

返回结果后，Agent 会整理并回答用户。

### 批量查询

如果需要查询多个主题，可以依次调用：

```json
{
  "query": "深圳天气",
  "engine": "duckduckgo"
}
```

```json
{
  "query": "深圳新闻",
  "engine": "bing"
}
```

## 故障排除

### 问题：搜索失败

**可能原因：**
- 网络连接问题
- 搜索引擎暂时不可用
- 页面结构变化

**解决方案：**
1. 检查网络连接
2. 尝试其他搜索引擎
3. 等待一段时间后重试

### 问题：结果不准确

**可能原因：**
- 搜索关键词不够具体
- 搜索引擎返回的结果不符合预期

**解决方案：**
1. 优化搜索关键词
2. 尝试不同的搜索引擎
3. 增加结果数量以获取更多选项

## 更新日志

### v1.4.0 (2026-05-22)
- **重大更新**：Google 搜索改用 Playwright JS 渲染，成功绕过 CAPTCHA
- **解析策略重构**：
  - 使用 `#main` 作为稳定容器（ID 属性，非 class）
  - 在 `#main` 内查找 `h3` 标题 + `a` 链接
  - 不依赖特定 CSS 类名（div.g, div.tF2Cxc 等都可能变化）
  - 自动处理 Google 重定向 URL，提取真实链接
- 修正错误提示信息
- 更新文档说明各引擎的渲染方式和解析策略
- **验证结果**：Google 搜索现已完全可用，可返回 10+ 结果

### v1.3.0 (2026-05-19)
- `web_fetch` 新增 JavaScript 渲染能力，支持 Playwright/Chromium
- 新增 `render_mode` 参数：`auto`、`http`、`js`
- 新增 `wait_until` 与 `timeout_ms` 参数，控制 JS 渲染等待策略和超时
- 默认 `auto` 模式会先走快速 HTTP 提取，检测到 JS-only 页面时自动 fallback 到 JS 渲染

### v1.2.0 (2026-05-19)
- 新增 `web_fetch` 工具，获取 URL 正文并转为 AI 友好的 Markdown
- 基于 trafilatura 智能提取，自动去除广告和噪声
- 支持 markdown 和 text 两种输出模式

### v1.1.0 (2026-05-17)
- 重写为 HTTP 请求方式（httpx + selectolax）
- 移除浏览器驱动依赖（undetected-chromedriver、selenium）
- Google 搜索暂不支持（需要 JS 渲染）
- 提升稳定性和响应速度

### v1.0.0 (2026-05-17)
- 初始版本发布
- 支持 Google、Bing、Yahoo、DuckDuckGo 四个搜索引擎
- 实现 MCP 协议集成
- 添加反检测功能
