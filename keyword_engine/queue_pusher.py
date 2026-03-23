"""Notion 키워드 큐 적재 — 기존 키워드 큐 DB에 연결 + 블로그 기발행 글 중복 체크"""
import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# .env 로드
_env = Path(__file__).parent.parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
KEYWORD_DB_ID = "d6bb5b753f1b4963891de02427411276"

# 블로그별 RSS URL
BLOG_RSS = {
    "goodisak":  "https://goodisak.tistory.com/rss",
    "nolja100":  "https://nolja100.tistory.com/rss",
    "salim1su":  "https://rss.blog.naver.com/salim1su.xml",
    "baremi542": "https://baremi542.com/feed",
}


def _fetch_published_titles(blog_id: str) -> list:
    """블로그 RSS에서 기발행 글 제목 수집"""
    rss_url = BLOG_RSS.get(blog_id)
    if not rss_url:
        return []
    try:
        req = urllib.request.Request(
            rss_url,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        content = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", errors="ignore")
        root = ET.fromstring(content)
        titles = []
        for item in root.iter("item"):
            t = item.find("title")
            if t is not None and t.text:
                titles.append(t.text.strip())
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            t = entry.find("{http://www.w3.org/2005/Atom}title")
            if t is not None and t.text:
                titles.append(t.text.strip())
        return titles
    except Exception:
        return []


def _normalize(text: str) -> str:
    """비교용 정규화 — 공백·특수문자 제거, 소문자"""
    return re.sub(r"[^\w가-힣]", "", text).lower()


def _is_duplicate(keyword: str, published_titles: list) -> bool:
    """
    키워드가 기발행 글과 중복인지 판단.
    - 키워드가 기존 제목에 포함되거나
    - 기존 제목이 키워드를 포함하면 중복
    """
    kw_norm = _normalize(keyword)
    for title in published_titles:
        title_norm = _normalize(title)
        if kw_norm in title_norm or title_norm in kw_norm:
            return True
    return False


def _headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _existing_keywords() -> set:
    """Notion DB에 이미 있는 키워드 목록 조회"""
    existing = set()
    start_cursor = None
    while True:
        body = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor
        req = urllib.request.Request(
            f"{NOTION_API}/databases/{KEYWORD_DB_ID}/query",
            data=json.dumps(body).encode(),
            headers=_headers(),
            method="POST",
        )
        try:
            data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        except Exception:
            break
        for page in data.get("results", []):
            for prop_name in ["키워드", "Name", "name"]:
                prop = page["properties"].get(prop_name, {})
                if prop.get("type") == "title":
                    texts = prop.get("title", [])
                    if texts:
                        existing.add(texts[0].get("plain_text", ""))
                    break
        if not data.get("has_more"):
            break
        start_cursor = data.get("next_cursor")
    return existing


def push(keywords: list, blog_id: str, on_log=None) -> int:
    """
    키워드를 Notion 키워드 큐에 적재.
    - Notion 큐 중복 체크 (같은 키워드 이미 있으면 스킵)
    - 블로그 기발행 글 중복 체크 (이미 쓴 주제면 스킵)

    Args:
        keywords: [{"keyword", "score", "volume"}, ...]
        blog_id: 블로그 ID (예: "goodisak")
    """
    existing = _existing_keywords()
    if on_log:
        on_log(f"[queue] Notion 큐 기존 {len(existing)}개 확인")

    published = _fetch_published_titles(blog_id)
    if on_log:
        on_log(f"[queue] {blog_id} 기발행 글 {len(published)}개 로드")

    saved = 0
    for item in keywords:
        kw = item["keyword"]

        # 1) Notion 큐 중복
        if kw in existing:
            if on_log:
                on_log(f"[queue] 큐 중복 스킵: {kw}")
            continue

        # 2) 기발행 글 중복
        if published and _is_duplicate(kw, published):
            if on_log:
                on_log(f"[queue] 발행 중복 스킵: {kw}")
            continue

        volume = int(item.get("volume", 0))
        score = int(item.get("score", 0))
        ktype = "트렌딩" if volume >= 5000 else "에버그린"

        body = {
            "parent": {"database_id": KEYWORD_DB_ID},
            "properties": {
                "키워드": {"title": [{"text": {"content": kw}}]},
                "블로그": {"select": {"name": blog_id}},
                "상태": {"select": {"name": "대기"}},
                "검색량": {"number": volume},
                "유형": {"select": {"name": ktype}},
                "수집일": {"date": {"start": datetime.now().strftime("%Y-%m-%d")}},
                "메모": {"rich_text": [{"text": {"content": f"천하무적엔진 점수:{score:,}"}}]},
            },
        }
        req = urllib.request.Request(
            f"{NOTION_API}/pages",
            data=json.dumps(body).encode(),
            headers=_headers(),
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=10)
            saved += 1
            if on_log:
                on_log(f"[queue] 저장: {kw} (점수:{score:,}  검색량:{volume:,})")
        except Exception as e:
            if on_log:
                on_log(f"[queue] 실패: {kw} — {e}")
        time.sleep(0.3)

    return saved
