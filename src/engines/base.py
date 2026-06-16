"""搜索引擎基类 - 使用 HTTP 请求实现，无需浏览器驱动。"""

import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from src.types import SearchEngine, SearchResult

logger = logging.getLogger(__name__)

# 常见的 User-Agent 列表
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]


class BaseSearchEngine(ABC):
    """搜索引擎基类，提供通用的 HTTP 客户端和搜索接口。"""

    def __init__(
        self,
        engine_type: SearchEngine,
        max_results: int = 5,
        timeout: int = 15,
    ):
        """初始化搜索引擎。

        Args:
            engine_type: 搜索引擎类型
            max_results: 最大返回结果数量
            timeout: 请求超时时间（秒）
        """
        self.engine_type = engine_type
        self.max_results = max_results
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _get_headers(self) -> dict[str, str]:
        """获取 HTTP 请求头。

        Returns:
            请求头字典
        """
        user_agent = random.choice(USER_AGENTS)
        return {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

    def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端实例。

        Returns:
            httpx 异步客户端
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self._get_headers(),
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
            )
        return self._client

    async def _close_client(self) -> None:
        """关闭 HTTP 客户端。"""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _fetch_page(self, url: str) -> str:
        """获取页面 HTML 内容。

        Args:
            url: 页面 URL

        Returns:
            HTML 内容字符串

        Raises:
            httpx.HTTPError: 请求失败
        """
        client = self._get_client()
        response = await client.get(url)
        response.raise_for_status()
        return response.text

    def _human_like_delay(self, min_seconds: float = 0.5, max_seconds: float = 1.5) -> None:
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

    async def __aenter__(self):
        """异步上下文管理器入口。"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口。"""
        await self._close_client()

    def __del__(self):
        """析构函数。"""
        # Note: cannot await in __del__, client will be garbage collected
        pass
