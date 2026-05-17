#!/bin/bash
# Search Engine MCP 安装脚本

set -e

echo "🚀 开始安装 Search Engine MCP..."

# 检查 Python 版本
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python 版本: $python_version"

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "⚡ 激活虚拟环境..."
source venv/bin/activate

# 安装依赖
echo "📥 安装依赖..."
pip install -e .

echo ""
echo "✅ 安装完成！"
echo ""
echo "使用方法："
echo "  1. 激活虚拟环境: source venv/bin/activate"
echo "  2. 运行服务器: python -m src.server"
echo "  3. 测试搜索: python test_search.py -e bing -q '测试查询'"
echo ""
echo "在 Craft Agent 中使用："
echo "  将 craft-agent-config.json 的内容复制到你的 sources 配置中"
echo ""
