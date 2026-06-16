"""工具函数模块 - 提供通用的辅助功能。"""

import logging
import sys
from typing import Optional

from src.types import SearchEngine


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """配置日志系统。

    Args:
        level: 日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        log_file: 日志文件路径（可选）
    """
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_level = getattr(logging, level.upper(), logging.INFO)

    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 清除现有的处理器
    root_logger.handlers.clear()

    # 添加控制台处理器
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console_handler)

    # 添加文件处理器（如果指定）
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(log_format))
        root_logger.addHandler(file_handler)

    # 设置第三方库的日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("hpack").setLevel(logging.WARNING)


def get_engine_display_name(engine: SearchEngine) -> str:
    """获取搜索引擎的显示名称。

    Args:
        engine: 搜索引擎类型

    Returns:
        搜索引擎的显示名称
    """
    display_names = {
        SearchEngine.GOOGLE: "Google",
        SearchEngine.BING: "Bing",
        SearchEngine.YAHOO: "Yahoo",
        SearchEngine.DUCKDUCKGO: "DuckDuckGo",
        SearchEngine.BAIDU: "百度",
    }
    return display_names.get(engine, engine.value)


def validate_query(query: str) -> tuple[bool, Optional[str]]:
    """验证搜索查询词。

    Args:
        query: 搜索查询词

    Returns:
        (是否有效, 错误信息) 元组
    """
    if not query or not query.strip():
        return False, "搜索查询词不能为空"

    if len(query.strip()) > 500:
        return False, "搜索查询词过长（最多 500 个字符）"

    return True, None


def format_results_for_display(results: list, engine_name: str) -> str:
    """格式化搜索结果用于显示。

    Args:
        results: 搜索结果列表
        engine_name: 搜索引擎名称

    Returns:
        格式化后的字符串
    """
    if not results:
        return f"未找到 {engine_name} 搜索结果"

    output_lines = [f"**{engine_name} 搜索结果：**\n"]

    for i, result in enumerate(results, 1):
        output_lines.append(f"{i}. **{result.title}**")
        output_lines.append(f"   链接: {result.href}")
        if result.abstract:
            output_lines.append(f"   摘要: {result.abstract}")
        output_lines.append("")

    return "\n".join(output_lines)
