"""搜索引擎单元测试。"""

import pytest
from src.types import SearchEngine, SearchResult
from src.utils import validate_query, get_engine_display_name, format_results_for_display


class TestTypes:
    """类型定义测试。"""

    def test_search_result_creation(self):
        """测试 SearchResult 创建。"""
        result = SearchResult(
            title="测试标题",
            href="https://example.com",
            abstract="测试摘要",
            source=SearchEngine.BING,
        )

        assert result.title == "测试标题"
        assert result.href == "https://example.com"
        assert result.abstract == "测试摘要"
        assert result.source == SearchEngine.BING

    def test_search_result_defaults(self):
        """测试 SearchResult 默认值。"""
        result = SearchResult(
            title="测试标题",
            href="https://example.com",
        )

        assert result.abstract == ""
        assert result.source is None

    def test_search_engine_enum(self):
        """测试 SearchEngine 枚举。"""
        assert SearchEngine.GOOGLE.value == "google"
        assert SearchEngine.BING.value == "bing"
        assert SearchEngine.YAHOO.value == "yahoo"
        assert SearchEngine.DUCKDUCKGO.value == "duckduckgo"


class TestUtils:
    """工具函数测试。"""

    def test_validate_query_valid(self):
        """测试有效查询词验证。"""
        is_valid, error = validate_query("测试查询")
        assert is_valid is True
        assert error is None

    def test_validate_query_empty(self):
        """测试空查询词验证。"""
        is_valid, error = validate_query("")
        assert is_valid is False
        assert error == "搜索查询词不能为空"

    def test_validate_query_whitespace(self):
        """测试空白查询词验证。"""
        is_valid, error = validate_query("   ")
        assert is_valid is False
        assert error == "搜索查询词不能为空"

    def test_validate_query_too_long(self):
        """测试过长查询词验证。"""
        long_query = "a" * 501
        is_valid, error = validate_query(long_query)
        assert is_valid is False
        assert error == "搜索查询词过长（最多 500 个字符）"

    def test_get_engine_display_name(self):
        """测试获取引擎显示名称。"""
        assert get_engine_display_name(SearchEngine.GOOGLE) == "Google"
        assert get_engine_display_name(SearchEngine.BING) == "Bing"
        assert get_engine_display_name(SearchEngine.YAHOO) == "Yahoo"
        assert get_engine_display_name(SearchEngine.DUCKDUCKGO) == "DuckDuckGo"

    def test_format_results_for_display(self):
        """测试格式化搜索结果。"""
        results = [
            SearchResult(
                title="测试标题",
                href="https://example.com",
                abstract="测试摘要",
            )
        ]

        formatted = format_results_for_display(results, "Bing")

        assert "Bing 搜索结果" in formatted
        assert "测试标题" in formatted
        assert "https://example.com" in formatted
        assert "测试摘要" in formatted

    def test_format_results_empty(self):
        """测试格式化空结果。"""
        formatted = format_results_for_display([], "Google")
        assert "未找到 Google 搜索结果" in formatted


class TestServer:
    """服务器测试。"""

    def test_tools_definition(self):
        """测试工具定义。"""
        from src.server import TOOLS

        assert len(TOOLS) == 2

        # 检查 search 工具
        search_tool = next(t for t in TOOLS if t.name == "search")
        assert search_tool.description is not None
        assert "query" in search_tool.inputSchema["properties"]

        # 检查 list_engines 工具
        list_tool = next(t for t in TOOLS if t.name == "list_engines")
        assert list_tool.description is not None

    def test_get_search_engine_valid(self):
        """测试获取有效的搜索引擎。"""
        from src.server import get_search_engine

        google = get_search_engine("google")
        assert google is not None

        bing = get_search_engine("bing")
        assert bing is not None

        yahoo = get_search_engine("yahoo")
        assert yahoo is not None

        duckduckgo = get_search_engine("duckduckgo")
        assert duckduckgo is not None

    def test_get_search_engine_invalid(self):
        """测试获取无效的搜索引擎。"""
        from src.server import get_search_engine

        with pytest.raises(ValueError) as exc_info:
            get_search_engine("invalid_engine")

        assert "不支持的搜索引擎" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
