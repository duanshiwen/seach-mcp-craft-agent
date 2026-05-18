"""Yahoo 搜索引擎实现 - 使用 HTTP 请求。"""

import logging
import re
from urllib.parse import quote_plus, unquote

from selectolax.parser import HTMLParser

from src.types import SearchEngine, SearchResult

from .base import BaseSearchEngine

logger = logging.getLogger(__name__)


class YahooSearchEngine(BaseSearchEngine):
    """Yahoo 搜索引擎实现。"""

    BASE_URL = "https://search.yahoo.com/search"

    def __init__(self, **kwargs):
        """初始化 Yahoo 搜索引擎。"""
        super().__init__(engine_type=SearchEngine.YAHOO, **kwargs)

    async def search(self, query: str) -> list[SearchResult]:
        """执行 Yahoo 搜索。

        Args:
            query: 搜索查询词

        Returns:
            搜索结果列表

        Raises:
            Exception: 搜索失败时抛出异常
        """
        try:
            encoded_query = quote_plus(query)
            url = f"{self.BASE_URL}?p={encoded_query}&ei=UTF-8"

            logger.info(f"正在搜索 Yahoo: {query}")
            html = await self._fetch_page(url)

            results = self._parse_results(html)
            logger.info(f"Yahoo 搜索完成，找到 {len(results)} 个结果")
            return results

        except Exception as e:
            logger.error(f"Yahoo 搜索失败: {e}")
            raise
        finally:
            await self._close_client()

    def _parse_results(self, html: str) -> list[SearchResult]:
        """解析 Yahoo 搜索结果页面。

        Args:
            html: 页面 HTML 内容

        Returns:
            解析后的搜索结果列表
        """
        results = []
        tree = HTMLParser(html)

        # Yahoo 搜索结果在 .searchCenterMiddle 下的 .algo 中
        result_elements = tree.css(".searchCenterMiddle .algo")

        if not result_elements:
            # 备用选择器
            result_elements = tree.css("div.algo")
            if not result_elements:
                result_elements = tree.css("li.algo")

        for element in result_elements[: self.max_results]:
            try:
                # 提取标题和链接
                link_el = element.css_first("h3 a") or element.css_first("a")
                if not link_el:
                    continue

                title = link_el.text(strip=True)
                # Yahoo 有时用 aria-label 作为标题
                if not title:
                    title = link_el.attributes.get("aria-label", "")
                # 清理标题中可能混入的域名信息
                title = re.sub(r'https?://\S+\s*', '', title).strip()

                href = link_el.attributes.get("href", "")
                # 从 Yahoo 重定向 URL 中提取真实链接
                ru_match = re.search(r'/RU=([^/]+)/', href)
                if ru_match:
                    href = unquote(ru_match.group(1))

                # 提取摘要
                abstract = ""
                abstract_el = element.css_first(".compText") or element.css_first(".compText p")
                if abstract_el:
                    abstract = abstract_el.text(strip=True)

                if title and href:
                    results.append(
                        SearchResult(
                            title=title,
                            href=href,
                            abstract=abstract,
                            source=SearchEngine.YAHOO,
                        )
                    )
                    logger.debug(f"解析结果: {title}")

            except Exception as e:
                logger.warning(f"解析结果时出错: {e}")
                continue

        return results
