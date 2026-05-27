# Search Engine MCP

免费的多搜索引擎 MCP (Model Context Protocol) 服务器，支持 Google、Bing、Yahoo、DuckDuckGo、百度五个主流搜索引擎，以及 `web_fetch` 网页内容提取工具。

## ✨ 特性

- 🔍 **五引擎支持**：Google、Bing、百度（可见浏览器模式 + CAPTCHA 处理）、DuckDuckGo、Yahoo（轻量 HTTP）
- 🌐 **网页提取**：`web_fetch` 工具获取 URL 正文，自动转为 AI 友好的 Markdown
- 🆓 **完全免费**：无需 API 密钥，无需付费
- 📦 **标准化输出**：返回结构化的搜索结果（标题、链接、摘要）
- 🔌 **MCP 协议**：兼容所有支持 MCP 的客户端（如 Craft Agent）
- 🐍 **Python 实现**：代码简洁，易于维护和扩展
- 🖥️ **智能浏览器管理**：全局队列锁，同一时间只允许一个浏览器窗口弹出

## 搜索引擎技术实现

| 引擎 | 渲染方式 | 速度 | 特点 |
|------|----------|------|------|
| **DuckDuckGo**（默认） | 轻量 HTTP (httpx + selectolax) | 1-3 秒 | 稳定可靠，无 CAPTCHA |
| **Yahoo** | 轻量 HTTP | 1-3 秒 | 综合搜索 |
| **Google** | 可见浏览器模式 | 3-10 秒；遇到 CAPTCHA 取决于人工验证时间 | 结果最全，语义结构解析（h3+a）；直接打开明文浏览器搜索，拿到结果后自动关闭；触发 CAPTCHA 时在同一窗口等待手动验证 |
| **Bing** | 可见浏览器模式 + HTTP fallback | 3-10 秒 | 中文搜索效果好；浏览器模式失败时自动回退到轻量 HTTP |
| **百度** | 可见浏览器模式 + HTTP fallback | 3-10 秒 | 国内内容搜索；浏览器模式失败时自动回退到轻量 HTTP（移动端入口） |

> **注意**：Google/Bing/百度三个浏览器引擎共享全局队列锁，同一时间只允许一个引擎弹出浏览器窗口。

## 🚀 快速开始

### 安装依赖

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -e .
```

### 安装 Playwright 浏览器（Google 搜索需要）

```bash
playwright install chromium
```

### 运行服务器

```bash
# 直接运行
python -m src.server

# 或使用入口脚本
search-engine-mcp
```

### 在 Craft Agent 中使用

在 Craft Agent 中配置 MCP 源：

```json
{
  "type": "mcp",
  "name": "搜索引擎 MCP",
  "slug": "search-engine-mcp",
  "provider": "search-engine",
  "mcp": {
    "transport": "stdio",
    "command": "<venv-path>/bin/python",
    "args": ["-m", "src.server"],
    "cwd": "<project-path>",
    "authType": "none"
  }
}
```

> 将 `<venv-path>` 和 `<project-path>` 替换为实际的虚拟环境和项目路径。

## 📖 工具说明

### 1. 搜索工具 (`search`)

执行搜索查询，返回结构化的搜索结果。

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `query` | string | ✅ | - | 搜索查询关键词 |
| `engine` | string | ❌ | `duckduckgo` | 搜索引擎：`duckduckgo` / `bing` / `google` / `yahoo` / `baidu` |
| `max_results` | integer | ❌ | `5` | 最大返回结果数量（1-10） |

**示例：**

```json
{
  "query": "深圳市天气",
  "engine": "bing",
  "max_results": 5
}
```

**返回示例：**

```
**Bing 搜索结果：**

1. **深圳市天气预报**
   链接: https://weather.com/...
   摘要: 今天深圳天气晴朗，气温 25-30°C...

2. **深圳天气_百度百科**
   链接: https://baike.baidu.com/...
   摘要: 深圳市位于广东省南部...
```

### 2. 列出搜索引擎 (`list_engines`)

列出所有可用的搜索引擎及其描述。

**参数：** 无

### 3. 网页内容提取 (`web_fetch`)

获取指定 URL 的网页正文，自动转为 AI 友好的 Markdown 格式。

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `url` | string | ✅ | - | 要获取的完整网页 URL |
| `extract_mode` | string | ❌ | `markdown` | 输出格式：`markdown`（保留格式）/ `text`（纯文本） |
| `render_mode` | string | ❌ | `auto` | 渲染模式：`auto`（自动检测）/ `http`（轻量）/ `js`（Playwright 渲染） |
| `wait_until` | string | ❌ | `networkidle` | JS 渲染等待策略：`load` / `domcontentloaded` / `networkidle` / `commit` |
| `timeout_ms` | integer | ❌ | `30000` | 超时时间（3000-120000 毫秒） |

**特性：**
- 🧹 自动去除广告、导航栏、页脚等干扰内容
- 📝 智能提取正文，保留核心信息
- 🔗 支持保留超链接和表格结构
- 🧩 `auto` 模式自动检测 JS-only 页面并 fallback 到浏览器渲染
- 📊 内容过长时自动截断（10 万字符上限）

**示例：**

```json
{
  "url": "https://example.com/article",
  "extract_mode": "markdown",
  "render_mode": "auto"
}
```

## 🛠️ 开发

### 项目结构

```
search-engine-mcp/
├── src/
│   ├── __init__.py          # 包初始化
│   ├── server.py            # MCP 服务器主入口（search / list_engines / web_fetch）
│   ├── types.py             # 类型定义（SearchEngine, SearchResult 等）
│   ├── utils.py             # 工具函数（格式化、验证、日志等）
│   ├── fetcher.py           # web_fetch 实现（trafilatura + Playwright）
│   └── engines/             # 搜索引擎实现
│       ├── __init__.py
│       ├── base.py          # HTTP 基类（BaseSearchEngine）
│       ├── browser_base.py  # 浏览器基类（BrowserSearchEngine）— 统一浏览器生命周期、CAPTCHA 处理、队列锁
│       ├── google.py        # Google 搜索（继承 BrowserSearchEngine）
│       ├── bing.py          # Bing 搜索（继承 BrowserSearchEngine + HTTP fallback）
│       ├── baidu.py         # 百度搜索（继承 BrowserSearchEngine + HTTP fallback）
│       ├── duckduckgo.py    # DuckDuckGo 搜索（继承 BaseSearchEngine，轻量 HTTP）
│       └── yahoo.py         # Yahoo 搜索（继承 BaseSearchEngine，轻量 HTTP）
├── pyproject.toml           # 项目配置与依赖
├── README.md                # 本文件
├── guide.md                 # Craft Agent 集成指南
└── tests/                   # 测试文件
```

### 依赖

| 依赖 | 用途 |
|------|------|
| `mcp` | MCP 协议实现 |
| `httpx` | 异步 HTTP 客户端 |
| `selectolax` | 高性能 HTML 解析 |
| `trafilatura` | 网页正文智能提取 |
| `playwright` | Google 搜索 JS 渲染 |
| `pydantic` | 数据验证 |
| `brotlicffi` | Brotli 压缩支持 |

### 添加新搜索引擎

**轻量 HTTP 引擎（如 DuckDuckGo/Yahoo）：**

1. 在 `src/engines/` 目录创建新的引擎文件
2. 继承 `BaseSearchEngine` 基类
3. 实现 `search()` 和 `_parse_results()` 方法
4. 在 `__init__.py` 中导出新引擎
5. 在 `server.py` 的 `TOOLS` 和 `get_search_engine()` 中注册

**浏览器模式引擎（如 Google/Bing/百度）：**

1. 在 `src/engines/` 目录创建新的引擎文件
2. 继承 `BrowserSearchEngine` 基类
3. 设置 `ENGINE_NAME` 和 `PROFILE_DIR_NAME` 类属性
4. 实现抽象方法：
   - `_get_search_url(query)` — 构造搜索 URL
   - `_is_blocked(html, url)` — 检测 CAPTCHA/拦截
   - `_extract_results_js` (property) — JavaScript 提取结果代码
5. 可选：重写 `search()` 方法添加 HTTP fallback
6. 在 `__init__.py` 中导出新引擎
7. 在 `server.py` 的 `TOOLS` 和 `get_search_engine()` 中注册

## 使用建议

### 引擎选择

- **日常快速查询** → DuckDuckGo 或 Yahoo（轻量 HTTP，无需浏览器，1-3 秒）
- **中文搜索** → Bing 或百度（浏览器模式，3-10 秒）
- **需要最全结果** → Google（浏览器模式，3-10 秒）
- **隐私优先** → DuckDuckGo

> **提示**：Google/Bing/百度使用浏览器模式时会弹出可见浏览器窗口。同一时间只能有一个浏览器窗口（全局队列锁）。

### 深入阅读搜索结果

1. 先用 `search` 找到相关页面
2. 再用 `web_fetch` 获取感兴趣的文章全文

```json
{ "query": "Rust async 最佳实践", "engine": "duckduckgo", "max_results": 5 }
```

```json
{ "url": "https://搜索结果中的某个链接", "extract_mode": "markdown" }
```

## 🤖 浏览器模式搜索与 CAPTCHA 手动验证

Google、Bing、百度三个引擎均采用 **可见浏览器优先** 的方式：

1. 🖥️ **直接打开明文浏览器窗口**：启动一个可见的 Chrome / Chromium 持久化浏览器上下文，并访问搜索页
2. 🔍 **自动提取结果**：页面出现搜索结果后，使用 Playwright 从页面结构中提取标题、链接、摘要
3. ✅ **自动关闭窗口**：一旦成功提取搜索结果，自动关闭本次搜索打开的浏览器窗口并返回结果
4. ✋ **遇到 CAPTCHA**：如果搜索引擎触发人机验证，用户在同一个可见浏览器窗口中手动完成验证
5. 🔁 **持续轮询**：程序每 2 秒检查一次页面是否已经出现可提取的搜索结果
6. ⏰ **超时返回空结果**：默认最多等待 300 秒；超时后返回空结果并建议换用 DuckDuckGo / Yahoo
7. 🔒 **全局队列锁**：同一时间只允许一个引擎弹出浏览器窗口，避免资源冲突

> **提示**：
> - 各引擎使用独立的专用浏览器 profile，不会复用或清理用户日常 Chrome profile
> - 拿到结果后窗口会自动关闭；如果正在 CAPTCHA 验证，请不要手动关闭窗口
> - Bing/百度在浏览器模式失败时会自动回退到轻量 HTTP 模式

### 环境变量

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SEARCH_ENGINE_MCP_CAPTCHA_TIMEOUT` | `300` | 所有浏览器引擎 CAPTCHA 验证最长等待秒数（统一配置） |
| `SEARCH_ENGINE_MCP_GOOGLE_PROFILE_DIR` | `~/.craft-agent/browser-profiles/search-engine-mcp-google` | Google 搜索专用浏览器 profile 目录 |
| `SEARCH_ENGINE_MCP_BING_PROFILE_DIR` | `~/.craft-agent/browser-profiles/search-engine-mcp-bing` | Bing 搜索专用浏览器 profile 目录 |
| `SEARCH_ENGINE_MCP_BAIDU_PROFILE_DIR` | `~/.craft-agent/browser-profiles/search-engine-mcp-baidu` | 百度搜索专用浏览器 profile 目录 |

### 诊断文件

当搜索、CAPTCHA 或窗口行为异常时，可以查看以下文件：

| 文件 | 说明 |
|------|------|
| `google_captcha_debug.log` | Google 搜索与浏览器流程诊断日志 |
| `bing_captcha_debug.log` | Bing 搜索与浏览器流程诊断日志 |
| `baidu_captcha_debug.log` | 百度搜索与浏览器流程诊断日志 |
| `google_last_captcha_url.txt` | 最近一次触发 Google CAPTCHA 的 URL |
| `mcp_runtime_debug.log` | MCP server 层 tool 调用与搜索运行诊断日志 |

## ⚠️ 注意事项

- ⏱️ **请求频率**：建议每次请求间隔 2-3 秒，避免被引擎限制
- 📊 **结果数量**：每次最多返回 10 个结果
- 🌐 **网络要求**：Google / Yahoo / DuckDuckGo 需要访问国际网络
- 🤖 **CAPTCHA 处理**：Google/Bing/百度使用可见浏览器窗口；被 CAPTCHA 拦截时，用户在同一窗口手动完成人机验证，验证通过并出现搜索结果后自动提取并关闭窗口。默认等待 300 秒（统一配置），超时后返回空结果并提示使用其他搜索引擎
- 🔒 **浏览器队列**：同一时间只允许一个浏览器窗口弹出，其他浏览器引擎搜索请求会排队等待

## 📄 许可证

MIT License
