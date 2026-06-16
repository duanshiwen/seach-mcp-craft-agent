"""网页内容获取模块 - 抓取 URL 并提取为 AI 友好的 Markdown 格式。"""

import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx
import trafilatura

logger = logging.getLogger(__name__)

# 请求头，模拟正常浏览器
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}

# 默认超时设置（毫秒 / 秒）
DEFAULT_TIMEOUT_MS = 720_000
FETCH_TIMEOUT = 720

# 最大内容长度（字符）
MAX_CONTENT_LENGTH = 100_000

# 常见的非 HTML 内容类型
NON_HTML_TYPES = [
    "application/pdf",
    "application/zip",
    "application/octet-stream",
    "image/",
    "video/",
    "audio/",
]

# JS-only / SPA 常见提示与空壳特征
JS_REQUIRED_PATTERNS = [
    r"doesn[’']?t work properly without javascript",
    r"please enable javascript",
    r"enable javascript to continue",
    r"requires javascript",
    r"javascript is disabled",
    r"请启用\s*javascript",
    r"需要\s*javascript",
]

VALID_RENDER_MODES = {"auto", "http", "js"}
VALID_WAIT_UNTIL = {"load", "domcontentloaded", "networkidle", "commit"}


def _validate_url(url: str) -> tuple[bool, str | None]:
    """验证 URL 格式。"""
    if not url or not url.strip():
        return False, "URL 不能为空"

    parsed = urlparse(url.strip())
    if not parsed.scheme:
        return False, f"URL 缺少协议前缀，请使用完整的 URL（如 https://{url}）"

    if parsed.scheme not in ("http", "https"):
        return False, f"不支持的协议: {parsed.scheme}，仅支持 http 和 https"

    if not parsed.netloc:
        return False, "URL 格式无效：缺少域名"

    return True, None


def _is_html_content(content_type: str) -> bool:
    """检查 Content-Type 是否为 HTML 类型。"""
    ct_lower = content_type.lower()
    for non_html in NON_HTML_TYPES:
        if non_html in ct_lower:
            return False
    return True


def _add_metadata(
    text: str,
    url: str,
    title: str | None = None,
    render_mode_used: str | None = None,
) -> str:
    """在内容前添加元数据头。"""
    parts = []
    if title:
        parts.append(f"# {title}")
    parts.append(f"**Source:** {url}")
    if render_mode_used:
        parts.append(f"**Render mode:** {render_mode_used}")
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append(text)
    return "\n".join(parts)


def _extract_title(html: str) -> str | None:
    """从 HTML 中提取标题。"""
    try:
        from selectolax.parser import HTMLParser

        tree = HTMLParser(html)
        title_node = tree.css_first("title")
        if title_node:
            title = title_node.text(strip=True)
            return title or None
    except Exception:
        pass
    return None


def _clean_html_for_extraction(html: str) -> str:
    """清理不应进入正文提取的标签，避免脚本模板导致重复内容。"""
    try:
        from selectolax.parser import HTMLParser

        tree = HTMLParser(html)
        for node in tree.css("script, style, noscript, template"):
            node.decompose()
        return tree.html
    except Exception:
        return html


def _extract_content(html: str, url: str, extract_mode: str) -> str | None:
    """使用 trafilatura 从 HTML 提取正文。"""
    cleaned_html = _clean_html_for_extraction(html)

    if extract_mode == "text":
        return trafilatura.extract(
            cleaned_html,
            url=url,
            output_format="txt",
            include_links=False,
            include_tables=True,
            include_comments=False,
            no_fallback=False,
        )

    return trafilatura.extract(
        cleaned_html,
        url=url,
        output_format="markdown",
        include_links=True,
        include_tables=True,
        include_comments=False,
        no_fallback=False,
    )


def _looks_like_js_required(extracted: str | None, html: str) -> bool:
    """判断页面是否可能需要 JS 渲染。

    Args:
        extracted: trafilatura 已提取的正文
        html: 原始或渲染前 HTML
    """
    combined = "\n".join([extracted or "", html[:5000] or ""]).lower()

    for pattern in JS_REQUIRED_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            return True

    # 典型 SPA 空壳：有 root/app 容器，但正文极短
    text_len = len((extracted or "").strip())
    html_lower = html.lower()
    has_spa_root = any(
        marker in html_lower
        for marker in (
            'id="root"',
            "id='root'",
            'id="app"',
            "id='app'",
            "data-reactroot",
            "__next_data__",
            "window.__nuxt__",
        )
    )
    has_many_scripts = html_lower.count("<script") >= 5

    return text_len < 200 and (has_spa_root or has_many_scripts)


async def _fetch_html_http(url: str, timeout_ms: int) -> tuple[str, str]:
    """使用 HTTP 请求获取 HTML。返回 (html, final_url)。"""
    try:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=timeout_ms / 1000,
            verify=False,  # 部分网站证书有问题
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.TimeoutException:
        raise RuntimeError(f"获取超时（{timeout_ms}ms）: {url}")
    except httpx.TooManyRedirects:
        raise RuntimeError(f"重定向次数过多: {url}")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"HTTP 错误 {e.response.status_code}: {url}")
    except httpx.RequestError as e:
        raise RuntimeError(f"请求失败: {str(e)}")

    content_type = response.headers.get("content-type", "")
    if not _is_html_content(content_type):
        raise RuntimeError(
            f"不支持的内容类型 '{content_type}'，仅支持 HTML 页面。URL: {url}"
        )

    return response.text, str(response.url)


async def _fetch_html_js(
    url: str,
    wait_until: str,
    timeout_ms: int,
) -> tuple[str, str]:
    """使用 Playwright 渲染页面并返回渲染后的 HTML。"""
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        raise RuntimeError(
            "Playwright 未安装，无法使用 JS 渲染模式。"
            "请安装 playwright 并运行 `python -m playwright install chromium`。"
        ) from e

    logger.info(
        f"启动 Playwright JS 渲染: url={url}, wait_until={wait_until}, timeout={timeout_ms}ms"
    )

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-dev-shm-usage",
                ],
            )
            try:
                page = await browser.new_page(
                    user_agent=DEFAULT_HEADERS["User-Agent"],
                    locale="zh-CN",
                    viewport={"width": 1366, "height": 900},
                )
                try:
                    await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                except Exception:
                    # Some pages (notably Apple Developer Documentation) keep analytics
                    # or streaming requests open, so networkidle can time out even after
                    # the document and app data are ready.
                    if wait_until != "domcontentloaded":
                        logger.info(
                            "JS render failed with wait_until=%s; retrying domcontentloaded",
                            wait_until,
                        )
                        await page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=timeout_ms,
                        )
                    else:
                        raise

                # 给客户端框架额外一点时间完成 hydration / 数据请求
                await page.wait_for_timeout(3000)

                html = await page.content()
                final_url = page.url
                return html, final_url
            finally:
                await browser.close()
    except Exception as e:
        raise RuntimeError(f"JS 渲染失败: {str(e)}")


def _apple_doc_json_url(page_url: str) -> str | None:
    """Map Apple Developer Documentation/HIG page URLs to their source JSON URL.

    Apple's documentation shell often ships little useful body text in the
    initial HTML. The authoritative page content is loaded from
    /tutorials/data/<path>.json by Apple's own frontend. Fetching this JSON is
    still an Apple-origin source and avoids depending on Playwright rendering.
    """
    parsed = urlparse(page_url)
    if parsed.netloc.lower() != "developer.apple.com":
        return None

    path = parsed.path.strip("/")
    if not path:
        return None

    # Known Apple Documentation shell paths that are backed by tutorials/data.
    supported_prefixes = (
        "design/human-interface-guidelines",
        "documentation/",
        "tutorials/",
    )
    if not path.startswith(supported_prefixes):
        return None

    if path.endswith(".json"):
        return page_url

    return f"{parsed.scheme}://{parsed.netloc}/tutorials/data/{path}.json"


async def _fetch_apple_doc_json(page_url: str, timeout_ms: int) -> tuple[dict[str, Any], str] | None:
    """Fetch Apple documentation source JSON if this URL has one."""
    json_url = _apple_doc_json_url(page_url)
    if not json_url:
        return None

    try:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=timeout_ms / 1000,
            verify=False,
        ) as client:
            response = await client.get(json_url)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json(), str(response.url)
    except Exception as e:
        logger.info("Apple documentation JSON fallback unavailable for %s: %s", page_url, e)
        return None


def _apple_ref_label(identifier: str, references: dict[str, Any]) -> tuple[str, str | None]:
    ref = references.get(identifier, {}) if isinstance(references, dict) else {}
    title = ref.get("title") or ref.get("name") or identifier.rsplit("/", 1)[-1]
    url = ref.get("url")
    if url and url.startswith("/"):
        url = "https://developer.apple.com" + url
    elif identifier.startswith("http"):
        url = identifier
    elif isinstance(url, str) and url:
        url = "https://developer.apple.com/" + url.lstrip("/")
    return str(title), url


def _apple_asset_url(identifier: str, references: dict[str, Any]) -> str | None:
    ref = references.get(identifier, {}) if isinstance(references, dict) else {}
    variants = ref.get("variants") if isinstance(ref, dict) else None
    if isinstance(variants, list) and variants:
        url = variants[0].get("url")
        if isinstance(url, str):
            return url
    return None


def _render_apple_inline(items: list[dict[str, Any]] | None, references: dict[str, Any]) -> str:
    if not items:
        return ""

    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        typ = item.get("type")
        if typ == "text":
            parts.append(str(item.get("text", "")))
        elif typ == "strong":
            parts.append("**" + _render_apple_inline(item.get("inlineContent"), references).strip() + "**")
        elif typ == "emphasis":
            parts.append("*" + _render_apple_inline(item.get("inlineContent"), references).strip() + "*")
        elif typ == "codeVoice":
            parts.append("`" + str(item.get("code", "")) + "`")
        elif typ == "reference":
            label = item.get("overridingTitle")
            if not label:
                label = _render_apple_inline(item.get("overridingTitleInlineContent"), references).strip()
            title, url = _apple_ref_label(str(item.get("identifier", "")), references)
            label = label or title
            parts.append(f"[{label}]({url})" if url else str(label))
        elif typ in ("image", "video"):
            ident = str(item.get("identifier", ""))
            ref = references.get(ident, {}) if isinstance(references, dict) else {}
            alt = ref.get("alt") or ident
            asset_url = _apple_asset_url(ident, references)
            # Avoid inline image Markdown in MCP text responses. Large image alt text
            # and renderer-side previews can make Apple documentation responses slow
            # or fragile; keep the Apple-origin asset URL as a normal link instead.
            if asset_url:
                parts.append(f"[Image: {alt}]({asset_url})")
            elif ident:
                parts.append(f"[{alt}]")
        else:
            text = item.get("text") or item.get("code")
            if text:
                parts.append(str(text))
            elif item.get("inlineContent"):
                parts.append(_render_apple_inline(item.get("inlineContent"), references))
    return "".join(parts)


def _render_apple_blocks(blocks: list[dict[str, Any]] | None, references: dict[str, Any]) -> list[str]:
    rendered: list[str] = []
    if not blocks:
        return rendered

    for block in blocks:
        if not isinstance(block, dict):
            continue
        typ = block.get("type")

        if typ == "paragraph":
            text = _render_apple_inline(block.get("inlineContent"), references).strip()
            if text:
                rendered.append(text)
        elif typ == "heading":
            level = int(block.get("level") or 2)
            level = max(2, min(level, 6))
            text = str(block.get("text", "")).strip()
            if text:
                rendered.append("#" * level + " " + text)
        elif typ in ("unorderedList", "orderedList"):
            lines: list[str] = []
            for idx, item in enumerate(block.get("items") or [], start=1):
                item_blocks = _render_apple_blocks(item.get("content") or [], references)
                item_text = " ".join(x.replace("\n", " ") for x in item_blocks).strip()
                if item_text:
                    prefix = f"{idx}." if typ == "orderedList" else "-"
                    lines.append(f"{prefix} {item_text}")
            if lines:
                rendered.append("\n".join(lines))
        elif typ == "aside":
            name = block.get("name") or block.get("style") or "Note"
            body = _render_apple_blocks(block.get("content") or [], references)
            if body:
                rendered.append(f"> **{name}:** " + "\n> ".join("\n\n".join(body).splitlines()))
        elif typ == "row":
            cols: list[str] = []
            for col in block.get("columns") or []:
                cols.extend(_render_apple_blocks(col.get("content") or [], references))
            if cols:
                rendered.append("\n\n".join(cols))
        elif typ == "table":
            rows = block.get("rows") or []
            md_rows: list[list[str]] = []
            for row in rows:
                cells: list[str] = []
                for cell in row:
                    cell_blocks: list[dict[str, Any]] = []
                    if isinstance(cell, list):
                        for part in cell:
                            if isinstance(part, dict):
                                cell_blocks.append(part)
                    elif isinstance(cell, dict):
                        cell_blocks.append(cell)
                    cell_text = " ".join(_render_apple_blocks(cell_blocks, references)).replace("|", "\\|").strip()
                    cells.append(cell_text)
                if cells:
                    md_rows.append(cells)
            if md_rows:
                width = max(len(r) for r in md_rows)
                md_rows = [r + [""] * (width - len(r)) for r in md_rows]
                header = md_rows[0]
                table_lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * width) + " |"]
                for row in md_rows[1:]:
                    table_lines.append("| " + " | ".join(row) + " |")
                rendered.append("\n".join(table_lines))
        elif typ == "links":
            lines: list[str] = []
            for ident in block.get("items") or []:
                title, url = _apple_ref_label(str(ident), references)
                lines.append(f"- [{title}]({url})" if url else f"- {title}")
            if lines:
                rendered.append("\n".join(lines))
        else:
            nested = block.get("content")
            if isinstance(nested, list):
                rendered.extend(_render_apple_blocks(nested, references))
            elif block.get("inlineContent"):
                text = _render_apple_inline(block.get("inlineContent"), references).strip()
                if text:
                    rendered.append(text)

    return rendered


def _render_apple_doc_markdown(data: dict[str, Any], source_url: str, extract_mode: str) -> str | None:
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    references = data.get("references") if isinstance(data.get("references"), dict) else {}
    title = metadata.get("title") or data.get("title")
    abstract = _render_apple_inline(data.get("abstract"), references).strip()

    sections: list[str] = []
    if title:
        sections.append(f"# {title}")
    if abstract:
        sections.append(abstract)

    for section in data.get("primaryContentSections") or []:
        if not isinstance(section, dict):
            continue
        blocks = _render_apple_blocks(section.get("content") or [], references)
        sections.extend(blocks)

    notices = data.get("legalNotices") if isinstance(data.get("legalNotices"), dict) else {}
    copyright_text = notices.get("copyright")
    if isinstance(copyright_text, str) and copyright_text:
        copyright_text = re.sub(r"<[^>]+>", "", copyright_text)
        sections.append(copyright_text)

    markdown = "\n\n".join(x.strip() for x in sections if x and x.strip())
    if not markdown.strip():
        return None
    # Keep Apple documentation responses conservative for MCP transport/UI.
    # The source remains Apple's own JSON; the text is flattened to avoid rich
    # Markdown edge cases in clients while still giving immediately usable body text.
    rendered = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", markdown)
    rendered = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", rendered)
    rendered = rendered.replace("**", "").replace("*", "").replace("`", "")
    rendered = _postprocess_content(rendered)
    apple_limit = 2_000
    if len(rendered) > apple_limit:
        rendered = rendered[:apple_limit] + "\n\n---\n\n[Truncated: Apple document is longer. Source above is the original Apple JSON URL.]"
    return _add_metadata(rendered, source_url, None, "apple-json")


def _dedupe_markdown_blocks(text: str) -> str:
    """去除完全重复的 Markdown 段落块。

    trafilatura 在少数 JS 渲染/短页面 fallback 场景下，可能会把 DOM 正文与脚本模板
    中的相同文本都提取出来。这里仅删除“完全相同”的段落块，避免影响正常内容。
    """
    blocks = re.split(r"\n{2,}", text.strip())
    seen: set[str] = set()
    kept: list[str] = []

    for block in blocks:
        normalized = re.sub(r"\s+", " ", block).strip().lower()
        # 很短的块（如分隔线、单字标题）不做全局去重，避免误删结构信息
        if len(normalized) < 30:
            kept.append(block)
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        kept.append(block)

    return "\n\n".join(kept).strip()


def _postprocess_content(extracted: str) -> str:
    """后处理提取结果：去重并截断超长内容。"""
    processed = _dedupe_markdown_blocks(extracted)
    if len(processed) > MAX_CONTENT_LENGTH:
        return processed[:MAX_CONTENT_LENGTH] + "\n\n---\n\n⚠️ 内容过长，已截断。"
    return processed


async def fetch_url(
    url: str,
    extract_mode: str = "markdown",
    render_mode: str = "auto",
    wait_until: str = "networkidle",
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> str:
    """获取指定 URL 的网页内容并转换为 Markdown 或纯文本格式。

    Args:
        url: 要获取的网页 URL
        extract_mode: 输出格式 - "markdown"（默认）或 "text"（纯文本）
        render_mode: 渲染模式 - "auto"（默认）、"http"、"js"
        wait_until: Playwright 等待策略 - load/domcontentloaded/networkidle/commit
        timeout_ms: 超时时间（毫秒）

    Returns:
        提取的 Markdown 或纯文本内容

    Raises:
        ValueError: URL 无效或参数错误
        RuntimeError: 获取或解析失败
    """
    is_valid, error_msg = _validate_url(url)
    if not is_valid:
        raise ValueError(error_msg)

    if extract_mode not in ("markdown", "text"):
        raise ValueError(f"不支持的提取模式: {extract_mode}，可选: markdown, text")

    if render_mode not in VALID_RENDER_MODES:
        raise ValueError(f"不支持的渲染模式: {render_mode}，可选: auto, http, js")

    if wait_until not in VALID_WAIT_UNTIL:
        raise ValueError(
            f"不支持的等待策略: {wait_until}，可选: load, domcontentloaded, networkidle, commit"
        )

    # 限制超时范围，避免长时间挂起
    timeout_ms = max(3_000, min(int(timeout_ms), 720_000))
    url = url.strip()

    logger.info(
        f"开始获取 URL: {url}, extract_mode={extract_mode}, "
        f"render_mode={render_mode}, wait_until={wait_until}, timeout_ms={timeout_ms}"
    )

    # Apple Developer Documentation pages (including HIG) are JS shells whose
    # authoritative article body is loaded from Apple-origin JSON. Prefer that
    # source directly so HIG pages work even when Playwright is unavailable or
    # networkidle never settles.
    apple_payload = await _fetch_apple_doc_json(url, timeout_ms)
    if apple_payload is not None:
        data, json_url = apple_payload
        apple_result = _render_apple_doc_markdown(data, json_url, extract_mode)
        if apple_result:
            return apple_result

    html = ""
    final_url = url
    render_mode_used = "http"

    # 1. HTTP-only 或 auto 的快速路径
    if render_mode in ("http", "auto"):
        html, final_url = await _fetch_html_http(url, timeout_ms)
        logger.info(f"HTTP 获取到 HTML 内容，长度: {len(html)} 字符")

        extracted = _extract_content(html, final_url, extract_mode)
        if render_mode == "http" or not _looks_like_js_required(extracted, html):
            if not extracted:
                raise RuntimeError(
                    "无法从该页面提取正文内容。可能原因：\n"
                    "- 页面需要 JavaScript 渲染（可尝试 render_mode=js 或 auto）\n"
                    "- 页面需要登录或有反爬机制\n"
                    "- 页面内容为空或为纯图片/视频\n"
                    f"URL: {url}"
                )
            title = _extract_title(html)
            result = _postprocess_content(extracted)
            return _add_metadata(result, final_url, title, render_mode_used)

        logger.info("检测到页面可能需要 JS 渲染，自动切换到 Playwright")

    # 2. JS 渲染路径（force js 或 auto fallback）
    render_mode_used = "js"
    html, final_url = await _fetch_html_js(url, wait_until, timeout_ms)
    logger.info(f"JS 渲染后 HTML 长度: {len(html)} 字符")

    try:
        extracted = _extract_content(html, final_url, extract_mode)
    except Exception as e:
        logger.error(f"trafilatura 提取失败: {e}")
        raise RuntimeError(f"内容提取失败: {str(e)}")

    if not extracted:
        raise RuntimeError(
            "JS 渲染后仍无法提取正文内容。可能原因：\n"
            "- 页面需要登录或 cookies\n"
            "- 网站阻止 headless 浏览器或存在强反爬\n"
            "- 页面内容为空、纯图片/视频，或正文结构特殊\n"
            f"URL: {url}"
        )

    title = _extract_title(html)
    result = _postprocess_content(extracted)
    logger.info(f"提取完成，输出长度: {len(result)} 字符，render_mode_used={render_mode_used}")

    return _add_metadata(result, final_url, title, render_mode_used)
