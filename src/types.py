"""类型定义模块 - 定义搜索引擎相关的数据类型。"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SearchEngine(str, Enum):
    """支持的搜索引擎枚举。"""

    GOOGLE = "google"
    BING = "bing"
    YAHOO = "yahoo"
    DUCKDUCKGO = "duckduckgo"


class SearchResult(BaseModel):
    """搜索结果数据模型。"""

    title: str = Field(..., description="搜索结果标题")
    href: str = Field(..., description="搜索结果链接")
    abstract: str = Field(default="", description="搜索结果摘要")
    source: Optional[SearchEngine] = Field(
        default=None, description="来源搜索引擎"
    )

    class Config:
        """Pydantic 配置。"""

        frozen = True
        json_schema_extra = {
            "example": {
                "title": "深圳市天气预报",
                "href": "https://weather.com/...",
                "abstract": "今天深圳天气晴朗...",
                "source": "bing",
            }
        }


class SearchResponse(BaseModel):
    """搜索响应数据模型。"""

    query: str = Field(..., description="搜索查询词")
    engine: SearchEngine = Field(..., description="使用的搜索引擎")
    results: list[SearchResult] = Field(
        default_factory=list, description="搜索结果列表"
    )
    total: int = Field(default=0, description="结果总数")
    error: Optional[str] = Field(default=None, description="错误信息（如果有）")

    class Config:
        """Pydantic 配置。"""

        frozen = True
