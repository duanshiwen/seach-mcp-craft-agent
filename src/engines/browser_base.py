"""浏览器搜索引擎基类 - 提供可见浏览器窗口和 CAPTCHA 处理能力。

所有需要浏览器渲染的搜索引擎（Google、Bing、百度）共享此基类。
核心职责：
1. Playwright 浏览器生命周期管理
2. 可见浏览器窗口弹出与 CAPTCHA 等待
3. 全局队列锁 - 同一时间只允许一个引擎弹出浏览器窗口
4. macOS 窗口激活与系统通知
5. 持久化 profile 目录管理

子类只需实现：
- _get_search_url(query): 构造搜索 URL
- _is_blocked(html, url): 检测 CAPTCHA/拦截
- _extract_results_js: JavaScript 提取结果代码（属性）
"""

import asyncio
import json
import logging
import os
import random
import socket
import subprocess
import sys
from abc import abstractmethod
from pathlib import Path
from urllib.parse import quote_plus

from src.types import SearchEngine, SearchResult

from .base import BaseSearchEngine

logger = logging.getLogger(__name__)

# 全局锁 - 所有浏览器引擎共享，确保同一时间只有一个弹出窗口
_browser_global_lock: asyncio.Lock | None = None
_browser_global_lock_loop: asyncio.AbstractEventLoop | None = None


def _get_browser_global_lock() -> asyncio.Lock:
    """获取全局浏览器队列锁。

    asyncio.Lock 绑定事件循环，因此按当前 running loop 懒加载。
    """
    global _browser_global_lock, _browser_global_lock_loop
    loop = asyncio.get_running_loop()
    if _browser_global_lock is None or _browser_global_lock_loop is not loop:
        _browser_global_lock = asyncio.Lock()
        _browser_global_lock_loop = loop
    return _browser_global_lock


class BrowserSearchEngine(BaseSearchEngine):
    """浏览器搜索引擎基类。

    提供可见浏览器窗口搜索、CAPTCHA 处理、队列管理等能力。
    子类必须实现以下抽象方法/属性：
    - _get_search_url(query) -> str
    - _is_blocked(html, url) -> bool
    - _extract_results_js (property) -> str: 浏览器内执行的 JavaScript 代码
    """

    # 子类必须覆盖：搜索引擎名称（用于日志和窗口标题）
    ENGINE_NAME: str = "Unknown"
    # 子类必须覆盖：profile 目录名
    PROFILE_DIR_NAME: str = "unknown"

    def __init__(
        self,
        engine_type: SearchEngine,
        max_results: int = 5,
        timeout: int = 15,
        **kwargs,
    ):
        """初始化浏览器搜索引擎。

        Args:
            engine_type: 搜索引擎类型
            max_results: 最大返回结果数量
            timeout: 请求超时时间（秒）
        """
        super().__init__(engine_type=engine_type, max_results=max_results, timeout=timeout)
        self._playwright = None
        self._popup_context = None
        self._popup_browser = None
        self._popup_process = None
        self._captcha_timeout = int(os.getenv("SEARCH_ENGINE_MCP_CAPTCHA_TIMEOUT", "300"))
        self._profile_dir = Path(
            os.getenv(
                f"SEARCH_ENGINE_MCP_{self.PROFILE_DIR_NAME.upper()}_PROFILE_DIR",
                Path.home() / ".craft-agent" / "browser-profiles" / f"search-engine-mcp-{self.PROFILE_DIR_NAME}",
            )
        )
        self._debug_log_path = Path(__file__).resolve().parents[2] / f"{self.PROFILE_DIR_NAME}_captcha_debug.log"

    # ── 抽象方法 ──────────────────────────────────────────────────────────────

    @abstractmethod
    def _get_search_url(self, query: str) -> str:
        """构造搜索引擎 URL。

        Args:
            query: 搜索查询词

        Returns:
            完整的搜索 URL
        """
        pass

    @abstractmethod
    def _is_blocked(self, html: str, url: str = "") -> bool:
        """检测页面是否被 CAPTCHA/拦截。

        Args:
            html: 页面 HTML 内容
            url: 当前页面 URL

        Returns:
            是否被拦截
        """
        pass

    @property
    @abstractmethod
    def _extract_results_js(self) -> str:
        """返回在浏览器中执行的 JavaScript 提取逻辑。

        Returns:
            JavaScript 代码字符串，返回 [{title, href, abstract}, ...]
        """
        pass

    # ── 浏览器生命周期 ────────────────────────────────────────────────────────

    async def _init_playwright(self):
        """初始化 Playwright 实例。"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright 未安装。请运行：\n"
                "pip install playwright && python -m playwright install chromium"
            )

        if self._playwright is None:
            self._playwright = await async_playwright().start()

    async def _close_playwright(self):
        """关闭 Playwright 实例和所有相关资源。"""
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
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"关闭 Playwright 时出错: {e}")
        finally:
            self._playwright = None

    # ── 搜索主流程 ────────────────────────────────────────────────────────────

    async def search(self, query: str) -> list[SearchResult]:
        """执行浏览器搜索。

        Args:
            query: 搜索查询词

        Returns:
            搜索结果列表

        Raises:
            Exception: 搜索失败时抛出异常
        """
        try:
            url = self._get_search_url(query)
            logger.info(f"正在搜索 {self.ENGINE_NAME} (浏览器模式): {query}")
            self._debug_log(f"search query={query!r} url={url}")

            # 使用浏览器获取并提取结果
            raw_results = await self._fetch_and_extract(url)

            # 转换为 SearchResult 对象
            results = []
            for item in raw_results[:self.max_results]:
                results.append(
                    SearchResult(
                        title=item["title"],
                        href=item["href"],
                        abstract=item.get("abstract", ""),
                        source=self.engine_type,
                    )
                )

            logger.info(f"{self.ENGINE_NAME} 搜索完成，找到 {len(results)} 个结果")
            return results

        except Exception as e:
            logger.error(f"{self.ENGINE_NAME} 搜索失败: {e}")
            raise
        finally:
            await self._close_playwright()

    async def _fetch_and_extract(self, url: str) -> list[dict]:
        """使用浏览器获取页面并提取搜索结果。

        Args:
            url: 搜索 URL

        Returns:
            原始结果字典列表
        """
        await self._init_playwright()

        # 获取全局锁 - 确保同一时间只有一个引擎弹出浏览器
        lock = _get_browser_global_lock()
        self._debug_log(f"waiting browser global lock url={url}")
        async with lock:
            self._debug_log(f"acquired browser global lock url={url}")
            try:
                return await self._search_with_visible_browser(url)
            finally:
                self._debug_log(f"releasing browser global lock url={url}")

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
                # 移除 Playwright 默认添加的 --no-sandbox，避免 Chrome 弹警告条
                "ignore_default_args": ["--no-sandbox"],
            }

            # 尝试使用系统 Chrome，失败则回退到 Playwright Chromium
            try:
                context = await self._playwright.chromium.launch_persistent_context(
                    channel="chrome",
                    **launch_kwargs,
                )
                self._activate_browser_window("Google Chrome")
            except Exception as e:
                self._debug_log(f"system chrome launch failed err={e!r}; fallback chromium")
                context = await self._playwright.chromium.launch_persistent_context(
                    **launch_kwargs,
                )
                self._activate_browser_window("Chromium")

            page = context.pages[0] if context.pages else await context.new_page()

            # 添加反检测脚本
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
            """)

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.warning(f"可见 {self.ENGINE_NAME} 窗口导航未完全完成，继续等待: {e}")
                self._debug_log(f"visible goto warning err={e!r}")

            # 轮询等待结果或 CAPTCHA
            start_time = asyncio.get_event_loop().time()
            notified = False
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > self._captcha_timeout:
                    self._debug_log(f"visible search timeout seconds={self._captcha_timeout}")
                    logger.warning(f"可见 {self.ENGINE_NAME} 搜索超时（{self._captcha_timeout}秒）")
                    return []

                await asyncio.sleep(2)
                try:
                    html = await page.content()
                    current_url = page.url
                except Exception as e:
                    self._debug_log(f"visible page unreadable err={e!r}")
                    return []

                # 检测 CAPTCHA
                blocked = self._is_blocked(html, current_url)
                if blocked and not notified:
                    notified = True
                    self._debug_log(f"visible search captcha detected url={current_url}")
                    print(
                        f"\n⚠️ {self.ENGINE_NAME} 触发 CAPTCHA。请在已打开的可见浏览器窗口中完成验证。\n",
                        file=sys.stderr,
                        flush=True,
                    )
                    self._activate_browser_window("Google Chrome")

                results = []
                if not blocked:
                    try:
                        results = await page.evaluate(self._extract_results_js)
                    except Exception as e:
                        self._debug_log(f"visible extract warning err={e!r}")

                if results:
                    self._debug_log(f"visible search extracted results={len(results)}")
                    logger.info(f"可见 {self.ENGINE_NAME} 搜索提取到 {len(results)} 个结果，准备关闭窗口")
                    return results

        finally:
            if context is not None:
                try:
                    await context.close()
                except Exception as e:
                    logger.debug(f"关闭可见 {self.ENGINE_NAME} 浏览器失败: {e}")
            self._terminate_existing_profile_chrome()

    # ── macOS 辅助方法 ────────────────────────────────────────────────────────

    def _terminate_existing_profile_chrome(self) -> None:
        """终止占用专用 profile 的旧 Chrome 进程。"""
        if sys.platform != "darwin":
            return
        try:
            profile = str(self._profile_dir)
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

    def _activate_browser_window(self, app_name: str) -> None:
        """在 macOS 上把浏览器窗口切到前台。"""
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
        """按 PID 强制把 Chrome 进程置前。"""
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

    # ── 工具方法 ──────────────────────────────────────────────────────────────

    def _get_free_port(self) -> int:
        """获取一个本机空闲端口。"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _browser_args(self) -> list[str]:
        """获取 Chromium 启动参数。

        注意：不使用 --no-sandbox / --disable-setuid-sandbox / --disable-blink-features
        等会触发 Chrome 橙色警告条的参数。反检测由 add_init_script 覆盖。
        """
        return [
            "--disable-dev-shm-usage",
        ]

    def _get_user_agents(self) -> list[str]:
        """获取 User-Agent 列表。"""
        return [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        ]

    def _debug_log(self, message: str) -> None:
        """写入调试日志。"""
        try:
            from datetime import datetime
            ts = datetime.now().isoformat(timespec="seconds")
            with self._debug_log_path.open("a", encoding="utf-8") as f:
                f.write(f"[{ts}] {message}\n")
        except Exception:
            pass
