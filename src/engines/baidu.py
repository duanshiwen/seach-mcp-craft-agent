"""百度搜索引擎实现 - 浏览器模式 + HTTP fallback。

优先使用可见浏览器窗口搜索，失败时回退到 HTTP 模式（移动端入口）。
"""

import json
import logging
import re
from html import unescape
from urllib.parse import quote_plus, unquote

from selectolax.parser import HTMLParser

from src.types import SearchEngine, SearchResult

from .browser_base import BrowserSearchEngine

logger = logging.getLogger(__name__)

# 百度搜索结果提取 JavaScript
# 基于 .c-result / .result / .c-container 容器
BAIDU_EXTRACT_RESULTS_JS = """
() => {
    const results = [];
    const seen = new Set();
    
    // 百度搜索结果容器
    const resultElements = document.querySelectorAll('.c-result.result, #content_left .result, #content_left .c-container');
    
    for (const el of resultElements) {
        try {
            // 提取标题
            let title = '';
            const titleSelectors = ['h3 a', 'h3', '.c-title', '[class*="title"] a', '[class*="title"]', 'a'];
            for (const sel of titleSelectors) {
                const titleEl = el.querySelector(sel);
                if (titleEl) {
                    title = titleEl.innerText?.trim().replace(/\\s+/g, ' ');
                    if (title && title.length > 3 && !['综合', '视频', '图片', '资讯', '问答'].includes(title)) {
                        break;
                    }
                    title = '';
                }
            }
            if (!title) continue;
            
            // 跳过推荐/导航类卡片
            if (title.includes('大家还在搜') || title.includes('相关搜索') || title.includes('点击即刻体验AI搜索')) {
                continue;
            }
            
            // 提取 URL - 优先从 data-log.mu 获取
            let href = '';
            const dataLog = el.getAttribute('data-log');
            if (dataLog) {
                try {
                    const data = JSON.parse(dataLog);
                    if (data.mu && data.mu.startsWith('http')) {
                        href = data.mu;
                    }
                } catch(e) {}
            }
            
            // 备用：从 rl-link-href 获取
            if (!href) {
                href = el.getAttribute('rl-link-href') || '';
            }
            
            // 备用：从链接获取
            if (!href) {
                const linkEl = el.querySelector('h3 a') || el.querySelector('a[href]');
                if (linkEl) {
                    href = linkEl.href || '';
                }
            }
            
            // 规范化 URL
            if (href.startsWith('//')) {
                href = 'https:' + href;
            } else if (href.startsWith('/')) {
                href = 'https://m.baidu.com' + href;
            }
            
            if (!href || href.startsWith('javascript:')) continue;
            if (!href.startsWith('http')) continue;
            
            // 去重
            if (seen.has(href)) continue;
            seen.add(href);
            
            // 提取摘要
            let abstract = '';
            const abstractSelectors = ['.c-abstract', '[class*="abstract"]', '[class*="summary"]', '[class*="desc"]', 'p'];
            for (const sel of abstractSelectors) {
                const nodes = el.querySelectorAll(sel);
                for (const node of nodes) {
                    const text = node.innerText?.trim().replace(/\\s+/g, ' ');
                    if (text && text !== title && text.length > 20) {
                        abstract = text.substring(0, 200);
                        break;
                    }
                }
                if (abstract) break;
            }
            
            results.push({ title, href, abstract });
        } catch (e) {
            continue;
        }
    }
    
    return results;
}
"""


class BaiduSearchEngine(BrowserSearchEngine):
    """百度搜索引擎实现。

    特点：
    - 优先使用可见浏览器窗口搜索
    - 浏览器模式失败时回退到 HTTP 模式（移动端入口）
    - 支持 CAPTCHA 检测与用户手动验证
    - HTTP 模式使用移动端 UA，通常更不容易触发安全验证
    """

    # 浏览器模式使用桌面端
    BASE_URL = "https://www.baidu.com/s"
    # HTTP fallback 使用移动端
    MOBILE_URL = "https://m.baidu.com/s"
    ENGINE_NAME = "百度"
    PROFILE_DIR_NAME = "baidu"

    def __init__(self, **kwargs):
        """初始化百度搜索引擎。"""
        super().__init__(engine_type=SearchEngine.BAIDU, **kwargs)
        # HTTP fallback 用的客户端
        self._http_client = None

    def _get_search_url(self, query: str) -> str:
        """构造百度搜索 URL（桌面端）。

        Args:
            query: 搜索查询词

        Returns:
            完整的百度搜索 URL
        """
        encoded_query = quote_plus(query)
        return f"{self.BASE_URL}?wd={encoded_query}"

    def _is_blocked(self, html: str, url: str = "") -> bool:
        """检测页面是否被百度拦截（CAPTCHA/安全验证）。

        Args:
            html: 页面 HTML 内容
            url: 当前页面 URL

        Returns:
            是否被拦截
        """
        return "百度安全验证" in html or "wappass.baidu.com/static/captcha" in html

    @property
    def _extract_results_js(self) -> str:
        """返回百度结果提取 JavaScript 代码。"""
        return BAIDU_EXTRACT_RESULTS_JS

    async def search(self, query: str) -> list[SearchResult]:
        """执行百度搜索。

        优先使用浏览器模式，失败时回退到 HTTP 模式（移动端）。

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
            logger.warning("百度浏览器模式未获取到结果，尝试 HTTP fallback")
        except Exception as e:
            logger.warning(f"百度浏览器模式失败: {e}，尝试 HTTP fallback")

        # HTTP fallback（移动端）
        return await self._search_http(query)

    async def _search_http(self, query: str) -> list[SearchResult]:
        """使用 HTTP 模式搜索（移动端 fallback）。

        Args:
            query: 搜索查询词

        Returns:
            搜索结果列表
        """
        try:
            encoded_query = quote_plus(query)
            url = f"{self.MOBILE_URL}?word={encoded_query}"

            logger.info(f"正在搜索百度 (HTTP fallback): {query}")
            html = await self._fetch_page_http(url)

            if self._is_captcha_page_http(html):
                logger.warning("百度 HTTP 模式返回了安全验证页面")
                return []

            results = self._parse_results_http(html)
            logger.info(f"百度 HTTP 搜索完成，找到 {len(results)} 个结果")
            return results

        except Exception as e:
            logger.error(f"百度 HTTP 搜索失败: {e}")
            raise
        finally:
            await self._close_http_client()

    def _is_captcha_page_http(self, html: str) -> bool:
        """检测 HTTP 模式页面是否为百度安全验证页面。"""
        return "百度安全验证" in html or "wappass.baidu.com/static/captcha" in html

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
        """获取 HTTP 请求头（移动端 UA）。"""
        return {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 "
                "Mobile/15E148 Safari/604.1"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://m.baidu.com/",
        }

    async def _close_http_client(self) -> None:
        """关闭 HTTP 客户端。"""
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    def _parse_results_http(self, html: str) -> list[SearchResult]:
        """解析百度 HTTP 模式搜索结果页面。"""
        results = []
        tree = HTMLParser(html)

        result_elements = tree.css(".c-result.result, #content_left .result, #content_left .c-container")

        for element in result_elements:
            if len(results) >= self.max_results:
                break

            try:
                title = self._extract_title_http(element)
                if not title:
                    continue

                # 跳过推荐/导航类卡片
                if any(skip in title for skip in ["大家还在搜", "相关搜索", "点击即刻体验AI搜索"]):
                    continue

                href = self._extract_url_http(element)
                if not href:
                    link_el = element.css_first("h3 a") or element.css_first("a[href]")
                    if link_el:
                        href = link_el.attributes.get("href", "")
                href = self._normalize_href_http(href)

                if not href or href.startswith("javascript:"):
                    continue

                abstract = self._extract_abstract_http(element, title)

                results.append(
                    SearchResult(
                        title=title,
                        href=href,
                        abstract=abstract,
                        source=SearchEngine.BAIDU,
                    )
                )

            except Exception as e:
                logger.warning(f"解析结果时出错: {e}")
                continue

        return results

    def _extract_url_http(self, element) -> str:
        """从百度结果节点属性中提取目标 URL。"""
        # 1. 移动端结果常在 data-log JSON 里提供 mu 字段
        data_log = element.attributes.get("data-log", "")
        if data_log:
            try:
                data = json.loads(unescape(data_log))
                mu = data.get("mu")
                if mu and mu.startswith("http"):
                    return mu
            except Exception:
                pass

        # 2. 部分节点使用 rl-link-href 提供跳转链接
        rl_href = element.attributes.get("rl-link-href", "")
        if rl_href:
            return rl_href

        # 3. 部分节点把真实 URL 双重编码放在 rl-link-data-click.extra.url
        rl_data_click = element.attributes.get("rl-link-data-click", "")
        if rl_data_click:
            try:
                data = json.loads(unescape(rl_data_click))
                extra = data.get("extra")
                if extra:
                    extra_data = json.loads(extra)
                    raw_url = extra_data.get("url")
                    if raw_url:
                        return unquote(unquote(raw_url))
            except Exception:
                pass

        return ""

    def _normalize_href_http(self, href: str) -> str:
        """规范化百度链接。"""
        if not href:
            return ""
        if href.startswith("//"):
            return "https:" + href
        if href.startswith("/"):
            return "https://m.baidu.com" + href
        return href

    def _extract_title_http(self, element) -> str:
        """从结果节点中提取标题。"""
        for selector in [
            "h3 a",
            "h3",
            ".c-title",
            "[class*=title] a",
            "[class*=title]",
            "a",
        ]:
            title_el = element.css_first(selector)
            if title_el:
                title = title_el.text(strip=True)
                title = re.sub(r"\s+", " ", title).strip()
                if title and len(title) > 3 and title not in {"综合", "视频", "图片", "资讯", "问答"}:
                    return title
        return ""

    def _extract_abstract_http(self, element, title: str) -> str:
        """从结果节点中提取摘要。"""
        for selector in [
            ".c-abstract",
            "[class*=abstract]",
            "[class*=summary]",
            "[class*=desc]",
            "p",
        ]:
            nodes = element.css(selector)
            for node in nodes:
                text = node.text(strip=True)
                text = re.sub(r"\s+", " ", text).strip()
                if text and text != title and len(text) > 20:
                    return text[:200]
        return ""
