"""Bing 搜索引擎实现 - 使用 HTTP 请求。"""

import logging
import re
from urllib.parse import quote_plus

from selectolax.parser import HTMLParser

from src.types import SearchEngine, SearchResult

from .base import BaseSearchEngine

logger = logging.getLogger(__name__)


class BingSearchEngine(BaseSearchEngine):
    """Bing 搜索引擎实现。"""

    BASE_URL = "https://www.bing.com/search"

    def __init__(self, **kwargs):
        """初始化 Bing 搜索引擎。"""
        super().__init__(engine_type=SearchEngine.BING, **kwargs)

    async def search(self, query: str) -> list[SearchResult]:
        """执行 Bing 搜索。

        Args:
            query: 搜索查询词

        Returns:
            搜索结果列表

        Raises:
            Exception: 搜索失败时抛出异常
        """
        try:
            encoded_query = quote_plus(query)
            url = f"{self.BASE_URL}?q={encoded_query}&cc=cn&setlang=zh-Hans"

            logger.info(f"正在搜索 Bing: {query}")
            html = await self._fetch_page(url)

            # 检查是否被 CAPTCHA 拦截
            if self._is_captcha_page(html):
                logger.warning("Bing 返回了 CAPTCHA 页面，尝试备用解析...")
                return []

            results = self._parse_results(html)
            logger.info(f"Bing 搜索完成，找到 {len(results)} 个结果")
            return results

        except Exception as e:
            logger.error(f"Bing 搜索失败: {e}")
            raise
        finally:
            await self._close_client()

    def _is_captcha_page(self, html: str) -> bool:
        """检测页面是否为 CAPTCHA 验证页面。

        Args:
            html: 页面 HTML 内容

        Returns:
            是否为 CAPTCHA 页面
        """
        lower = html.lower()
        indicators = ["captcha", "verify you are human", "challenge", "turnstile"]
        return any(ind in lower for ind in indicators) and "#b_results" not in lower

    def _parse_results(self, html: str) -> list[SearchResult]:
        """解析 Bing 搜索结果页面。

        Args:
            html: 页面 HTML 内容

        Returns:
            解析后的搜索结果列表
        """
        results = []
        tree = HTMLParser(html)

        # Bing 搜索结果在 #b_results 下的 .b_algo 中
        result_elements = tree.css("#b_results .b_algo")

        if not result_elements:
            # 备用选择器
            result_elements = tree.css("li.b_algo")

        for element in result_elements[: self.max_results]:
            try:
                # 提取标题和链接
                link_el = element.css_first("h2 a")
                if not link_el:
                    continue

                title = link_el.text(strip=True)
                href = link_el.attributes.get("href", "")

                # 提取摘要
                abstract = ""
                abstract_el = element.css_first(".b_caption p") or element.css_first(".b_algoSlug")
                if abstract_el:
                    abstract = abstract_el.text(strip=True)

                if title and href:
                    results.append(
                        SearchResult(
                            title=title,
                            href=href,
                            abstract=abstract,
                            source=SearchEngine.BING,
                        )
                    )
                    logger.debug(f"解析结果: {title}")

            except Exception as e:
                logger.warning(f"解析结果时出错: {e}")
                continue

        return results
