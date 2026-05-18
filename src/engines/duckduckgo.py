"""DuckDuckGo 搜索引擎实现 - 使用 HTML 端点。"""

import logging
from urllib.parse import quote_plus

from selectolax.parser import HTMLParser

from src.types import SearchEngine, SearchResult

from .base import BaseSearchEngine

logger = logging.getLogger(__name__)


class DuckDuckGoSearchEngine(BaseSearchEngine):
    """DuckDuckGo 搜索引擎实现。

    使用 DuckDuckGo 的 HTML-only 端点 (https://html.duckduckgo.com/html/)，
    该端点返回纯 HTML 结果，无需 JavaScript 渲染，适合自动化抓取。
    """

    BASE_URL = "https://html.duckduckgo.com/html/"

    def __init__(self, **kwargs):
        """初始化 DuckDuckGo 搜索引擎。"""
        super().__init__(engine_type=SearchEngine.DUCKDUCKGO, **kwargs)

    async def search(self, query: str) -> list[SearchResult]:
        """执行 DuckDuckGo 搜索。

        Args:
            query: 搜索查询词

        Returns:
            搜索结果列表

        Raises:
            Exception: 搜索失败时抛出异常
        """
        try:
            encoded_query = quote_plus(query)
            url = f"{self.BASE_URL}?q={encoded_query}"

            logger.info(f"正在搜索 DuckDuckGo: {query}")
            html = await self._fetch_page(url)

            results = self._parse_results(html)
            logger.info(f"DuckDuckGo 搜索完成，找到 {len(results)} 个结果")
            return results

        except Exception as e:
            logger.error(f"DuckDuckGo 搜索失败: {e}")
            raise
        finally:
            await self._close_client()

    def _parse_results(self, html: str) -> list[SearchResult]:
        """解析 DuckDuckGo HTML 搜索结果。

        Args:
            html: 页面 HTML 内容

        Returns:
            解析后的搜索结果列表
        """
        results = []
        tree = HTMLParser(html)

        # DuckDuckGo HTML 端点使用 .result 类
        result_elements = tree.css(".result")

        for element in result_elements[: self.max_results]:
            try:
                # 提取标题和链接
                link_el = element.css_first(".result__a")
                if not link_el:
                    # 备用选择器
                    link_el = element.css_first("a.result__url")
                    if not link_el:
                        link_el = element.css_first("a")

                if not link_el:
                    continue

                title = link_el.text(strip=True)

                # DuckDuckGo HTML 版本的链接可能在 data-u 属性中
                href = link_el.attributes.get("href", "")

                # 有时链接是重定向格式，提取真实 URL
                if "uddg=" in href:
                    from urllib.parse import parse_qs, urlparse
                    parsed = urlparse(href)
                    qs = parse_qs(parsed.query)
                    if "uddg" in qs:
                        href = qs["uddg"][0]

                # 提取摘要
                abstract = ""
                snippet_el = element.css_first(".result__snippet")
                if not snippet_el:
                    snippet_el = element.css_first(".result__body")
                if snippet_el:
                    abstract = snippet_el.text(strip=True)

                if title and href:
                    results.append(
                        SearchResult(
                            title=title,
                            href=href,
                            abstract=abstract,
                            source=SearchEngine.DUCKDUCKGO,
                        )
                    )
                    logger.debug(f"解析结果: {title}")

            except Exception as e:
                logger.warning(f"解析结果时出错: {e}")
                continue

        return results
