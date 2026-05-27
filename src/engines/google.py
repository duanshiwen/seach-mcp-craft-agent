"""Google 搜索引擎实现 - 使用 Playwright JS 渲染 + 语义结构解析。

解析策略：
- 基于 h3 标题 + a 链接的语义结构提取结果
- 不依赖特定的 CSS 类名（如 div.g, div.tF2Cxc 等）
- 自动处理 Google 重定向 URL
- 通过 Playwright JS 渲染绕过 CAPTCHA
"""

import asyncio
import json
import logging
import os
import random
import socket
import subprocess
import sys
from pathlib import Path
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

    # Google 使用 launch_persistent_context + 固定 user_data_dir 来保留 CAPTCHA
    # cookie。Chromium/Chrome 的持久化 profile 不能被同一进程中的多个
    # browser 实例并发独占，否则会触发 SingletonLock / database locked / 
    # “正在现有的浏览器会话中打开”，最终表现为 Playwright TargetClosedError。
    # 因此只串行化 Google profile 浏览器段；其他 HTTP 搜索引擎不受影响。
    _profile_lock: asyncio.Lock | None = None
    _profile_lock_loop: asyncio.AbstractEventLoop | None = None

    def __init__(self, **kwargs):
        """初始化 Google 搜索引擎。"""
        super().__init__(engine_type=SearchEngine.GOOGLE, **kwargs)
        self._playwright = None
        self._browser = None
        self._popup_browser = None
        self._popup_context = None
        self._popup_process = None
        self._captcha_timeout = int(os.getenv("GOOGLE_CAPTCHA_TIMEOUT", "300"))
        self._profile_dir = Path(
            os.getenv(
                "GOOGLE_PLAYWRIGHT_PROFILE_DIR",
                Path.home() / ".craft-agent" / "browser-profiles" / "search-engine-mcp-google",
            )
        )
        self._debug_log_path = Path(__file__).resolve().parents[2] / "google_captcha_debug.log"
        self._last_captcha_url_path = Path(__file__).resolve().parents[2] / "google_last_captcha_url.txt"

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

        # 不在这里启动普通 browser。
        # Google 搜索使用 launch_persistent_context，以便 CAPTCHA cookie 能持久化。
        # 若同时启动普通 browser + persistent context，既浪费资源，也容易让生命周期管理变复杂。

    async def _close_browser(self):
        """关闭 Playwright 浏览器（包括弹出浏览器）。"""
        try:
            if self._popup_context:
                await self._popup_context.close()
        except Exception as e:
            logger.warning(f"关闭弹出浏览器上下文时出错: {e}")
        finally:
            self._popup_context = None
        try:
            if self._popup_browser and hasattr(self._popup_browser, "is_connected") and self._popup_browser.is_connected():
                await self._popup_browser.close()
        except Exception as e:
            logger.warning(f"关闭弹出浏览器时出错: {e}")
        finally:
            self._popup_browser = None
        try:
            if self._popup_process and self._popup_process.poll() is None:
                self._popup_process.terminate()
        except Exception as e:
            logger.debug(f"结束原生 Chrome 弹窗进程失败: {e}")
        finally:
            self._popup_process = None
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
            self._debug_log(f"search query={query!r} url={url} force_popup={os.getenv('SEARCH_ENGINE_MCP_GOOGLE_FORCE_POPUP')!r}")

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

        lock = self._get_profile_lock()
        self._debug_log(f"waiting google profile lock url={url}")
        async with lock:
            self._debug_log(f"acquired google profile lock url={url}")
            try:
                return await self._search_with_visible_browser(url)
            finally:
                self._debug_log(f"releasing google profile lock url={url}")

    @classmethod
    def _get_profile_lock(cls) -> asyncio.Lock:
        """获取当前事件循环上的 Google profile 串行锁。

        asyncio.Lock 绑定事件循环；测试或嵌入式运行时可能创建新的 loop。
        因此按当前 running loop 懒加载，避免跨 loop 复用锁。
        """
        loop = asyncio.get_running_loop()
        if cls._profile_lock is None or cls._profile_lock_loop is not loop:
            cls._profile_lock = asyncio.Lock()
            cls._profile_lock_loop = loop
        return cls._profile_lock

    async def _search_with_visible_browser(self, url: str) -> list[dict]:
        """直接打开可见浏览器搜索，拿到结果后自动关闭。"""
        self._debug_log(f"visible search start url={url}")
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        self._terminate_existing_profile_chrome()

        context = None
        try:
            launch_kwargs = {
                "user_data_dir": str(self._profile_dir),
                "headless": False,
                "user_agent": random.choice(self._get_user_agents()),
                "viewport": {"width": 1366, "height": 900},
                "locale": "zh-CN",
                "timezone_id": "Asia/Shanghai",
                "args": self._browser_args() + [
                    "--window-position=80,80",
                    "--window-size=1366,900",
                ],
            }
            try:
                context = await self._playwright.chromium.launch_persistent_context(
                    channel="chrome",
                    **launch_kwargs,
                )
                self._activate_browser_window("Google Chrome")
            except Exception as e:
                self._debug_log(f"visible system chrome launch failed err={e!r}; fallback chromium")
                context = await self._playwright.chromium.launch_persistent_context(
                    **launch_kwargs,
                )
                self._activate_browser_window("Chromium")

            page = context.pages[0] if context.pages else await context.new_page()
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
            """)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.warning(f"可见 Google 窗口导航未完全完成，继续等待: {e}")
                self._debug_log(f"visible goto warning err={e!r}")

            start_time = asyncio.get_event_loop().time()
            notified = False
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > self._captcha_timeout:
                    self._debug_log(f"visible search timeout seconds={self._captcha_timeout}")
                    logger.warning(f"可见 Google 搜索超时（{self._captcha_timeout}秒）")
                    return []

                await asyncio.sleep(2)
                try:
                    html = await page.content()
                    current_url = page.url
                except Exception as e:
                    self._debug_log(f"visible page unreadable err={e!r}")
                    return []

                blocked = self._is_blocked(html, current_url)
                if blocked and not notified:
                    notified = True
                    self._debug_log(f"visible search captcha detected url={current_url}")
                    try:
                        self._last_captcha_url_path.write_text(current_url or url, encoding="utf-8")
                    except Exception:
                        pass
                    print(
                        "\n⚠️ Google 触发 CAPTCHA。请在已打开的可见浏览器窗口中完成验证。\n",
                        file=sys.stderr,
                        flush=True,
                    )
                    self._activate_browser_window("Google Chrome")

                results = []
                if not blocked:
                    try:
                        results = await page.evaluate(EXTRACT_RESULTS_JS)
                    except Exception as e:
                        self._debug_log(f"visible extract warning err={e!r}")

                if results:
                    self._debug_log(f"visible search extracted results={len(results)}")
                    logger.info(f"可见 Google 搜索提取到 {len(results)} 个结果，准备关闭窗口")
                    return results

        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception as e:
                    logger.debug(f"关闭可见 Google 浏览器失败: {e}")
            self._terminate_existing_profile_chrome()

    def _is_blocked(self, html: str, current_url: str = "") -> bool:
        """检测页面是否被 Google 拦截。

        CAPTCHA 页面形态不稳定：有时是 /sorry/index，有时嵌入 reCAPTCHA，
        有时仍保留 #main 或其他主体容器。因此只要命中强验证特征，就触发弹窗。

        Args:
            html: 页面 HTML 内容
            current_url: 当前页面 URL

        Returns:
            是否被拦截
        """
        return self._looks_like_google_verification(html, current_url)

    def _looks_like_google_verification(self, html: str, current_url: str = "") -> bool:
        """判断页面是否疑似 Google 验证 / 风控页面。"""
        lower = html.lower()
        url_lower = (current_url or "").lower()

        url_indicators = [
            "/sorry/",
            "sorry/index",
            "continue=",
        ]
        if "google." in url_lower and any(ind in url_lower for ind in url_indicators):
            return True

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

    async def _handle_captcha_with_popup(self, url: str) -> list[dict]:
        """当 CAPTCHA 被检测到时，弹出可见浏览器窗口等待用户手动验证。

        关闭现有 headless 浏览器，启动一个非 headless 浏览器。
        用户在浏览器窗口中手动完成人机验证后，自动提取搜索结果。

        Args:
            url: Google 搜索 URL

        Returns:
            验证通过后的搜索结果列表（超时则返回空列表）
        """
        banner = "=" * 60
        msg = (
            f"\n{banner}\n"
            f"  ⚠️  Google 触发了人机验证（CAPTCHA）\n"
            f"  🖥️  正在弹出浏览器窗口，请在窗口中完成验证……\n"
            f"  ⏱️  最多等待 {self._captcha_timeout} 秒\n"
            f"{banner}\n"
        )
        logger.warning("Google CAPTCHA — 弹出浏览器等待用户手动验证")
        self._debug_log(f"captcha handler entered url={url}")
        try:
            self._last_captcha_url_path.write_text(url, encoding="utf-8")
        except Exception:
            pass
        print(msg, file=sys.stderr, flush=True)

        # 立即显示 macOS 系统提示 + 打开 Chrome。即使 Chrome 被复用到后台 tab，
        # 用户也能看到系统级 CAPTCHA 提示和可复制 URL。
        self._show_captcha_system_prompt(url)
        self._open_url_with_system_chrome(url)
        print(f"🔗 如果没有看到弹窗，请手动打开：{url}\n", file=sys.stderr, flush=True)

        # 先关闭现有的 headless 上下文
        try:
            if self._browser and self._browser.is_connected():
                await self._browser.close()
                self._browser = None
        except Exception as e:
            logger.warning(f"关闭 headless 浏览器时出错: {e}")

        # 确保 Playwright 仍在运行
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright 未安装。请运行：\n"
                "pip install playwright && python -m playwright install chromium"
            )
        if self._playwright is None:
            self._playwright = await async_playwright().start()

        # 启动非 headless 持久化浏览器上下文。
        # 首选直接拉起真实 Chrome 窗口，再通过 CDP 连接。
        # 启动前先清理同一专用 profile 的旧 Chrome，否则 Chrome 会复用旧会话，
        # 新的 --remote-debugging-port 不生效，表现为“没有弹出可控窗口”。
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        self._terminate_existing_profile_chrome()
        context = None
        page = None
        keep_popup_open = False
        if sys.platform == "darwin":
            try:
                # 先用 AppleScript 在当前登录用户桌面打开/置前一个 Chrome 窗口。
                # 这一步不依赖 Playwright/CDP，是“用户必须看得到弹窗”的主路径。
                self._open_url_with_system_chrome(url)
                await asyncio.sleep(0.8)
                self._activate_browser_window("Google Chrome")

                port = self._get_free_port()
                chrome_bin = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                chrome_args = [
                    chrome_bin,
                    f"--remote-debugging-port={port}",
                    f"--user-data-dir={self._profile_dir}",
                    "--new-window",
                    "--start-maximized",
                    "--window-position=80,80",
                    "--window-size=1366,900",
                    "--no-first-run",
                    "--no-default-browser-check",
                    url,
                ]
                logger.warning("正在直接启动 Google Chrome CAPTCHA 窗口: %s", chrome_bin)
                self._popup_process = subprocess.Popen(
                    chrome_args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                keep_popup_open = True
                await asyncio.sleep(0.8)
                self._activate_browser_window("Google Chrome")
                self._activate_process_window(self._popup_process.pid)
                self._popup_browser = await self._connect_over_cdp(port)
                context = self._popup_browser.contexts[0]
                # 等待 Chrome 创建页面。
                for _ in range(30):
                    if context.pages:
                        page = context.pages[-1]
                        break
                    await asyncio.sleep(0.2)
                if page is None:
                    page = await context.new_page()
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.warning(f"原生 Chrome CAPTCHA 窗口已尝试打开，但 CDP 连接失败: {e}")
                # 如果进程仍在，说明可见窗口大概率已经打开。不要立即回退并抢占同一 profile，
                # 否则会把用户可见的验证窗口关掉/干扰掉。
                if self._popup_process and self._popup_process.poll() is None:
                    self._activate_browser_window("Google Chrome")
                    self._activate_process_window(self._popup_process.pid)
                    self._open_url_with_system_chrome(url)
                    print(
                        "\n⚠️ 已尝试打开 Google Chrome CAPTCHA 窗口，但无法连接自动轮询。"
                        "请在弹出的 Chrome 窗口中完成验证，然后重试搜索。\n",
                        file=sys.stderr,
                        flush=True,
                    )
                    return []
                context = None
                page = None

        if context is None:
            launch_kwargs = {
                "user_data_dir": str(self._profile_dir),
                "headless": False,
                "user_agent": random.choice(self._get_user_agents()),
                "viewport": {"width": 1366, "height": 900},
                "locale": "zh-CN",
                "timezone_id": "Asia/Shanghai",
                "args": self._browser_args(),
            }
            try:
                context = await self._playwright.chromium.launch_persistent_context(
                    channel="chrome",
                    **launch_kwargs,
                )
                self._activate_browser_window("Google Chrome")
            except Exception as e:
                logger.warning(f"使用系统 Chrome 弹窗失败，回退到 Playwright Chromium: {e}")
                context = await self._playwright.chromium.launch_persistent_context(
                    **launch_kwargs,
                )
                self._activate_browser_window("Chromium")
            page = context.pages[0] if context.pages else await context.new_page()

        self._popup_context = context

        try:
            # 添加反检测脚本
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en']
                });
            """)

            # 访问 Google 搜索页面（此时会显示 CAPTCHA）。
            # 不使用 networkidle，避免 reCAPTCHA 长连接导致可见弹窗流程超时退出。
            response = None
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.warning(f"弹出浏览器页面导航未完全完成，继续等待用户验证: {e}")
            if not response or response.status != 200:
                logger.warning(
                    f"弹出浏览器页面返回状态码: "
                    f"{response.status if response else 'None'}"
                )

            # 等待用户手动完成验证（每 2 秒轮询一次）
            start_time = asyncio.get_event_loop().time()
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > self._captcha_timeout:
                    timeout_msg = (
                        f"\n⏰ CAPTCHA 验证超时（{self._captcha_timeout} 秒），"
                        f"请稍后重试或使用其他搜索引擎。\n"
                    )
                    logger.warning(
                        f"CAPTCHA 验证超时（{self._captcha_timeout}秒），放弃等待"
                    )
                    print(timeout_msg, file=sys.stderr, flush=True)
                    if keep_popup_open:
                        self._activate_browser_window("Google Chrome")
                        if self._popup_process:
                            self._activate_process_window(self._popup_process.pid)
                        self._open_url_with_system_chrome(url)
                        print(
                            "⚠️ Chrome CAPTCHA 窗口将保持打开。请在窗口中完成验证后重试 Google 搜索。\n",
                            file=sys.stderr,
                            flush=True,
                        )
                    return []

                await asyncio.sleep(2)

                try:
                    html = await page.content()
                    current_url = page.url
                except Exception as e:
                    logger.warning(f"CAPTCHA 弹窗页面暂时不可读，保持窗口打开等待用户手动验证: {e}")
                    if keep_popup_open:
                        print(
                            "\n⚠️ Chrome CAPTCHA 窗口已打开，但自动轮询无法读取页面。"
                            "请在窗口中完成验证后重试 Google 搜索。\n",
                            file=sys.stderr,
                            flush=True,
                        )
                        return []
                    raise
                results = []
                if not self._is_blocked(html, current_url):
                    # 只有确实提取到搜索结果，才认为 CAPTCHA 已完成。
                    # 避免把 Google consent / 空白页 / 中间跳转页误判为验证通过。
                    try:
                        results = await page.evaluate(EXTRACT_RESULTS_JS)
                    except Exception as e:
                        logger.debug(f"CAPTCHA 轮询中提取结果失败，继续等待: {e}")

                if results:
                    passed_msg = (
                        f"\n✅ CAPTCHA 验证通过！正在提取搜索结果……\n"
                    )
                    logger.info("CAPTCHA 验证通过！正在提取搜索结果...")
                    print(passed_msg, file=sys.stderr, flush=True)
                    logger.info(f"验证通过后提取到 {len(results)} 个结果")
                    return results

                logger.debug(
                    "等待 CAPTCHA 验证完成: elapsed=%.1fs url=%s blocked=%s",
                    elapsed,
                    current_url,
                    self._is_blocked(html, current_url),
                )

        finally:
            if keep_popup_open:
                # 保持原生 Chrome 窗口打开，避免用户看到“一闪而过”。
                # 下次搜索开始前会由 _terminate_existing_profile_chrome 清理旧窗口。
                self._popup_context = None
                self._popup_browser = None
                self._popup_process = None
            else:
                try:
                    if context is not None:
                        await context.close()
                finally:
                    self._terminate_existing_profile_chrome()
                    self._popup_context = None
                    self._popup_browser = None
                    self._popup_process = None

    def _debug_log(self, message: str) -> None:
        """写入 Google CAPTCHA 调试日志。"""
        try:
            from datetime import datetime
            ts = datetime.now().isoformat(timespec="seconds")
            with self._debug_log_path.open("a", encoding="utf-8") as f:
                f.write(f"[{ts}] {message}\n")
        except Exception:
            pass

    def _terminate_existing_profile_chrome(self) -> None:
        """终止占用专用 Google profile 的旧 Chrome 进程。"""
        if sys.platform != "darwin":
            return
        try:
            profile = str(self._profile_dir)
            # 只匹配本 source 专用 profile，避免影响用户日常 Chrome。
            cmd = f"pkill -f 'Google Chrome.*--user-data-dir={profile}' || true"
            self._debug_log(f"terminate existing chrome profile={profile}")
            subprocess.run(
                ["/bin/bash", "-lc", cmd],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except Exception as e:
            logger.debug(f"清理旧 Chrome profile 进程失败: {e}")

    def _get_free_port(self) -> int:
        """获取一个本机空闲端口，用于 Chrome remote debugging。"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    async def _connect_over_cdp(self, port: int):
        """等待并连接到通过 macOS open 启动的 Chrome CDP 端点。"""
        endpoint = f"http://127.0.0.1:{port}"
        last_error = None
        for _ in range(50):
            try:
                return await self._playwright.chromium.connect_over_cdp(endpoint)
            except Exception as e:
                last_error = e
                await asyncio.sleep(0.2)
        raise RuntimeError(f"无法连接 Chrome remote debugging 端口 {port}: {last_error}")

    def _browser_args(self) -> list[str]:
        """获取 Chromium 启动参数。"""
        return [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--start-maximized",
        ]

    def _activate_browser_window(self, app_name: str) -> None:
        """在 macOS 上尽量把 CAPTCHA 浏览器窗口切到前台。"""
        if sys.platform != "darwin":
            return
        try:
            subprocess.run(
                ["/usr/bin/osascript", "-e", f'tell application "{app_name}" to activate'],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
        except Exception as e:
            logger.debug(f"激活浏览器窗口失败: {e}")

    def _activate_process_window(self, pid: int | None) -> None:
        """按 PID 强制把 Chrome CAPTCHA 进程置前，并调整窗口位置。"""
        if sys.platform != "darwin" or not pid:
            return
        script = f'''
        tell application "System Events"
            set targetProc to first process whose unix id is {pid}
            set frontmost of targetProc to true
            try
                set position of front window of targetProc to {{80, 80}}
                set size of front window of targetProc to {{1366, 900}}
            end try
        end tell
        '''
        try:
            subprocess.run(
                ["/usr/bin/osascript", "-e", script],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
        except Exception as e:
            logger.debug(f"按 PID 激活浏览器窗口失败: {e}")

    def _show_captcha_system_prompt(self, url: str) -> None:
        """显示 macOS 系统级 CAPTCHA 提示，避免 Chrome 后台打开时用户无感。"""
        if sys.platform != "darwin":
            return
        uid = str(os.getuid())
        message = "Google 触发 CAPTCHA。已尝试打开 Chrome；如果没看到窗口，请复制并打开：\n\n" + url
        dialog_script = (
            'display dialog '
            + json.dumps(message)
            + ' buttons {"OK"} default button "OK" with title "Google CAPTCHA"'
        )
        notification_script = (
            'display notification '
            + json.dumps("请在 Chrome 中完成 Google CAPTCHA；若未看到窗口，请查看 google_last_captcha_url.txt")
            + ' with title "Google CAPTCHA" subtitle "search-engine-mcp"'
        )
        try:
            subprocess.Popen(
                ["/bin/launchctl", "asuser", uid, "/usr/bin/osascript", "-e", notification_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self._debug_log("captcha notification invoked")
        except Exception as e:
            self._debug_log(f"captcha notification exception={e!r}")
        try:
            subprocess.Popen(
                ["/bin/launchctl", "asuser", uid, "/usr/bin/osascript", "-e", dialog_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self._debug_log("captcha dialog invoked")
        except Exception as e:
            self._debug_log(f"captcha dialog exception={e!r}")

    def _open_url_with_system_chrome(self, url: str) -> None:
        """最后兜底：通过当前 macOS 用户会话打开一个可见 Chrome 窗口。"""
        if sys.platform != "darwin":
            return

        uid = str(os.getuid())

        # 第一选择：通过 launchctl 投递到当前登录用户 GUI 会话。
        # MCP stdio 子进程可能不是 Aqua 前台会话，直接 open 会“成功但不可见”。
        try:
            result = subprocess.run(
                ["/bin/launchctl", "asuser", uid, "/usr/bin/open", "-na", "Google Chrome", url],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=8,
            )
            self._debug_log(f"launchctl asuser open -na Chrome rc={result.returncode} stderr={result.stderr.strip()!r}")
            self._activate_browser_window("Google Chrome")
            if result.returncode == 0:
                return
        except Exception as e:
            self._debug_log(f"launchctl asuser open exception={e!r}")

        # 第二选择：强制新 Chrome 实例/窗口。避免 open -a 复用已有后台 tab。
        try:
            result = subprocess.run(
                ["/usr/bin/open", "-na", "Google Chrome", url],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            self._debug_log(f"open -na Google Chrome rc={result.returncode} stderr={result.stderr.strip()!r}")
            self._activate_browser_window("Google Chrome")
            if result.returncode == 0:
                return
        except Exception as e:
            self._debug_log(f"open -na Google Chrome exception={e!r}")

        # 第三选择：使用用户会话的 open location；不依赖 Chrome AppleScript 对象模型。
        quoted_url = json.dumps(url)
        try:
            result = subprocess.run(
                ["/bin/launchctl", "asuser", uid, "/usr/bin/osascript", "-e", f'open location {quoted_url}', "-e", 'tell application "Google Chrome" to activate'],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=8,
            )
            self._debug_log(f"launchctl asuser osascript open location rc={result.returncode} stderr={result.stderr.strip()!r}")
            if result.returncode == 0:
                return
        except Exception as e:
            self._debug_log(f"launchctl asuser osascript exception={e!r}")
            logger.debug(f"AppleScript open location 打开 CAPTCHA URL 失败: {e}")

        # 第四选择：至少弹出一个 macOS 对话框，把 URL 明确展示给用户。
        try:
            dialog_script = (
                'display dialog '
                + json.dumps("Google 触发 CAPTCHA，但自动打开 Chrome 失败。请复制并手动打开：\n\n" + url)
                + ' buttons {"OK"} default button "OK" with title "Google CAPTCHA"'
            )
            subprocess.Popen(
                ["/bin/launchctl", "asuser", uid, "/usr/bin/osascript", "-e", dialog_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self._debug_log("fallback launchctl display dialog invoked")
        except Exception as e:
            self._debug_log(f"fallback display dialog exception={e!r}")
            logger.debug(f"系统弹窗展示 CAPTCHA URL 失败: {e}")

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
