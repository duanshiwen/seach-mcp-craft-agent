# Search Engine MCP

免费的多搜索引擎 MCP (Model Context Protocol) 服务器，支持 Google、Bing、Yahoo、DuckDuckGo 四个主流搜索引擎。

## ✨ 特性

- 🔍 **多引擎支持**：Google、Bing、Yahoo、DuckDuckGo
- 🆓 **完全免费**：无需 API 密钥，无需付费
- 🛡️ **反检测**：使用 undetected-chromedriver 绕过反爬虫检测
- 📦 **标准化输出**：返回结构化的搜索结果（标题、链接、摘要）
- 🔌 **MCP 协议**：兼容所有支持 MCP 的客户端（如 Craft Agent）
- 🐍 **Python 实现**：代码简洁，易于维护和扩展

## 🚀 快速开始

### 安装依赖

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -e .
```

### 运行服务器

```bash
# 直接运行
python -m src.server

# 或使用入口脚本
search-engine-mcp
```

### 在 Craft Agent 中使用

1. 将项目构建为可执行文件
2. 在 Craft Agent 中配置 MCP 源：

```json
{
  "type": "mcp",
  "name": "搜索引擎",
  "slug": "search-engine",
  "provider": "search-engine",
  "mcp": {
    "transport": "stdio",
    "command": "python",
    "args": ["-m", "src.server"],
    "authType": "none"
  }
}
```

## 📖 使用方法

### 搜索工具 (`search`)

执行搜索查询，返回结构化的搜索结果。

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `query` | string | ✅ | - | 搜索查询关键词 |
| `engine` | string | ❌ | `bing` | 搜索引擎选择 |
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

### 列出搜索引擎工具 (`list_engines`)

列出所有可用的搜索引擎及其描述。

**参数：** 无

**返回示例：**

```
**可用的搜索引擎：**

- **Google** (`google`)
  全球最大的搜索引擎

- **Bing** (`bing`)
  微软搜索引擎，中文搜索效果较好

- **Yahoo** (`yahoo`)
  雅虎搜索引擎

- **DuckDuckGo** (`duckduckgo`)
  注重隐私的搜索引擎
```

## 🛠️ 开发

### 项目结构

```
search-engine-mcp/
├── src/
│   ├── __init__.py          # 包初始化
│   ├── server.py            # MCP 服务器主入口
│   ├── types.py             # 类型定义
│   ├── utils.py             # 工具函数
│   └── engines/             # 搜索引擎实现
│       ├── __init__.py
│       ├── base.py          # 基类
│       ├── google.py        # Google 搜索
│       ├── bing.py          # Bing 搜索
│       ├── yahoo.py         # Yahoo 搜索
│       └── duckduckgo.py    # DuckDuckGo 搜索
├── pyproject.toml           # 项目配置
├── README.md               # 本文件
└── tests/                  # 测试文件（待添加）
```

### 代码规范

- 使用 Python 3.10+ 语法
- 遵循 PEP 8 规范
- 使用类型注解（Type Hints）
- 使用 Pydantic 进行数据验证

### 添加新搜索引擎

1. 在 `src/engines/` 目录创建新的引擎文件
2. 继承 `BaseSearchEngine` 基类
3. 实现 `search()` 和 `_parse_results()` 方法
4. 在 `__init__.py` 中导出新引擎
5. 在 `server.py` 中注册新引擎

## ⚠️ 注意事项

### 反检测说明

本项目使用 `undetected-chromedriver` 来绕过搜索引擎的反爬虫检测：

- ✅ 自动修改浏览器指纹
- ✅ 随机 User-Agent
- ✅ 模拟人类操作延迟
- ✅ 禁用自动化标志

### 使用限制

- 🚫 **请勿滥用**：频繁请求可能导致 IP 被临时封禁
- ⏱️ **建议延迟**：每次请求间隔 2-3 秒
- 📊 **结果数量**：建议每次请求 5 个结果，最多 10 个
- 🌐 **网络要求**：需要能够访问国际网络（Google、Yahoo）

### 已知问题

- 搜索引擎页面结构可能变化，需要定期更新选择器
- 首次启动浏览器需要一定时间（约 2-3 秒）
- 在某些网络环境下可能无法访问特定搜索引擎

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📧 联系方式

如有问题，请通过 GitHub Issues 反馈。
