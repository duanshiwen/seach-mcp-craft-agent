"""MCP 服务器主入口 - 实现搜索引擎 MCP 服务。"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
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
from src.fetcher import (
    _fetch_apple_doc_json,
    _render_apple_doc_markdown,
    fetch_url,
)
from src.types import SearchEngine, SearchResult
from src.utils import (
    format_results_for_display,
    get_engine_display_name,
    setup_logging,
    validate_query,
)

logger = logging.getLogger(__name__)
SOURCE_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DEBUG_LOG = SOURCE_ROOT / "mcp_runtime_debug.log"
GOOGLE_LAST_CAPTCHA_URL_PATH = SOURCE_ROOT / "google_last_captcha_url.txt"
GOOGLE_CAPTCHA_DEBUG_LOG_PATH = SOURCE_ROOT / "google_captcha_debug.log"


def _runtime_debug(message: str) -> None:
    """Write source-local runtime diagnostics without touching MCP stdout."""
    try:
        ts = datetime.now().isoformat(timespec="seconds")
        with RUNTIME_DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")
    except Exception:
        pass

# 创建 MCP 服务器实例
server = Server("search-engine-mcp")


# 定义工具列表
TOOLS = [
    Tool(
        name="search",
        description=(
            "通过指定搜索引擎查询信息，返回结构化的搜索结果。支持 Google、Bing、DuckDuckGo、Yahoo、百度五个搜索引擎。\n"
            "- DuckDuckGo（默认）：稳定可靠，轻量 HTTP，速度快\n"
            "- Bing：中文搜索效果好，轻量 HTTP\n"
            "- Google：结果最全，Playwright JS 渲染，较慢（3-5秒）\n"
            "- 百度：国内内容搜索，轻量 HTTP\n"
            "- Yahoo：综合搜索，轻量 HTTP\n"
            "适合获取实时信息，如天气、新闻、最新资讯、技术文档等。"
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
                    "description": "搜索引擎选择。duckduckgo（默认，稳定快速）、bing（中文优化）、google（结果最全，JS渲染较慢）、baidu（国内内容）、yahoo（综合搜索）",
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
            "获取指定 URL 的网页正文内容，提取为 AI 友好的 Markdown 格式。\n"
            "特性：自动去除广告/导航栏/页脚等干扰，保留核心正文；支持表格和链接；\n"
            "支持三种渲染模式：auto（自动）、http（轻量快速）、js（Playwright 渲染 SPA 页面）。\n"
            "适用于深入阅读搜索结果、抓取文章全文、提取网页结构化内容。"
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
                    "maximum": 720000,
                    "default": 720000,
                    "description": "请求或 JS 渲染超时时间（毫秒），默认 720000（12分钟）",
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
    _runtime_debug(f"call_tool name={name!r} arguments={arguments!r}")

    if name == "search":
        return await handle_search(arguments or {})
    elif name == "list_engines":
        return await handle_list_engines()
    elif name == "web_fetch":
        args = arguments or {}
        url = str(args.get("url", "")).strip()
        extract_mode = args.get("extract_mode", "markdown")
        timeout_ms = int(args.get("timeout_ms", 720000))
        # Earliest possible fast path for Apple Developer Documentation/HIG.
        # Some stale/cancelled long web_fetch calls can delay normal dispatch;
        # this returns directly after the call_tool log line.
        apple_payload = await _fetch_apple_doc_json(url, timeout_ms) if url else None
        if apple_payload is not None:
            data, json_url = apple_payload
            content = _render_apple_doc_markdown(data, json_url, extract_mode)
            if content:
                _runtime_debug(
                    f"apple dispatch_fast_path url={url!r} json_url={json_url!r} len={len(content)}"
                )
                return [TextContent(type="text", text=content)]
        return await handle_web_fetch(args)
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
    _runtime_debug(
        "handle_search "
        f"query={query!r} engine={engine!r} max_results={max_results!r} "
        f"force_popup={os.getenv('SEARCH_ENGINE_MCP_GOOGLE_FORCE_POPUP')!r} "
        f"captcha_timeout={os.getenv('SEARCH_ENGINE_MCP_CAPTCHA_TIMEOUT')!r}"
    )

    try:
        # 执行搜索
        _runtime_debug(f"before perform_search engine={engine!r}")
        results = await perform_search(query, engine, max_results)
        _runtime_debug(f"after perform_search engine={engine!r} results={len(results) if results is not None else None}")

        # 如果 Google 返回空结果（可能是 CAPTCHA 验证超时或用户取消了验证）
        if not results and engine == "google":
            return [TextContent(
                type="text",
                text=(
                    "Google 搜索未返回结果。\n\n"
                    "如果没有看到 CAPTCHA 弹窗，请查看并手动打开最近一次验证 URL：\n"
                    f"{GOOGLE_LAST_CAPTCHA_URL_PATH}\n\n"
                    "可能原因：\n"
                    "- CAPTCHA 验证超时（已弹出浏览器窗口等待完成验证）\n"
                    "- 搜索频率过高\n"
                    "- IP 被 Google 限制\n"
                    "\n建议：\n"
                    "- 等待几秒后重试 Google 搜索，弹出窗口后完成手动验证\n"
                    "- 或使用其他搜索引擎：`duckduckgo`（推荐）、`bing`\n"
                    f"\n诊断日志：{GOOGLE_CAPTCHA_DEBUG_LOG_PATH}"
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
        _runtime_debug(f"handle_search exception type={type(e).__name__} err={e!r}")
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
            "description": "全球最大的搜索引擎（Playwright JS 渲染，结果最全但较慢）",
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
    timeout_ms = arguments.get("timeout_ms", 720000)

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
    _runtime_debug(
        "handle_web_fetch "
        f"url={url!r} extract_mode={extract_mode!r} render_mode={render_mode!r} "
        f"wait_until={wait_until!r} timeout_ms={timeout_ms!r}"
    )

    try:
        # Fast path for Apple Developer Documentation / HIG. This keeps the MCP
        # tool responsive even when the generic HTTP→trafilatura→JS fallback path
        # or client-side JS rendering is fragile for Apple documentation shells.
        apple_payload = await _fetch_apple_doc_json(url, int(timeout_ms))
        if apple_payload is not None:
            data, json_url = apple_payload
            content = _render_apple_doc_markdown(data, json_url, extract_mode)
            if content:
                _runtime_debug(f"apple fast_path url={url!r} json_url={json_url!r} len={len(content)}")
                return [TextContent(type="text", text=content)]

        _runtime_debug(f"before fetch_url url={url!r}")
        content = await fetch_url(url, extract_mode, render_mode, wait_until, timeout_ms)
        _runtime_debug(f"after fetch_url url={url!r} len={len(content)}")
        logger.info(f"网页内容获取成功，长度: {len(content)} 字符")
        return [TextContent(type="text", text=content)]
    except ValueError as e:
        _runtime_debug(f"handle_web_fetch value_error type={type(e).__name__} err={e!r}")
        raise e
    except Exception as e:
        error_message = f"获取网页内容失败: {str(e)}"
        logger.error(error_message)
        _runtime_debug(f"handle_web_fetch exception type={type(e).__name__} err={e!r}")
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
