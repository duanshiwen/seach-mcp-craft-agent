.PHONY: help install test run demo verify clean

# 默认目标
help:
	@echo "Search Engine MCP - 可用命令"
	@echo ""
	@echo "  make install    安装依赖"
	@echo "  make test       运行测试"
	@echo "  make run        启动 MCP 服务器"
	@echo "  make demo       运行演示"
	@echo "  make verify     验证配置"
	@echo "  make clean      清理临时文件"
	@echo "  make format     格式化代码"
	@echo "  make lint       代码检查"
	@echo ""

# 安装依赖
install:
	@echo "📦 安装依赖..."
	pip install -e .
	@echo "✅ 安装完成"

# 运行测试
test:
	@echo "🧪 运行测试..."
	pytest tests/ -v
	@echo "✅ 测试完成"

# 启动 MCP 服务器
run:
	@echo "🚀 启动 MCP 服务器..."
	python -m src.server

# 运行演示
demo:
	@echo "🎮 运行演示..."
	python demo.py

# 验证配置
verify:
	@echo "🔍 验证配置..."
	python verify_setup.py

# 清理临时文件
clean:
	@echo "🧹 清理临时文件..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -delete
	find . -type d -name ".mypy_cache" -delete
	find . -type d -name ".ruff_cache" -delete
	@echo "✅ 清理完成"

# 格式化代码
format:
	@echo "🎨 格式化代码..."
	ruff format .
	ruff check --fix .
	@echo "✅ 格式化完成"

# 代码检查
lint:
	@echo "🔍 代码检查..."
	ruff check .
	mypy src/
	@echo "✅ 检查完成"

# 测试搜索
test-search:
	@echo "🔍 测试搜索功能..."
	python test_search.py -e bing -q "Python 教程"

# 测试所有引擎
test-all:
	@echo "🔍 测试所有搜索引擎..."
	python test_search.py -e all -q "Python 教程"

# 构建包
build:
	@echo "📦 构建包..."
	pip install build
	python -m build
	@echo "✅ 构建完成"

# 安装到系统
install-global:
	@echo "📥 全局安装..."
	pip install .
	@echo "✅ 全局安装完成"
