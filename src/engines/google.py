"""Google 搜索引擎实现 - 使用 Playwright JS 渲染 + 语义结构解析。

解析策略：
- 基于 h3 标题 + a 链接的语义结构提取结果
- 不依赖特定的 CSS 类名（如 div.g, div.tF2Cxc 等）
- 自动处理 Google 重定向 URL
- 通过 Playwright JS 渲染绕过 CAPTCHA
"""

import logging
import random
from urllib.parse import quote_plus, urlparse, parse_qs

from src.types import SearchEngine, SearchResult

from .base import BaseSearchEngine

logger = logging.getLogger(__name__)

# 在页面中执行的 JavaScript 提取逻辑
# 基于语义结构：#main 容器 + h3 标题 + a 链接
# 不依赖特定 CSS 类名（如 div.g, div.tF2Cxc 等）
EXTRACT_RESULTS_JS = """
() => {
    const results = [];
    const seen = new Set();
    
    // 在 #main 容器内查找 h3（Google 搜索结果的稳定容器）
    const mainContainer = document.querySelector('#main');
    if (!mainContainer) return results;
    
    const h3s = mainContainer.querySelectorAll('h3');
    
    for (const h3 of h3s) {
        // 1. 获取标题
        const title = h3.innerText?.trim();
        if (!title || title.length < 3) continue;
        
        // 2. 向上查找包含此 h3 的链接 <a>
        let linkEl = null;
        let current = h3;
        for (let i = 0; i < 6; i++) {
            current = current.parentElement;
            if (!current) break;
            if (current.tagName === 'A') {
                linkEl = current;
                break;
            }
        }
        
        if (!linkEl) continue;
        
        // 3. 获取链接 URL
        let href = linkEl.href;
        if (!href) continue;
        
        // 4. 从 Google 重定向 URL 中提取真实 URL
        if (href.includes('google.com/url')) {
            try {
                const urlObj = new URL(href);
                const realUrl = urlObj.searchParams.get('q');
                if (realUrl) href = realUrl;
            } catch(e) {}
        }
        
        // 5. 过滤非 http 链接和 Google 内部链接
        if (!href.startsWith('http')) continue;
        if (href.includes('google.com/search') || 
            href.includes('accounts.google') ||
            href.includes('google.com/preferences') ||
            href.includes('google.com/maps')) continue;
        
        // 6. 去重
        if (seen.has(href)) continue;
        seen.add(href);
        
        // 7. 获取摘要文本
        let abstract = '';
        const container = linkEl.parentElement || linkEl;
        const candidates = container.querySelectorAll('span, div');
        for (const node of candidates) {
            const text = node.innerText?.trim();
            if (text && 
                text.length > 30 && 
                text !== title && 
                !text.startsWith('http') &&
                !text.includes('›') &&
                !text.includes('...') &&
                text.length < 500) {
                abstract = text.substring(0, 300);
                break;
            }
        }
        
        results.push({ title, href, abstract });
    }
    
    return results;
}
"""


class GoogleSearchEngine(BaseSearchEngine):
    """Google 搜索引擎实现 - 使用 Playwright JS 渲染。

    特点：
    - 使用 Playwright 进行真实浏览器渲染，绕过 CAPTCHA
    - 基于语义结构（h3 + a）解析结果，不依赖特定 CSS 类名
    - 自动处理 Google 重定向 URL
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

            logger.info(f"正在搜索 Google (Playwright): {query}")

            # 使用 Playwright 渲染并提取结果
            raw_results = await self._fetch_and_extract(url)

            # 转换为 SearchResult 对象
            results = []
            for item in raw_results[:self.max_results]:
                results.append(
                    SearchResult(
                        title=item["title"],
                        href=item["href"],
                        abstract=item.get("abstract", ""),
                        source=SearchEngine.GOOGLE,
                    )
                )

            logger.info(f"Google 搜索完成，找到 {len(results)} 个结果")
            return results

        except Exception as e:
            logger.error(f"Google 搜索失败: {e}")
            raise
        finally:
            await self._close_browser()

    async def _fetch_and_extract(self, url: str) -> list[dict]:
        """使用 Playwright 获取页面并提取搜索结果。

        Args:
            url: Google 搜索 URL

        Returns:
            原始结果字典列表
        """
        await self._init_browser()

        # 创建浏览器上下文
        context = await self._browser.new_context(
            user_agent=random.choice(self._get_user_agents()),
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

            # 等待页面加载
            await page.wait_for_timeout(random.randint(1000, 2000))

            # 检查是否被 CAPTCHA 拦截
            html = await page.content()
            if self._is_blocked(html):
                logger.warning("Google 返回了验证页面 (CAPTCHA)")
                return []

            # 使用 JavaScript 提取结果
            results = await page.evaluate(EXTRACT_RESULTS_JS)
            logger.info(f"从页面提取到 {len(results)} 个结果")

            return results

        finally:
            await context.close()

    def _is_blocked(self, html: str) -> bool:
        """检测页面是否被 Google 拦截。

        正常的搜索结果页面会有 #main 容器和 h3 标题。
        CAPTCHA 页面通常没有这些元素，或者包含特定的拦截标识。

        Args:
            html: 页面 HTML 内容

        Returns:
            是否被拦截
        """
        lower = html.lower()
        
        # CAPTCHA/拦截页面的特征
        block_indicators = [
            "sorry/index",
            "captcha",
            "unusual traffic",
            "automated queries",
            "检测到异常流量",
            "unusual traffic from your computer",
        ]
        has_block = any(ind in lower for ind in block_indicators)
        
        # 正常页面的特征：有 #main 容器
        has_main = 'id="main"' in lower
        
        # 如果有拦截特征且没有 #main，说明被拦截
        return has_block and not has_main

    def _get_user_agents(self) -> list[str]:
        """获取 User-Agent 列表。

        Returns:
            User-Agent 字符串列表
        """
        return [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        ]
