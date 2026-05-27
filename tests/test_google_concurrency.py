"""Google 搜索 profile 并发保护测试。"""

import asyncio

import pytest

from src.engines.google import GoogleSearchEngine


@pytest.mark.asyncio
async def test_google_profile_searches_are_serialized(monkeypatch):
    """并发 Google 搜索必须串行进入 persistent profile 浏览器段。

    GoogleSearchEngine 使用固定 user_data_dir 保存 CAPTCHA cookie。两个
    launch_persistent_context 并发占用同一个 profile 会导致 Chrome SingletonLock /
    database locked，并最终表现为 Playwright TargetClosedError。
    """

    active = 0
    max_active = 0
    calls = []

    async def fake_init_browser(self):
        return None

    async def fake_search_with_visible_browser(self, url):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        calls.append(("start", url))
        await asyncio.sleep(0.01)
        calls.append(("end", url))
        active -= 1
        return [{"title": url, "href": "https://example.com", "abstract": ""}]

    monkeypatch.setattr(GoogleSearchEngine, "_init_browser", fake_init_browser)
    monkeypatch.setattr(
        GoogleSearchEngine,
        "_search_with_visible_browser",
        fake_search_with_visible_browser,
    )

    # 保证测试不受同一 Python 进程中其它测试创建的 lock 影响。
    GoogleSearchEngine._profile_lock = None
    GoogleSearchEngine._profile_lock_loop = None

    engine_a = GoogleSearchEngine()
    engine_b = GoogleSearchEngine()

    results = await asyncio.gather(
        engine_a._fetch_and_extract("https://www.google.com/search?q=a"),
        engine_b._fetch_and_extract("https://www.google.com/search?q=b"),
    )

    assert max_active == 1
    assert len(results) == 2
    assert [event for event, _ in calls] == ["start", "end", "start", "end"]
