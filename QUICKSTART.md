# 🚀 快速启动指南

## 一分钟上手

### 1. 安装依赖

```bash
cd /Users/yakii/code/search-engine-mcp
chmod +x install.sh
./install.sh
```

### 2. 测试搜索功能

```bash
# 激活虚拟环境
source venv/bin/activate

# 测试 Bing 搜索
python test_search.py -e bing -q "今天深圳天气"

# 测试所有搜索引擎
python test_search.py -e all -q "Python 教程"
```

### 3. 在 Craft Agent 中使用

将以下配置添加到你的 Craft Agent sources 目录：

**文件位置：** `~/.craft-agent/workspaces/dailyai/sources/search-engine-mcp/config.json`

```json
{
  "id": "search-engine-mcp_a1b2c3d4",
  "name": "搜索引擎 MCP",
  "slug": "search-engine-mcp",
  "enabled": true,
  "provider": "search-engine",
  "type": "mcp",
  "icon": "🔍",
  "tagline": "免费的多搜索引擎 API 工具",
  "mcp": {
    "transport": "stdio",
    "command": "/Users/yakii/code/search-engine-mcp/venv/bin/python",
    "args": ["-m", "src.server"],
    "env": {
      "PYTHONPATH": "/Users/yakii/code/search-engine-mcp"
    },
    "authType": "none"
  }
}
```

**复制使用指南：**
```bash
cp guide.md ~/.craft-agent/workspaces/dailyai/sources/search-engine-mcp/
cp permissions.json ~/.craft-agent/workspaces/dailyai/sources/search-engine-mcp/
```

### 4. 测试 MCP 连接

在 Craft Agent 中运行：
```
source_test({ sourceSlug: "search-engine-mcp" })
```

## 常用命令

### 搜索测试

```bash
# 测试单个引擎
python test_search.py -e google -q "搜索词"
python test_search.py -e bing -q "搜索词"
python test_search.py -e yahoo -q "搜索词"
python test_search.py -e duckduckgo -q "搜索词"

# 测试所有引擎
python test_search.py -e all -q "搜索词"
```

### 运行 MCP 服务器

```bash
# 直接运行
python -m src.server

# 后台运行（用于 Craft Agent）
nohup python -m src.server > server.log 2>&1 &
```

### 运行测试

```bash
# 运行单元测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_engines.py -v
```

## 故障排除

### 问题：ImportError: No module named 'src'

**解决方案：**
```bash
export PYTHONPATH=/Users/yakii/code/search-engine-mcp
```

### 问题：ChromeDriver 版本不匹配

**解决方案：**
```bash
pip install --upgrade undetected-chromedriver
```

### 问题：搜索超时

**可能原因：**
- 网络连接问题
- 搜索引擎暂时不可用

**解决方案：**
1. 检查网络连接
2. 尝试其他搜索引擎
3. 减少结果数量：`max_results=3`

## 下一步

- 📖 阅读完整的 [README.md](README.md) 了解详细用法
- 🔧 查看 [guide.md](guide.md) 了解在 Craft Agent 中的使用方法
- 🧪 运行测试确保功能正常
- 🚀 开始使用搜索引擎功能！

## 获取帮助

- 查看项目文档
- 提交 GitHub Issue
- 联系开发者

---

**祝你使用愉快！** 🎉
