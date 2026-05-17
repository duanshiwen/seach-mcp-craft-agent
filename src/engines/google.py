"""Google 搜索引擎实现。"""

import logging
from urllib.parse import quote_plus

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.types import SearchEngine, SearchResult

from .base import BaseSearchEngine

logger = logging.getLogger(__name__)


class GoogleSearchEngine(BaseSearchEngine):
    """Google 搜索引擎实现。"""

    BASE_URL = "https://www.google.com/search"

    def __init__(self, **kwargs):
        """初始化 Google 搜索引擎。"""
        super().__init__(engine_type=SearchEngine.GOOGLE, **kwargs)

    async def search(self, query: str) -> list[SearchResult]:
        """执行 Google 搜索。

        Args:
            query: 搜索查询词

        Returns:
            搜索结果列表

        Raises:
            Exception: 搜索失败时抛出异常
        """
        driver = self._get_driver()

        try:
            # 构建搜索 URL
            encoded_query = quote_plus(query)
            url = f"{self.BASE_URL}?q={encoded_query}&hl=zh-CN&gl=cn"

            logger.info(f"正在搜索 Google: {query}")
            driver.get(url)

            # 模拟人类延迟
            self._human_like_delay(2, 4)

            # 等待搜索结果加载
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#search"))
            )

            # 解析结果
            results = self._parse_results(driver)

            logger.info(f"Google 搜索完成，找到 {len(results)} 个结果")
            return results

        except Exception as e:
            logger.error(f"Google 搜索失败: {e}")
            raise
        finally:
            self._close_driver()

    def _parse_results(self, driver) -> list[SearchResult]:
        """解析 Google 搜索结果页面。

        Args:
            driver: 浏览器驱动实例

        Returns:
            解析后的搜索结果列表
        """
        results = []

        try:
            # 查找所有搜索结果
            result_elements = driver.find_elements(
                By.CSS_SELECTOR, "#search .g"
            )

            for i, element in enumerate(result_elements[: self.max_results]):
                try:
                    # 提取标题
                    title_element = element.find_element(By.CSS_SELECTOR, "h3")
                    title = title_element.text.strip()

                    # 提取链接
                    link_element = element.find_element(By.CSS_SELECTOR, "a")
                    href = link_element.get_attribute("href")

                    # 提取摘要
                    abstract = ""
                    try:
                        abstract_element = element.find_element(
                            By.CSS_SELECTOR, ".VwiC3b, .IsZvec, .s3v9rd"
                        )
                        abstract = abstract_element.text.strip()
                    except Exception:
                        # 如果找不到摘要元素，尝试其他选择器
                        try:
                            abstract_element = element.find_element(
                                By.CSS_SELECTOR, "span.st, div[data-sncf]"
                            )
                            abstract = abstract_element.text.strip()
                        except Exception:
                            pass

                    # 只添加有效的结果
                    if title and href:
                        results.append(
                            SearchResult(
                                title=title,
                                href=href,
                                abstract=abstract,
                                source=SearchEngine.GOOGLE,
                            )
                        )
                        logger.debug(f"解析结果 {i+1}: {title}")

                except Exception as e:
                    logger.warning(f"解析第 {i+1} 个结果时出错: {e}")
                    continue

        except Exception as e:
            logger.error(f"解析 Google 搜索结果页面失败: {e}")

        return results
