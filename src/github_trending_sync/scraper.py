"""GitHub Trending 采集（Playwright 真实浏览器）。

使用 headless Chromium 打开 https://github.com/trending?since=daily，
按页面展示顺序读取仓库卡片，提取结构化字段。数据仅来源于该页面当次展示结果。
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from .errors import ScrapeError
from .normalize import (
    absolute_url,
    normalize_description,
    normalize_language,
    parse_count,
)


@dataclass
class Repo:
    rank: int
    repo_full_name: str
    repo_url: str
    description: str
    language: str
    stars: int | None
    forks: int | None
    stars_today: int | None

    def to_dict(self) -> dict:
        return asdict(self)


def _extract_repo(article, rank: int) -> Repo:
    """从单个 article.Box-row 卡片提取字段。"""
    # 仓库全名与链接：h2 内的 a[href]，如 /owner/repo
    name_link = article.query_selector("h2 a")
    href = name_link.get_attribute("href") if name_link else ""
    repo_full_name = href.strip("/")
    if not repo_full_name or "/" not in repo_full_name:
        raise ScrapeError(
            f"第 {rank} 条仓库链接解析失败，href={href!r}",
            "GitHub Trending 页面结构可能已变化，请检查 h2 a 选择器。",
        )
    repo_url = absolute_url(href)

    # 简介：卡片直接子级 p 标签（可能缺失）
    desc_el = article.query_selector(":scope > p")
    description = normalize_description(desc_el.inner_text() if desc_el else "")

    # 主语言
    lang_el = article.query_selector('span[itemprop="programmingLanguage"]')
    language = normalize_language(lang_el.inner_text() if lang_el else "")

    # 总 Star / Fork
    stars_el = article.query_selector('a[href$="/stargazers"]')
    forks_el = article.query_selector('a[href$="/forks"]')
    stars = parse_count(stars_el.inner_text() if stars_el else "")
    forks = parse_count(forks_el.inner_text() if forks_el else "")

    # 当日新增 Star（"1,005 stars today"）
    today_el = article.query_selector("span.float-sm-right")
    stars_today = parse_count(today_el.inner_text() if today_el else "")

    return Repo(
        rank=rank,
        repo_full_name=repo_full_name,
        repo_url=repo_url,
        description=description,
        language=language,
        stars=stars,
        forks=forks,
        stars_today=stars_today,
    )


def scrape_trending(url: str, top_n: int, *, ignore_https_errors: bool = False,
                    timeout_ms: int = 60_000) -> list[dict]:
    """采集当日 Top N 项目，返回字典列表（按页面顺序）。"""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        raise ScrapeError(
            "未安装 Playwright 或浏览器未就绪",
            "请执行：pip install -r requirements.txt && playwright install chromium",
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(ignore_https_errors=ignore_https_errors)
            page = context.new_page()

            # 屏蔽非关键静态资源，显著加快加载、降低超时概率；
            # 仓库列表数据来自主文档（SSR），不依赖图片/字体/样式表。
            def _block_static(route):
                if route.request.resource_type in ("image", "font", "media", "stylesheet"):
                    route.abort()
                else:
                    route.continue_()

            page.route("**/*", _block_static)

            try:
                page.goto(url, wait_until="commit", timeout=timeout_ms)
            except Exception as exc:
                raise ScrapeError(
                    f"无法访问 GitHub Trending 页面：{url}",
                    "请确认网络可达 github.com；如处于受限网络，可配置代理或设置 "
                    "IGNORE_HTTPS_ERRORS=true（仅用于证书异常环境）。",
                ) from exc

            try:
                page.wait_for_selector(
                    "article.Box-row", state="attached", timeout=timeout_ms
                )
            except Exception as exc:
                raise ScrapeError(
                    "页面已打开但未发现任何仓库卡片（可能无记录或结构变化）",
                    "请确认页面确有 Trending 数据；若为空榜请稍后重试。",
                ) from exc

            articles = page.query_selector_all("article.Box-row")
            results: list[dict] = []
            for idx, article in enumerate(articles[:top_n], start=1):
                results.append(_extract_repo(article, idx).to_dict())

            if not results:
                raise ScrapeError(
                    "未采集到任何记录",
                    "Trending 页面可能为空，请稍后重试。",
                )
            return results
        finally:
            browser.close()
