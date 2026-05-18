"""Google 搜索引擎实现 - 使用 HTTP 请求。"""

import logging
from urllib.parse import quote_plus

from selectolax.parser import HTMLParser

from src.types import SearchEngine, SearchResult

from .base import BaseSearchEngine

logger = logging.getLogger(__name__)


class GoogleSearchEngine(BaseSearchEngine):
    """Google 搜索引擎实现。"""

    BASE_URL = "https://www.google.com/search"

    def __init__(self, **kwargs):
        """初始化 Google 搜索引擎。"""
        super().__init__(engine_type=SearchEngine.GOOGLE, **kwargs)

    async def search(self, query: str) -> list[SearchResult]:
        """执行 Google 搜索。

        Args:
            query: 搜索查询词

        Returns:
            搜索结果列表

        Raises:
            Exception: 搜索失败时抛出异常
        """
        try:
            encoded_query = quote_plus(query)
            url = f"{self.BASE_URL}?q={encoded_query}&hl=zh-CN&gl=cn"

            logger.info(f"正在搜索 Google: {query}")
            html = await self._fetch_page(url)

            # 检查是否被 CAPTCHA 拦截
            if self._is_blocked(html):
                logger.warning("Google 返回了验证页面")
                return []

            results = self._parse_results(html)
            logger.info(f"Google 搜索完成，找到 {len(results)} 个结果")
            return results

        except Exception as e:
            logger.error(f"Google 搜索失败: {e}")
            raise
        finally:
            await self._close_client()

    def _is_blocked(self, html: str) -> bool:
        """检测页面是否被 Google 拦截。

        Args:
            html: 页面 HTML 内容

        Returns:
            是否被拦截
        """
        lower = html.lower()
        # Google 的 CAPTCHA/拦截页面特征
        block_indicators = [
            "sorry/index",
            "captcha",
            "unusual traffic",
            "automated queries",
            "robot",
        ]
        has_block = any(ind in lower for ind in block_indicators)
        # 同时检查是否有正常搜索结果
        has_results = "id=\"search\"" in html or "id=\"rso\"" in html
        return has_block and not has_results

    def _parse_results(self, html: str) -> list[SearchResult]:
        """解析 Google 搜索结果页面。

        Args:
            html: 页面 HTML 内容

        Returns:
            解析后的搜索结果列表
        """
        results = []
        tree = HTMLParser(html)

        # Google 搜索结果在 #search 下的 .g 或 #rso 下的 div
        result_elements = tree.css("#search .g")

        if not result_elements:
            result_elements = tree.css("#rso .g")

        if not result_elements:
            # 更宽泛的选择器
            result_elements = tree.css("div.g")

        for element in result_elements[: self.max_results]:
            try:
                # 提取标题
                title_el = element.css_first("h3")
                if not title_el:
                    continue
                title = title_el.text(strip=True)

                # 提取链接
                link_el = element.css_first("a")
                if not link_el:
                    continue
                href = link_el.attributes.get("href", "")

                # 过滤掉非 http 链接（如 Google 内部链接）
                if not href.startswith("http"):
                    continue

                # 提取摘要
                abstract = ""
                for selector in [".VwiC3b", ".IsZvec", ".s3v9rd", "span.st"]:
                    abstract_el = element.css_first(selector)
                    if abstract_el:
                        abstract = abstract_el.text(strip=True)
                        break

                if title and href:
                    results.append(
                        SearchResult(
                            title=title,
                            href=href,
                            abstract=abstract,
                            source=SearchEngine.GOOGLE,
                        )
                    )
                    logger.debug(f"解析结果: {title}")

            except Exception as e:
                logger.warning(f"解析结果时出错: {e}")
                continue

        return results
