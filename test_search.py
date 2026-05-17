#!/usr/bin/env python3
"""快速测试搜索引擎功能。"""

import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.engines import (
    BingSearchEngine,
    GoogleSearchEngine,
    YahooSearchEngine,
    DuckDuckGoSearchEngine,
)
from src.types import SearchEngine


async def test_search_engine(engine_name: str, query: str = "Python 教程"):
    """测试指定的搜索引擎。

    Args:
        engine_name: 搜索引擎名称
        query: 搜索查询词
    """
    engine_map = {
        "google": GoogleSearchEngine,
        "bing": BingSearchEngine,
        "yahoo": YahooSearchEngine,
        "duckduckgo": DuckDuckGoSearchEngine,
    }

    engine_class = engine_map.get(engine_name.lower())
    if not engine_class:
        print(f"❌ 不支持的搜索引擎: {engine_name}")
        return

    print(f"\n🔍 正在测试 {engine_name.upper()} 搜索...")
    print(f"   查询词: {query}")
    print("-" * 50)

    try:
        engine = engine_class(max_results=3, headless=True)

        async with engine:
            results = await engine.search(query)

            if results:
                print(f"✅ 找到 {len(results)} 个结果:\n")
                for i, result in enumerate(results, 1):
                    print(f"{i}. {result.title}")
                    print(f"   链接: {result.href}")
                    if result.abstract:
                        print(f"   摘要: {result.abstract[:100]}...")
                    print()
            else:
                print("⚠️  未找到结果")

    except Exception as e:
        print(f"❌ 测试失败: {e}")


async def test_all_engines(query: str = "Python 教程"):
    """测试所有搜索引擎。

    Args:
        query: 搜索查询词
    """
    engines = ["bing", "google", "yahoo", "duckduckgo"]

    print("🚀 开始测试所有搜索引擎")
    print("=" * 60)

    for engine in engines:
        await test_search_engine(engine, query)
        print("=" * 60)


async def main():
    """主函数。"""
    import argparse

    parser = argparse.ArgumentParser(description="测试搜索引擎功能")
    parser.add_argument(
        "-e", "--engine",
        choices=["google", "bing", "yahoo", "duckduckgo", "all"],
        default="bing",
        help="要测试的搜索引擎（默认: bing）"
    )
    parser.add_argument(
        "-q", "--query",
        default="Python 教程",
        help="搜索查询词（默认: Python 教程）"
    )

    args = parser.parse_args()

    if args.engine == "all":
        await test_all_engines(args.query)
    else:
        await test_search_engine(args.engine, args.query)


if __name__ == "__main__":
    asyncio.run(main())
