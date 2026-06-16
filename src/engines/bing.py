"""Bing 搜索引擎实现 - 浏览器模式 + HTTP fallback。

优先使用可见浏览器窗口搜索，失败时回退到 HTTP 模式。
"""

import logging
from urllib.parse import quote_plus

from selectolax.parser import HTMLParser

from src.types import SearchEngine, SearchResult

from .browser_base import BrowserSearchEngine

logger = logging.getLogger(__name__)

# Bing 搜索结果提取 JavaScript
# 基于 #b_results 容器下的 .b_algo 元素
BING_EXTRACT_RESULTS_JS = """
() => {
    const results = [];
    const seen = new Set();
    
    // Bing 搜索结果在 #b_results 下的 .b_algo 中
    const resultElements = document.querySelectorAll('#b_results .b_algo');
    
    for (const el of resultElements) {
        try {
            // 提取标题和链接
            const linkEl = el.querySelector('h2 a');
            if (!linkEl) continue;
            
            const title = linkEl.innerText?.trim();
            const href = linkEl.href;
            
            if (!title || !href) continue;
            
            // 过滤非 http 链接
            if (!href.startsWith('http')) continue;
            
            // 去重
            if (seen.has(href)) continue;
            seen.add(href);
            
            // 提取摘要
            let abstract = '';
            const captionEl = el.querySelector('.b_caption p') || el.querySelector('.b_algoSlug');
            if (captionEl) {
                abstract = captionEl.innerText?.trim() || '';
            }
            
            results.push({ title, href, abstract });
        } catch (e) {
            continue;
        }
    }
    
    return results;
}
"""


class BingSearchEngine(BrowserSearchEngine):
    """Bing 搜索引擎实现。

    特点：
    - 优先使用可见浏览器窗口搜索
    - 浏览器模式失败时回退到 HTTP 模式
    - 支持 CAPTCHA 检测与用户手动验证
    """

    BASE_URL = "https://www.bing.com/search"
    ENGINE_NAME = "Bing"
    PROFILE_DIR_NAME = "bing"

    def __init__(self, **kwargs):
        """初始化 Bing 搜索引擎。"""
        super().__init__(engine_type=SearchEngine.BING, **kwargs)
        # HTTP fallback 用的客户端
        self._http_client = None

    def _get_search_url(self, query: str) -> str:
        """构造 Bing 搜索 URL。

        Args:
            query: 搜索查询词

        Returns:
            完整的 Bing 搜索 URL
        """
        encoded_query = quote_plus(query)
        return f"{self.BASE_URL}?q={encoded_query}&cc=cn&setlang=zh-Hans"

    def _is_blocked(self, html: str, url: str = "") -> bool:
        """检测页面是否被 Bing 拦截（CAPTCHA）。

        Args:
            html: 页面 HTML 内容
            url: 当前页面 URL

        Returns:
            是否被拦截
        """
        lower = html.lower()
        indicators = ["captcha", "verify you are human", "challenge", "turnstile"]
        # 只有在没有搜索结果容器时才认为是 CAPTCHA
        return any(ind in lower for ind in indicators) and "#b_results" not in lower

    @property
    def _extract_results_js(self) -> str:
        """返回 Bing 结果提取 JavaScript 代码。"""
        return BING_EXTRACT_RESULTS_JS

    async def search(self, query: str) -> list[SearchResult]:
        """执行 Bing 搜索。

        优先使用浏览器模式，失败时回退到 HTTP 模式。

        Args:
            query: 搜索查询词

        Returns:
            搜索结果列表
        """
        # 尝试浏览器模式
        try:
            results = await super().search(query)
            if results:
                return results
            logger.warning("Bing 浏览器模式未获取到结果，尝试 HTTP fallback")
        except Exception as e:
            logger.warning(f"Bing 浏览器模式失败: {e}，尝试 HTTP fallback")

        # HTTP fallback
        return await self._search_http(query)

    async def _search_http(self, query: str) -> list[SearchResult]:
        """使用 HTTP 模式搜索（fallback）。

        Args:
            query: 搜索查询词

        Returns:
            搜索结果列表
        """
        try:
            encoded_query = quote_plus(query)
            url = f"{self.BASE_URL}?q={encoded_query}&cc=cn&setlang=zh-Hans"

            logger.info(f"正在搜索 Bing (HTTP fallback): {query}")
            html = await self._fetch_page_http(url)

            # 检查是否被 CAPTCHA 拦截
            if self._is_captcha_page_http(html):
                logger.warning("Bing HTTP 模式返回了 CAPTCHA 页面")
                return []

            results = self._parse_results_http(html)
            logger.info(f"Bing HTTP 搜索完成，找到 {len(results)} 个结果")
            return results

        except Exception as e:
            logger.error(f"Bing HTTP 搜索失败: {e}")
            raise
        finally:
            await self._close_http_client()

    def _is_captcha_page_http(self, html: str) -> bool:
        """检测 HTTP 模式页面是否为 CAPTCHA 验证页面。"""
        lower = html.lower()
        indicators = ["captcha", "verify you are human", "challenge", "turnstile"]
        return any(ind in lower for ind in indicators) and "#b_results" not in lower

    async def _fetch_page_http(self, url: str) -> str:
        """使用 HTTP 获取页面。"""
        import httpx

        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                headers=self._get_headers_http(),
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
            )
        response = await self._http_client.get(url)
        response.raise_for_status()
        return response.text

    def _get_headers_http(self) -> dict[str, str]:
        """获取 HTTP 请求头。"""
        import random as _random
        user_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        ]
        return {
            "User-Agent": _random.choice(user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    async def _close_http_client(self) -> None:
        """关闭 HTTP 客户端。"""
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    def _parse_results_http(self, html: str) -> list[SearchResult]:
        """解析 Bing HTTP 模式搜索结果页面。"""
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

            except Exception as e:
                logger.warning(f"解析结果时出错: {e}")
                continue

        return results
