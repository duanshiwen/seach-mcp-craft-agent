"""Google 搜索引擎实现 - 使用 Playwright JS 渲染绕过 CAPTCHA。"""

import logging
import random
from urllib.parse import quote_plus

from selectolax.parser import HTMLParser

from src.types import SearchEngine, SearchResult

from .base import BaseSearchEngine

logger = logging.getLogger(__name__)


class GoogleSearchEngine(BaseSearchEngine):
    """Google 搜索引擎实现 - 使用 JS 渲染。

    Google 的反爬虫机制较强，HTTP 请求容易被 CAPTCHA 拦截。
    此实现使用 Playwright 进行真实浏览器渲染，可大幅提高成功率。
    """

    BASE_URL = "https://www.google.com/search"

    def __init__(self, **kwargs):
        """初始化 Google 搜索引擎。"""
        super().__init__(engine_type=SearchEngine.GOOGLE, **kwargs)
        self._playwright = None
        self._browser = None

    async def _init_browser(self):
        """初始化 Playwright 浏览器。"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright 未安装。请运行：\n"
                "pip install playwright && python -m playwright install chromium"
            )

        if self._playwright is None:
            self._playwright = await async_playwright().start()

        if self._browser is None or not self._browser.is_connected():
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                ],
            )

    async def _close_browser(self):
        """关闭 Playwright 浏览器。"""
        try:
            if self._browser and self._browser.is_connected():
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"关闭浏览器时出错: {e}")
        finally:
            self._browser = None
            self._playwright = None

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

            logger.info(f"正在搜索 Google (JS 渲染): {query}")

            # 使用 Playwright 进行 JS 渲染
            html = await self._fetch_page_with_js(url)

            # 检查是否被 CAPTCHA 拦截
            if self._is_blocked(html):
                logger.warning("Google 返回了验证页面 (CAPTCHA)")
                return []

            results = self._parse_results(html)
            logger.info(f"Google 搜索完成，找到 {len(results)} 个结果")
            return results

        except Exception as e:
            logger.error(f"Google 搜索失败: {e}")
            raise
        finally:
            await self._close_browser()

    async def _fetch_page_with_js(self, url: str) -> str:
        """使用 Playwright 获取页面内容。

        Args:
            url: 页面 URL

        Returns:
            渲染后的 HTML 内容
        """
        await self._init_browser()

        # 创建新的浏览器上下文，模拟真实用户
        context = await self._browser.new_context(
            user_agent=random.choice(self.USER_AGENTS if hasattr(self, 'USER_AGENTS') else [
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            ]),
            viewport={"width": 1366, "height": 900},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )

        page = await context.new_page()

        try:
            # 添加反检测脚本
            await page.add_init_script("""
                // 隐藏 webdriver 标志
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                
                // 修改 navigator.plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // 修改 navigator.languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en']
                });
            """)

            # 访问页面
            response = await page.goto(url, wait_until="networkidle", timeout=30000)

            if not response or response.status != 200:
                logger.warning(f"Google 返回状态码: {response.status if response else 'None'}")

            # 等待页面加载完成
            await page.wait_for_timeout(random.randint(1000, 2000))

            # 获取渲染后的 HTML
            html = await page.content()
            return html

        finally:
            await context.close()

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
            "检测到异常流量",
            "unusual traffic from your computer",
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

    def __del__(self):
        """析构函数 - 确保浏览器被关闭。"""
        # Note: cannot await in __del__, but try to cleanup
        pass
