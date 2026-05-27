"""Google 搜索引擎实现 - 继承 BrowserSearchEngine。

使用 Playwright 可见浏览器窗口搜索，支持 CAPTCHA 自动检测与用户手动验证。
"""

import logging
from urllib.parse import quote_plus

from src.types import SearchEngine

from .browser_base import BrowserSearchEngine

logger = logging.getLogger(__name__)

# 在页面中执行的 JavaScript 提取逻辑
# 基于语义结构：#main 容器 + h3 标题 + a 链接
# 不依赖特定 CSS 类名（如 div.g, div.tF2Cxc 等）
GOOGLE_EXTRACT_RESULTS_JS = """
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


class GoogleSearchEngine(BrowserSearchEngine):
    """Google 搜索引擎实现 - 使用 Playwright 可见浏览器窗口。

    特点：
    - 使用可见浏览器窗口，绕过 CAPTCHA
    - 基于语义结构（h3 + a）解析结果，不依赖特定 CSS 类名
    - 自动处理 Google 重定向 URL
    - CAPTCHA 时弹出窗口等待用户手动验证
    """

    BASE_URL = "https://www.google.com/search"
    ENGINE_NAME = "Google"
    PROFILE_DIR_NAME = "google"

    def __init__(self, **kwargs):
        """初始化 Google 搜索引擎。"""
        super().__init__(engine_type=SearchEngine.GOOGLE, **kwargs)

    def _get_search_url(self, query: str) -> str:
        """构造 Google 搜索 URL。

        Args:
            query: 搜索查询词

        Returns:
            完整的 Google 搜索 URL
        """
        encoded_query = quote_plus(query)
        return f"{self.BASE_URL}?q={encoded_query}&hl=zh-CN&gl=cn"

    def _is_blocked(self, html: str, url: str = "") -> bool:
        """检测页面是否被 Google 拦截（CAPTCHA）。

        Args:
            html: 页面 HTML 内容
            url: 当前页面 URL

        Returns:
            是否被拦截
        """
        lower = html.lower()
        url_lower = (url or "").lower()

        # URL 特征检测
        url_indicators = [
            "/sorry/",
            "sorry/index",
            "continue=",
        ]
        if "google." in url_lower and any(ind in url_lower for ind in url_indicators):
            return True

        # 页面内容特征检测
        block_indicators = [
            "sorry/index",
            "google.com/sorry",
            "recaptcha",
            "g-recaptcha",
            "captcha",
            "unusual traffic",
            "automated queries",
            "our systems have detected unusual traffic",
            "to continue, please type the characters",
            "about this page",
            "detected unusual traffic from your computer network",
            "检测到异常流量",
            "请输入下图中的字符",
            "请进行人机身份验证",
        ]
        return any(ind in lower for ind in block_indicators)

    @property
    def _extract_results_js(self) -> str:
        """返回 Google 结果提取 JavaScript 代码。"""
        return GOOGLE_EXTRACT_RESULTS_JS
