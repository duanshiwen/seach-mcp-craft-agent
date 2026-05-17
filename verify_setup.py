#!/usr/bin/env python3
"""配置验证脚本 - 检查环境和依赖是否满足要求。"""

import sys
import os
import subprocess
import importlib
from typing import List, Tuple


def check_python_version() -> Tuple[bool, str]:
    """检查 Python 版本。"""
    version = sys.version_info
    required = (3, 10)

    if version >= required:
        return True, f"Python {version.major}.{version.minor}.{version.micro}"
    else:
        return False, f"Python {version.major}.{version.minor}.{version.micro} (需要 >= {required[0]}.{required[1]})"


def check_dependency(package_name: str, import_name: str = None) -> Tuple[bool, str]:
    """检查依赖包是否已安装。"""
    try:
        if import_name:
            importlib.import_module(import_name)
        else:
            importlib.import_module(package_name)
        return True, package_name
    except ImportError:
        return False, package_name


def check_chrome() -> Tuple[bool, str]:
    """检查 Chrome 浏览器是否可用。"""
    try:
        # 尝试运行 chrome --version
        result = subprocess.run(
            ["google-chrome", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # 尝试其他 Chrome 路径
    chrome_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ]

    for path in chrome_paths:
        if os.path.exists(path):
            try:
                result = subprocess.run(
                    [path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return True, result.stdout.strip()
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

    return False, "Chrome 浏览器未找到"


def check_project_structure() -> Tuple[bool, List[str]]:
    """检查项目结构。"""
    required_files = [
        "src/__init__.py",
        "src/server.py",
        "src/types.py",
        "src/utils.py",
        "src/engines/__init__.py",
        "src/engines/base.py",
        "src/engines/google.py",
        "src/engines/bing.py",
        "src/engines/yahoo.py",
        "src/engines/duckduckgo.py",
        "pyproject.toml",
    ]

    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)

    return len(missing_files) == 0, missing_files


def run_verification():
    """运行所有验证检查。"""
    print("🔍 Search Engine MCP 配置验证")
    print("="*60)

    all_passed = True

    # 1. 检查 Python 版本
    print("\n1️⃣  检查 Python 版本...")
    passed, message = check_python_version()
    status = "✅" if passed else "❌"
    print(f"   {status} {message}")
    if not passed:
        all_passed = False

    # 2. 检查依赖包
    print("\n2️⃣  检查依赖包...")
    dependencies = [
        ("mcp", "mcp"),
        ("undetected-chromedriver", "undetected_chromedriver"),
        ("selenium", "selenium"),
        ("pydantic", "pydantic"),
    ]

    for package_name, import_name in dependencies:
        passed, message = check_dependency(package_name, import_name)
        status = "✅" if passed else "❌"
        print(f"   {status} {message}")
        if not passed:
            all_passed = False

    # 3. 检查 Chrome 浏览器
    print("\n3️⃣  检查 Chrome 浏览器...")
    passed, message = check_chrome()
    status = "✅" if passed else "❌"
    print(f"   {status} {message}")
    if not passed:
        all_passed = False

    # 4. 检查项目结构
    print("\n4️⃣  检查项目结构...")
    passed, missing_files = check_project_structure()
    if passed:
        print("   ✅ 项目结构完整")
    else:
        print("   ❌ 缺少以下文件:")
        for file in missing_files:
            print(f"      - {file}")
        all_passed = False

    # 总结
    print("\n" + "="*60)
    if all_passed:
        print("✅ 所有检查通过！配置正确。")
        print("\n下一步：")
        print("  1. 运行 'python test_search.py' 测试搜索功能")
        print("  2. 运行 'python demo.py' 查看演示")
        print("  3. 查看 QUICKSTART.md 了解如何在 Craft Agent 中使用")
    else:
        print("❌ 部分检查未通过，请修复上述问题。")
        print("\n常见解决方案：")
        print("  1. 安装依赖: pip install -e .")
        print("  2. 安装 Chrome: https://www.google.com/chrome/")
        print("  3. 检查 Python 版本: python --version")

    print("="*60)
    return all_passed


if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
