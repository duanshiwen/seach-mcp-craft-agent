"""MCP 服务器主入口 - 实现搜索引擎 MCP 服务。"""

import asyncio
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.server.lowlevel.server import NotificationOptions
from mcp.types import (
    TextContent,
    Tool,
)

from src.engines import (
    BaiduSearchEngine,
    BingSearchEngine,
    DuckDuckGoSearchEngine,
    GoogleSearchEngine,
    YahooSearchEngine,
)
from src.fetcher import fetch_url
from src.types import SearchEngine, SearchResult
from src.utils import (
    format_results_for_display,
    get_engine_display_name,
    setup_logging,
    validate_query,
)

logger = logging.getLogger(__name__)

# 创建 MCP 服务器实例
server = Server("search-engine-mcp")


# 定义工具列表
TOOLS = [
    Tool(
        name="search",
        description=(
            "通过指定搜索引擎查询信息，返回结构化的搜索结果。"
            "支持 Bing、DuckDuckGo、Yahoo、百度四个搜索引擎（Google 需要 JS 渲染暂不支持）。"
            "适合获取实时信息，如天气、新闻、最新资讯等。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询关键词",
                    "minLength": 1,
                    "maxLength": 500,
                },
                "engine": {
                    "type": "string",
                    "enum": ["google", "bing", "yahoo", "duckduckgo", "baidu"],
                    "default": "duckduckgo",
                    "description": "搜索引擎选择（默认: duckduckgo）",
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                    "description": "最大返回结果数量（默认: 5）",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="list_engines",
        description="列出所有可用的搜索引擎及其状态",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="web_fetch",
        description=(
            "获取指定 URL 的网页正文内容，提取为 AI 友好的 Markdown 格式。"
            "自动去除广告、导航栏、页脚等干扰内容，保留核心正文。"
            "适用于需要深入阅读搜索结果页面内容的场景。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要获取内容的完整网页 URL",
                    "format": "uri",
                },
                "extract_mode": {
                    "type": "string",
                    "enum": ["markdown", "text"],
                    "default": "markdown",
                    "description": (
                        "输出格式：markdown（默认，保留标题/链接/表格等格式）"
                        "或 text（纯文本，无格式标记）"
                    ),
                },
                "render_mode": {
                    "type": "string",
                    "enum": ["auto", "http", "js"],
                    "default": "auto",
                    "description": (
                        "渲染模式：auto（默认，先 HTTP，必要时自动 JS 渲染）、"
                        "http（强制轻量 HTTP）、js（强制 Playwright/Chromium 渲染）"
                    ),
                },
                "wait_until": {
                    "type": "string",
                    "enum": ["load", "domcontentloaded", "networkidle", "commit"],
                    "default": "networkidle",
                    "description": "JS 渲染时的页面等待策略，默认 networkidle",
                },
                "timeout_ms": {
                    "type": "integer",
                    "minimum": 3000,
                    "maximum": 120000,
                    "default": 30000,
                    "description": "请求或 JS 渲染超时时间（毫秒），默认 30000",
                },
            },
            "required": ["url"],
        },
    ),
]


def get_search_engine(engine_name: str, max_results: int = 5) -> Any:
    """根据引擎名称获取搜索引擎实例。

    Args:
        engine_name: 搜索引擎名称
        max_results: 最大返回结果数量

    Returns:
        搜索引擎实例

    Raises:
        ValueError: 不支持的搜索引擎
    """
    engine_map = {
        "google": GoogleSearchEngine,
        "bing": BingSearchEngine,
        "yahoo": YahooSearchEngine,
        "duckduckgo": DuckDuckGoSearchEngine,
        "baidu": BaiduSearchEngine,
    }

    engine_class = engine_map.get(engine_name.lower())
    if not engine_class:
        raise ValueError(f"不支持的搜索引擎: {engine_name}")

    return engine_class(max_results=max_results)


async def perform_search(
    query: str, engine: str = "duckduckgo", max_results: int = 5
) -> list[SearchResult]:
    """执行搜索操作。

    Args:
        query: 搜索查询词
        engine: 搜索引擎名称
        max_results: 最大返回结果数量

    Returns:
        搜索结果列表

    Raises:
        Exception: 搜索失败时抛出异常
    """
    search_engine = get_search_engine(engine, max_results)

    async with search_engine:
        results = await search_engine.search(query)

    return results


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """处理列出工具请求。

    Returns:
        工具列表
    """
    logger.info("列出可用工具")
    return TOOLS


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict[str, Any] | None
) -> list[TextContent]:
    """处理工具调用请求。

    Args:
        name: 工具名称
        arguments: 工具参数

    Returns:
        工具执行结果

    Raises:
        ValueError: 参数错误或工具不存在
    """
    logger.info(f"调用工具: {name}, 参数: {arguments}")

    if name == "search":
        return await handle_search(arguments or {})
    elif name == "list_engines":
        return await handle_list_engines()
    elif name == "web_fetch":
        return await handle_web_fetch(arguments or {})
    else:
        raise ValueError(f"未知的工具: {name}")


async def handle_search(arguments: dict[str, Any]) -> list[TextContent]:
    """处理搜索请求。

    Args:
        arguments: 搜索参数

    Returns:
        搜索结果

    Raises:
        ValueError: 参数错误
    """
    # 提取参数
    query = arguments.get("query", "").strip()
    engine = arguments.get("engine", "duckduckgo")
    max_results = arguments.get("max_results", 5)

    # 验证查询词
    is_valid, error_msg = validate_query(query)
    if not is_valid:
        raise ValueError(error_msg)

    logger.info(f"执行搜索: query='{query}', engine='{engine}', max_results={max_results}")

    try:
        # 执行搜索
        results = await perform_search(query, engine, max_results)

        # 如果 Google 返回空结果，提供提示
        if not results and engine == "google":
            return [TextContent(
                type="text",
                text=(
                    "Google 搜索需要 JavaScript 渲染，当前不支持。"
                    "请尝试使用其他搜索引擎：\n"
                    "- `duckduckgo`（推荐，稳定可靠）\n"
                    "- `bing`（中文效果好）\n"
                    "- `yahoo`（综合搜索）"
                ),
            )]

        # 格式化结果
        engine_display_name = get_engine_display_name(SearchEngine(engine))
        formatted_output = format_results_for_display(results, engine_display_name)

        logger.info(f"搜索完成，返回 {len(results)} 个结果")

        return [TextContent(type="text", text=formatted_output)]

    except Exception as e:
        error_message = f"搜索失败: {str(e)}"
        logger.error(error_message)
        return [TextContent(type="text", text=error_message)]


async def handle_list_engines() -> list[TextContent]:
    """处理列出搜索引擎请求。

    Returns:
        搜索引擎列表
    """
    engines_info = [
        {
            "name": "google",
            "display_name": "Google",
            "description": "全球最大的搜索引擎（需要 JS 渲染，暂不支持）",
        },
        {
            "name": "bing",
            "display_name": "Bing",
            "description": "微软搜索引擎，中文搜索效果较好",
        },
        {
            "name": "yahoo",
            "display_name": "Yahoo",
            "description": "雅虎搜索引擎",
        },
        {
            "name": "duckduckgo",
            "display_name": "DuckDuckGo",
            "description": "注重隐私的搜索引擎",
        },
        {
            "name": "baidu",
            "display_name": "百度",
            "description": "中文搜索引擎，适合中文内容搜索",
        },
    ]

    output_lines = ["**可用的搜索引擎：**\n"]

    for engine in engines_info:
        output_lines.append(f"- **{engine['display_name']}** (`{engine['name']}`)")
        output_lines.append(f"  {engine['description']}")
        output_lines.append("")

    output_lines.append("\n使用 `search` 工具时，通过 `engine` 参数指定搜索引擎。")

    return [TextContent(type="text", text="\n".join(output_lines))]


async def handle_web_fetch(arguments: dict[str, Any]) -> list[TextContent]:
    """处理网页内容获取请求。

    Args:
        arguments: 工具参数

    Returns:
        提取的网页内容
    """
    url = arguments.get("url", "").strip()
    extract_mode = arguments.get("extract_mode", "markdown")
    render_mode = arguments.get("render_mode", "auto")
    wait_until = arguments.get("wait_until", "networkidle")
    timeout_ms = arguments.get("timeout_ms", 30000)

    if not url:
        raise ValueError("URL 参数不能为空")

    if extract_mode not in ("markdown", "text"):
        raise ValueError(f"不支持的提取模式: {extract_mode}，可选: markdown, text")

    if render_mode not in ("auto", "http", "js"):
        raise ValueError(f"不支持的渲染模式: {render_mode}，可选: auto, http, js")

    if wait_until not in ("load", "domcontentloaded", "networkidle", "commit"):
        raise ValueError(
            f"不支持的等待策略: {wait_until}，可选: load, domcontentloaded, networkidle, commit"
        )

    logger.info(
        f"获取网页内容: url='{url}', mode='{extract_mode}', "
        f"render='{render_mode}', wait_until='{wait_until}', timeout_ms={timeout_ms}"
    )

    try:
        content = await fetch_url(url, extract_mode, render_mode, wait_until, timeout_ms)
        logger.info(f"网页内容获取成功，长度: {len(content)} 字符")
        return [TextContent(type="text", text=content)]
    except ValueError as e:
        raise e
    except Exception as e:
        error_message = f"获取网页内容失败: {str(e)}"
        logger.error(error_message)
        return [TextContent(type="text", text=error_message)]


async def run_server() -> None:
    """运行 MCP 服务器。"""
    logger.info("启动 Search Engine MCP 服务器...")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="search-engine-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities=None,
                ),
            ),
        )


def main() -> None:
    """主入口函数。"""
    setup_logging(level="DEBUG")

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("服务器已停止")
    except Exception as e:
        import traceback
        logger.error(f"服务器启动失败: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
