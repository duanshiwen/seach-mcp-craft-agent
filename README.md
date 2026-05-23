# Search Engine MCP

免费的多搜索引擎 MCP (Model Context Protocol) 服务器，支持 Google、Bing、Yahoo、DuckDuckGo、百度五个主流搜索引擎，以及 `web_fetch` 网页内容提取工具。

## ✨ 特性

- 🔍 **五引擎支持**：Google（Playwright JS 渲染）、Bing、DuckDuckGo、Yahoo、百度
- 🌐 **网页提取**：`web_fetch` 工具获取 URL 正文，自动转为 AI 友好的 Markdown
- 🆓 **完全免费**：无需 API 密钥，无需付费
- 📦 **标准化输出**：返回结构化的搜索结果（标题、链接、摘要）
- 🔌 **MCP 协议**：兼容所有支持 MCP 的客户端（如 Craft Agent）
- 🐍 **Python 实现**：代码简洁，易于维护和扩展

## 搜索引擎技术实现

| 引擎 | 渲染方式 | 速度 | 特点 |
|------|----------|------|------|
| **DuckDuckGo**（默认） | 轻量 HTTP (httpx + selectolax) | 1-3 秒 | 稳定可靠，无 CAPTCHA |
| **Bing** | 轻量 HTTP | 1-3 秒 | 中文搜索效果好 |
| **百度** | 轻量 HTTP | 1-3 秒 | 国内内容搜索 |
| **Yahoo** | 轻量 HTTP | 1-3 秒 | 综合搜索 |
| **Google** | Playwright JS 渲染 | 3-5 秒 | 结果最全，语义结构解析（h3+a）；触发 CAPTCHA 时自动弹出可见浏览器窗口等待手动验证 |

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
│       ├── base.py          # 基类（BaseSearchEngine）
│       ├── google.py        # Google 搜索（Playwright JS 渲染 + 语义结构解析）
│       ├── bing.py          # Bing 搜索（HTTP）
│       ├── duckduckgo.py    # DuckDuckGo 搜索（HTTP）
│       ├── yahoo.py         # Yahoo 搜索（HTTP）
│       └── baidu.py         # 百度搜索（HTTP）
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

1. 在 `src/engines/` 目录创建新的引擎文件
2. 继承 `BaseSearchEngine` 基类
3. 实现 `search()` 和 `_parse_results()` 方法
4. 在 `__init__.py` 中导出新引擎
5. 在 `server.py` 的 `TOOLS` 和 `get_search_engine()` 中注册

## 使用建议

### 引擎选择

- **日常快速查询** → DuckDuckGo（推荐，稳定快速）
- **中文搜索** → Bing 或百度
- **需要最全结果** → Google（接受较慢速度）
- **隐私优先** → DuckDuckGo

### 深入阅读搜索结果

1. 先用 `search` 找到相关页面
2. 再用 `web_fetch` 获取感兴趣的文章全文

```json
{ "query": "Rust async 最佳实践", "engine": "duckduckgo", "max_results": 5 }
```

```json
{ "url": "https://搜索结果中的某个链接", "extract_mode": "markdown" }
```

## 🤖 Google CAPTCHA 手动验证

当 Google 检测到自动化请求并弹出 CAPTCHA 人机验证时，搜索引擎会自动处理：

1. 🔍 **首次尝试**：使用 headless Playwright 浏览器访问 Google
2. 🚫 **检测到 CAPTCHA**：关闭 headless 浏览器，stderr 输出提示信息
3. 🖥️ **弹出可见窗口**：启动非 headless Chromium 浏览器，显示 Google 验证页面
4. ✋ **等待手动完成**：每 2 秒轮询检测 CAPTCHA 状态
5. ✅ **验证通过**：自动提取搜索结果并返回
6. ⏰ **超时**：默认等待 120 秒，超时后返回空结果并建议换引擎

> **提示**：弹出窗口时会在终端看到明显的提示信息。完成验证后窗口会自动关闭。

## ⚠️ 注意事项

- ⏱️ **请求频率**：建议每次请求间隔 2-3 秒，避免被引擎限制
- 📊 **结果数量**：每次最多返回 10 个结果
- 🌐 **网络要求**：Google / Yahoo / DuckDuckGo 需要访问国际网络
- 🤖 **CAPTCHA 处理**：Google 搜索被 CAPTCHA 拦截时，会自动弹出可见浏览器窗口（非 headless）等待用户手动完成人机验证，验证通过后自动提取搜索结果并返回。默认等待 120 秒，超时后返回空结果并提示使用其他搜索引擎

## 📄 许可证

MIT License
