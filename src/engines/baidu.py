"""百度搜索引擎实现 - 使用 HTTP 请求。"""

import json
import logging
import re
from html import unescape
from urllib.parse import quote_plus, unquote, parse_qs, urlparse

from selectolax.parser import HTMLParser

from src.types import SearchEngine, SearchResult

from .base import BaseSearchEngine

logger = logging.getLogger(__name__)


class BaiduSearchEngine(BaseSearchEngine):
    """百度搜索引擎实现。

    使用百度移动端搜索入口，通常比桌面端更不容易触发安全验证，
    且 HTML 中包含可解析的 `data-log.mu` 原始目标 URL。
    """

    BASE_URL = "https://m.baidu.com/s"

    def __init__(self, **kwargs):
        """初始化百度搜索引擎。"""
        super().__init__(engine_type=SearchEngine.BAIDU, **kwargs)

    def _get_headers(self) -> dict[str, str]:
        """获取 HTTP 请求头，使用移动端 UA 并禁用 Brotli。

        Returns:
            请求头字典
        """
        headers = super()._get_headers()
        headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 "
                    "Mobile/15E148 Safari/604.1"
                ),
                # 百度部分 Brotli 响应与 brotlicffi/httpx 存在兼容性问题。
                "Accept-Encoding": "gzip, deflate",
                "Referer": "https://m.baidu.com/",
            }
        )
        return headers

    async def search(self, query: str) -> list[SearchResult]:
        """执行百度搜索。"""
        try:
            encoded_query = quote_plus(query)
            url = f"{self.BASE_URL}?word={encoded_query}"

            logger.info(f"正在搜索百度: {query}")
            html = await self._fetch_page(url)

            if self._is_captcha_page(html):
                logger.warning("百度返回了安全验证页面")
                return []

            results = self._parse_results(html)
            logger.info(f"百度搜索完成，找到 {len(results)} 个结果")
            return results

        except Exception as e:
            logger.error(f"百度搜索失败: {e}")
            raise
        finally:
            await self._close_client()

    def _is_captcha_page(self, html: str) -> bool:
        """检测是否为百度安全验证页面。"""
        return "百度安全验证" in html or "wappass.baidu.com/static/captcha" in html

    def _extract_url_from_attrs(self, element) -> str:
        """从百度结果节点属性中提取目标 URL。"""
        # 1. 移动端结果常在 data-log JSON 里提供 mu 字段。
        data_log = element.attributes.get("data-log", "")
        if data_log:
            try:
                data = json.loads(unescape(data_log))
                mu = data.get("mu")
                if mu and mu.startswith("http"):
                    return mu
            except Exception:
                pass

        # 2. 部分节点使用 rl-link-href 提供跳转链接。
        rl_href = element.attributes.get("rl-link-href", "")
        if rl_href:
            return rl_href

        # 3. 部分节点把真实 URL 双重编码放在 rl-link-data-click.extra.url。
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

    def _normalize_href(self, href: str) -> str:
        """规范化百度链接。"""
        if not href:
            return ""
        if href.startswith("//"):
            return "https:" + href
        if href.startswith("/"):
            return "https://m.baidu.com" + href
        return href

    def _extract_title(self, element) -> str:
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

    def _extract_abstract(self, element, title: str) -> str:
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

    def _parse_results(self, html: str) -> list[SearchResult]:
        """解析百度搜索结果页面。"""
        results = []
        tree = HTMLParser(html)

        result_elements = tree.css(".c-result.result, #content_left .result, #content_left .c-container")

        for element in result_elements:
            if len(results) >= self.max_results:
                break

            try:
                title = self._extract_title(element)
                if not title:
                    continue

                # 跳过推荐/导航类卡片。
                if any(skip in title for skip in ["大家还在搜", "相关搜索", "点击即刻体验AI搜索"]):
                    continue

                href = self._extract_url_from_attrs(element)
                if not href:
                    link_el = element.css_first("h3 a") or element.css_first("a[href]")
                    if link_el:
                        href = link_el.attributes.get("href", "")
                href = self._normalize_href(href)

                if not href or href.startswith("javascript:"):
                    continue

                abstract = self._extract_abstract(element, title)

                results.append(
                    SearchResult(
                        title=title,
                        href=href,
                        abstract=abstract,
                        source=SearchEngine.BAIDU,
                    )
                )
                logger.debug(f"解析结果: {title}")

            except Exception as e:
                logger.warning(f"解析结果时出错: {e}")
                continue

        return results
