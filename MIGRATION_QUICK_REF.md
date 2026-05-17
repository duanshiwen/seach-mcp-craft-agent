# 🚀 MCP 迁移快速参考

## 一键迁移命令

```bash
# 迁移到新工作区
cd /Users/yakii/code/search-engine-mcp
./migrate-mcp.sh /path/to/target/workspace

# 示例：迁移到 dailyai 工作区
./migrate-mcp.sh /Users/yakii/.craft-agent/workspaces/dailyai
```

## 迁移后验证

### 1. 测试 MCP 服务器

```bash
cd /path/to/search-engine-mcp
uv run python test_search.py -e bing -q "测试查询"
```

### 2. 在 Craft Agent 中测试

```
# 测试连接
source_test({ sourceSlug: "search-engine-mcp" })

# 列出工具
mcp__search-engine-mcp__list_engines

# 测试搜索
mcp__search-engine-mcp__search({
  "query": "今天天气",
  "engine": "bing",
  "max_results": 3
})
```

## 配置文件位置

迁移后，配置文件位于：

```
/path/to/workspace/sources/search-engine-mcp/config.json
```

## 常见问题

### Q: 如何更新到新版本？

```bash
# 1. 更新源代码
cd /Users/yakii/code/search-engine-mcp
git pull

# 2. 重新迁移
./migrate-mcp.sh /path/to/workspace
```

### Q: 如何卸载？

```bash
rm -rf /path/to/workspace/sources/search-engine-mcp
```

### Q: 如何查看日志？

```bash
# 在 Craft Agent 中查看
# 或手动运行服务器查看输出
cd /path/to/search-engine-mcp
uv run python -m src.server
```

## 详细文档

- 📖 [完整迁移指南](MIGRATION_GUIDE.md)
- 📖 [项目文档](README.md)
- 📖 [快速启动](QUICKSTART.md)
- 📖 [使用指南](guide.md)
