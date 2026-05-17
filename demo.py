#!/usr/bin/env python3
"""Search Engine MCP 演示脚本。"""

import asyncio
import json
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.server import handle_list_tools, handle_call_tool


async def demo_list_tools():
    """演示列出工具功能。"""
    print("\n" + "="*60)
    print("📋 列出可用工具")
    print("="*60)

    tools = await handle_list_tools()

    for tool in tools:
        print(f"\n🔧 工具名称: {tool.name}")
        print(f"   描述: {tool.description}")
        print(f"   参数: {json.dumps(tool.inputSchema, indent=2, ensure_ascii=False)}")


async def demo_search():
    """演示搜索功能。"""
    print("\n" + "="*60)
    print("🔍 搜索演示")
    print("="*60)

    # 测试查询
    test_queries = [
        {"query": "Python 教程", "engine": "bing", "max_results": 3},
        {"query": "今天天气", "engine": "google", "max_results": 2},
    ]

    for i, params in enumerate(test_queries, 1):
        print(f"\n--- 测试 {i}: {params['query']} (引擎: {params['engine']}) ---")

        try:
            result = await handle_call_tool("search", params)

            if result and hasattr(result[0], 'text'):
                print(result[0].text)
            else:
                print("⚠️  未返回结果")

        except Exception as e:
            print(f"❌ 错误: {e}")

        print()


async def demo_list_engines():
    """演示列出搜索引擎功能。"""
    print("\n" + "="*60)
    print("🌐 列出可用搜索引擎")
    print("="*60)

    try:
        result = await handle_call_tool("list_engines", {})

        if result and hasattr(result[0], 'text'):
            print(result[0].text)
        else:
            print("⚠️  未返回结果")

    except Exception as e:
        print(f"❌ 错误: {e}")


async def main():
    """主演示函数。"""
    print("🚀 Search Engine MCP 演示")
    print("="*60)
    print("这个演示将展示 MCP 服务器的主要功能")
    print("="*60)

    # 1. 列出工具
    await demo_list_tools()

    # 2. 列出搜索引擎
    await demo_list_engines()

    # 3. 搜索演示（可选，因为需要实际网络请求）
    print("\n" + "="*60)
    print("是否运行搜索演示？(需要网络连接)")
    print("="*60)

    try:
        choice = input("输入 'y' 运行搜索演示，其他键跳过: ").strip().lower()
        if choice == 'y':
            await demo_search()
        else:
            print("\n⏭️  跳过搜索演示")
    except (EOFError, KeyboardInterrupt):
        print("\n⏭️  跳过搜索演示")

    print("\n" + "="*60)
    print("✅ 演示完成！")
    print("="*60)
    print("\n提示：")
    print("  - 运行 'python test_search.py' 进行完整测试")
    print("  - 查看 README.md 了解更多用法")
    print("  - 查看 guide.md 了解 Craft Agent 集成")


if __name__ == "__main__":
    asyncio.run(main())
