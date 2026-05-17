"""搜索引擎基类 - 定义搜索引擎的通用接口和功能。"""

import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Optional

import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from src.types import SearchEngine, SearchResult

logger = logging.getLogger(__name__)

# 常见的 User-Agent 列表
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]


class BaseSearchEngine(ABC):
    """搜索引擎基类，提供通用的浏览器管理和搜索接口。"""

    def __init__(
        self,
        engine_type: SearchEngine,
        headless: bool = True,
        max_results: int = 5,
        timeout: int = 30,
    ):
        """初始化搜索引擎。

        Args:
            engine_type: 搜索引擎类型
            headless: 是否使用无头模式
            max_results: 最大返回结果数量
            timeout: 页面加载超时时间（秒）
        """
        self.engine_type = engine_type
        self.headless = headless
        self.max_results = max_results
        self.timeout = timeout
        self._driver: Optional[uc.Chrome] = None

    def _get_chrome_options(self) -> Options:
        """获取 Chrome 配置选项。

        Returns:
            Chrome 选项对象
        """
        options = uc.ChromeOptions()

        if self.headless:
            options.add_argument("--headless=new")

        # 基础配置
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        # 随机 User-Agent
        user_agent = random.choice(USER_AGENTS)
        options.add_argument(f"--user-agent={user_agent}")

        # 禁用自动化标志
        options.add_argument("--disable-blink-features=AutomationControlled")

        return options

    def _get_driver(self) -> uc.Chrome:
        """获取或创建浏览器驱动实例。

        Returns:
            Chrome 驱动实例
        """
        if self._driver is None:
            options = self._get_chrome_options()
            self._driver = uc.Chrome(options=options)
            self._driver.set_page_load_timeout(self.timeout)
            logger.info(f"浏览器驱动已启动 ({self.engine_type.value})")
        return self._driver

    def _close_driver(self) -> None:
        """关闭浏览器驱动实例。"""
        if self._driver is not None:
            try:
                self._driver.quit()
                logger.info(f"浏览器驱动已关闭 ({self.engine_type.value})")
            except Exception as e:
                logger.warning(f"关闭浏览器驱动时出错: {e}")
            finally:
                self._driver = None

    def _human_like_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0) -> None:
        """模拟人类操作延迟。

        Args:
            min_seconds: 最小延迟时间
            max_seconds: 最大延迟时间
        """
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)

    @abstractmethod
    async def search(self, query: str) -> list[SearchResult]:
        """执行搜索操作。

        Args:
            query: 搜索查询词

        Returns:
            搜索结果列表

        Raises:
            Exception: 搜索失败时抛出异常
        """
        pass

    @abstractmethod
    def _parse_results(self, driver: uc.Chrome) -> list[SearchResult]:
        """解析搜索结果页面。

        Args:
            driver: 浏览器驱动实例

        Returns:
            解析后的搜索结果列表
        """
        pass

    async def __aenter__(self):
        """异步上下文管理器入口。"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口。"""
        self._close_driver()

    def __del__(self):
        """析构函数，确保浏览器驱动被关闭。"""
        self._close_driver()
