# 🚀 MCP 迁移指南

## 概述

本指南说明如何将 Search Engine MCP 服务器迁移到另一个 Craft Agent 工作区。

## 迁移步骤

### 方法一：完整复制（推荐）

#### 1. 复制项目目录

```bash
# 源目录
SOURCE_DIR="/Users/yakii/code/search-engine-mcp"

# 目标工作区（替换为你的目标工作区路径）
TARGET_WORKSPACE="/Users/yakii/.craft-agent/workspaces/your-workspace"
TARGET_DIR="$TARGET_WORKSPACE/sources/search-engine-mcp"

# 创建目标目录
mkdir -p "$TARGET_DIR"

# 复制项目文件
cp -r "$SOURCE_DIR"/* "$TARGET_DIR/"
```

#### 2. 在目标工作区安装依赖

```bash
cd "$TARGET_DIR"
uv sync
```

#### 3. 创建 Craft Agent 源配置

在目标工作区创建配置文件：

```bash
cat > "$TARGET_DIR/config.json" << 'EOF'
{
  "id": "search-engine-mcp_a1b2c3d4",
  "name": "搜索引擎 MCP",
  "slug": "search-engine-mcp",
  "enabled": true,
  "provider": "search-engine",
  "type": "mcp",
  "icon": "🔍",
  "tagline": "免费的多搜索引擎 API 工具，支持 Google、Bing、Yahoo、DuckDuckGo",
  "mcp": {
    "transport": "stdio",
    "command": "uv",
    "args": ["run", "python", "-m", "src.server"],
    "env": {
      "PYTHONPATH": "$TARGET_DIR"
    },
    "authType": "none"
  }
}
EOF
```

**注意：** 将 `$TARGET_DIR` 替换为实际的绝对路径。

#### 4. 复制使用指南和权限配置

```bash
# 复制指南文件
cp "$SOURCE_DIR/guide.md" "$TARGET_DIR/"
cp "$SOURCE_DIR/permissions.json" "$TARGET_DIR/"
```

#### 5. 测试连接

在 Craft Agent 中运行：

```
source_test({ sourceSlug: "search-engine-mcp" })
```

---

### 方法二：符号链接（节省空间）

如果你希望多个工作区共享同一个 MCP 服务器：

#### 1. 创建共享目录

```bash
# 创建共享目录
SHARED_DIR="/Users/yakii/.craft-agent/shared-sources/search-engine-mcp"
mkdir -p "$SHARED_DIR"

# 复制项目到共享目录
cp -r /Users/yakii/code/search-engine-mcp/* "$SHARED_DIR/"

# 在共享目录安装依赖
cd "$SHARED_DIR"
uv sync
```

#### 2. 在目标工作区创建符号链接

```bash
# 目标工作区
TARGET_WORKSPACE="/Users/yakii/.craft-agent/workspaces/your-workspace"
TARGET_DIR="$TARGET_WORKSPACE/sources/search-engine-mcp"

# 创建符号链接
ln -s "$SHARED_DIR" "$TARGET_DIR"
```

#### 3. 创建配置文件

```bash
cat > "$TARGET_DIR/config.json" << 'EOF'
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
    "command": "uv",
    "args": ["run", "python", "-m", "src.server"],
    "env": {
      "PYTHONPATH": "/Users/yakii/.craft-agent/shared-sources/search-engine-mcp"
    },
    "authType": "none"
  }
}
EOF
```

---

### 方法三：打包分发

如果你需要将 MCP 分发给其他人：

#### 1. 创建安装包

```bash
cd /Users/yakii/code/search-engine-mcp

# 创建安装脚本
cat > install-mcp.sh << 'INSTALL_SCRIPT'
#!/bin/bash
set -e

echo "📦 安装 Search Engine MCP..."

# 检查 uv
if ! command -v uv &> /dev/null; then
    echo "❌ 需要安装 uv: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# 获取安装目录
INSTALL_DIR="${1:-$HOME/.craft-agent/sources/search-engine-mcp}"
mkdir -p "$INSTALL_DIR"

# 复制文件
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/"

# 安装依赖
cd "$INSTALL_DIR"
uv sync

# 创建配置文件
cat > config.json << EOF
{
  "id": "search-engine-mcp_$(openssl rand -hex 4)",
  "name": "搜索引擎 MCP",
  "slug": "search-engine-mcp",
  "enabled": true,
  "provider": "search-engine",
  "type": "mcp",
  "icon": "🔍",
  "tagline": "免费的多搜索引擎 API 工具",
  "mcp": {
    "transport": "stdio",
    "command": "uv",
    "args": ["run", "python", "-m", "src.server"],
    "env": {
      "PYTHONPATH": "$INSTALL_DIR"
    },
    "authType": "none"
  }
}
EOF

echo "✅ 安装完成！"
echo ""
echo "下一步："
echo "1. 在 Craft Agent 中测试: source_test({ sourceSlug: 'search-engine-mcp' })"
echo "2. 查看使用指南: cat $INSTALL_DIR/guide.md"
INSTALL_SCRIPT

chmod +x install-mcp.sh
```

#### 2. 打包项目

```bash
# 创建 tar.gz 包
tar -czf search-engine-mcp.tar.gz \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.git' \
  -C /Users/yakii/code \
  search-engine-mcp

echo "📦 包已创建: search-engine-mcp.tar.gz"
```

#### 3. 在目标机器安装

```bash
# 解压
tar -xzf search-engine-mcp.tar.gz

# 运行安装脚本
cd search-engine-mcp
./install-mcp.sh /path/to/target/workspace/sources/search-engine-mcp
```

---

## 配置文件说明

### config.json 字段说明

```json
{
  "id": "search-engine-mcp_a1b2c3d4",  // 唯一标识符
  "name": "搜索引擎 MCP",               // 显示名称
  "slug": "search-engine-mcp",         // URL 友好的标识符
  "enabled": true,                      // 是否启用
  "provider": "search-engine",          // 提供商
  "type": "mcp",                        // 源类型
  "icon": "🔍",                         // 图标
  "tagline": "简短描述",                // 简短描述
  "mcp": {
    "transport": "stdio",               // 传输协议
    "command": "uv",                    // 命令
    "args": ["run", "python", "-m", "src.server"],  // 参数
    "env": {                            // 环境变量
      "PYTHONPATH": "/absolute/path/to/search-engine-mcp"
    },
    "authType": "none"                  // 认证类型
  }
}
```

### 重要提示

1. **PYTHONPATH** 必须是绝对路径
2. **command** 使用 `uv` 确保使用正确的 Python 环境
3. **id** 必须在工作区内唯一

---

## 验证迁移

### 1. 测试 MCP 服务器

```bash
cd /path/to/search-engine-mcp
uv run python -c "from src.server import server; print('✅ 服务器模块正常')"
```

### 2. 测试搜索功能

```bash
uv run python test_search.py -e bing -q "测试查询"
```

### 3. 测试 Craft Agent 集成

在 Craft Agent 中运行：

```
# 列出可用工具
mcp__search-engine-mcp__list_engines

# 测试搜索
mcp__search-engine-mcp__search({
  "query": "今天天气",
  "engine": "bing",
  "max_results": 3
})
```

---

## 故障排除

### 问题：找不到 Python 模块

**解决方案：**
```bash
# 检查 PYTHONPATH 是否正确
echo $PYTHONPATH

# 确保使用 uv 运行
uv run python -m src.server
```

### 问题：ChromeDriver 版本不匹配

**解决方案：**
```bash
uv pip install --upgrade undetected-chromedriver
```

### 问题：权限错误

**解决方案：**
```bash
chmod +x install-mcp.sh
chmod -R 755 /path/to/search-engine-mcp
```

### 问题：网络连接失败

**解决方案：**
1. 检查网络连接
2. 尝试其他搜索引擎
3. 使用代理（如果需要）

---

## 快速迁移命令

### 一键迁移到新工作区

```bash
#!/bin/bash
# migrate-mcp.sh

SOURCE="/Users/yakii/code/search-engine-mcp"
TARGET_WORKSPACE="$1"

if [ -z "$TARGET_WORKSPACE" ]; then
    echo "用法: ./migrate-mcp.sh <目标工作区路径>"
    echo "示例: ./migrate-mcp.sh /Users/yakii/.craft-agent/workspaces/my-workspace"
    exit 1
fi

TARGET="$TARGET_WORKSPACE/sources/search-engine-mcp"

echo "🚀 迁移 Search Engine MCP"
echo "   源: $SOURCE"
echo "   目标: $TARGET"
echo ""

# 创建目录
mkdir -p "$TARGET"

# 复制文件
cp -r "$SOURCE"/* "$TARGET/"
rm -rf "$TARGET/.venv"
rm -rf "$TARGET/__pycache__"

# 安装依赖
cd "$TARGET"
uv sync

# 创建配置
cat > config.json << EOF
{
  "id": "search-engine-mcp_$(openssl rand -hex 4)",
  "name": "搜索引擎 MCP",
  "slug": "search-engine-mcp",
  "enabled": true,
  "provider": "search-engine",
  "type": "mcp",
  "icon": "🔍",
  "tagline": "免费的多搜索引擎 API 工具",
  "mcp": {
    "transport": "stdio",
    "command": "uv",
    "args": ["run", "python", "-m", "src.server"],
    "env": {
      "PYTHONPATH": "$TARGET"
    },
    "authType": "none"
  }
}
EOF

echo ""
echo "✅ 迁移完成！"
echo ""
echo "在 Craft Agent 中测试:"
echo "  source_test({ sourceSlug: 'search-engine-mcp' })"
```

使用方法：

```bash
chmod +x migrate-mcp.sh
./migrate-mcp.sh /Users/yakii/.craft-agent/workspaces/your-workspace
```

---

## 总结

| 方法 | 适用场景 | 优点 | 缺点 |
|------|---------|------|------|
| 完整复制 | 单个工作区 | 简单直接 | 占用空间 |
| 符号链接 | 多个工作区共享 | 节省空间 | 依赖共享目录 |
| 打包分发 | 分发给其他人 | 便于分享 | 需要安装步骤 |

**推荐：** 使用完整复制方法，简单可靠。
