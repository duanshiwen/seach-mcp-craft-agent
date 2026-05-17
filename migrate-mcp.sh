#!/bin/bash
# Search Engine MCP 迁移脚本
# 用法: ./migrate-mcp.sh <目标工作区路径>

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 源目录
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 检查参数
if [ -z "$1" ]; then
    echo -e "${RED}错误: 请提供目标工作区路径${NC}"
    echo ""
    echo "用法: ./migrate-mcp.sh <目标工作区路径>"
    echo ""
    echo "示例:"
    echo "  ./migrate-mcp.sh /Users/yakii/.craft-agent/workspaces/my-workspace"
    echo "  ./migrate-mcp.sh ~/.craft-agent/workspaces/dailyai"
    exit 1
fi

# 解析目标路径
TARGET_WORKSPACE="$(cd "$1" 2>/dev/null && pwd)" || {
    echo -e "${RED}错误: 目标路径不存在: $1${NC}"
    exit 1
}

TARGET_DIR="$TARGET_WORKSPACE/sources/search-engine-mcp"

echo -e "${GREEN}🚀 Search Engine MCP 迁移工具${NC}"
echo ""
echo "源目录: $SOURCE_DIR"
echo "目标目录: $TARGET_DIR"
echo ""

# 确认迁移
read -p "确认迁移? (y/N): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "已取消迁移"
    exit 0
fi

# 创建目标目录
echo -e "${YELLOW}📁 创建目标目录...${NC}"
mkdir -p "$TARGET_DIR"

# 复制文件（排除虚拟环境和缓存）
echo -e "${YELLOW}📋 复制文件...${NC}"
rsync -av --progress \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache' \
    --exclude='.mypy_cache' \
    --exclude='.ruff_cache' \
    "$SOURCE_DIR/" "$TARGET_DIR/"

# 安装依赖
echo -e "${YELLOW}📦 安装依赖...${NC}"
cd "$TARGET_DIR"

# 检查 uv 是否可用
if ! command -v uv &> /dev/null; then
    echo -e "${RED}错误: 需要安装 uv${NC}"
    echo "安装方法: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# 清理旧的虚拟环境
rm -rf .venv

# 安装依赖
uv sync

# 创建配置文件
echo -e "${YELLOW}⚙️  创建配置文件...${NC}"
cat > config.json << EOF
{
  "id": "search-engine-mcp_$(openssl rand -hex 4)",
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

# 验证安装
echo -e "${YELLOW}🔍 验证安装...${NC}"
if uv run python -c "from src.server import server; print('✅ 服务器模块正常')" 2>/dev/null; then
    echo -e "${GREEN}✅ 模块导入成功${NC}"
else
    echo -e "${RED}❌ 模块导入失败${NC}"
    exit 1
fi

# 完成
echo ""
echo -e "${GREEN}✅ 迁移完成！${NC}"
echo ""
echo "📁 目标目录: $TARGET_DIR"
echo ""
echo "下一步:"
echo "1. 在 Craft Agent 中测试连接:"
echo "   source_test({ sourceSlug: 'search-engine-mcp' })"
echo ""
echo "2. 查看使用指南:"
echo "   cat $TARGET_DIR/guide.md"
echo ""
echo "3. 测试搜索功能:"
echo "   cd $TARGET_DIR && uv run python test_search.py -e bing -q '测试查询'"
echo ""
