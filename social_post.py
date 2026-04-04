"""RSS → Facebook Pages + Threads 자동 포스팅
- goodisak/nolja100 → 이거알아요 Facebook Page + Threads
- salim1su → 퇴근후살림 Facebook Page + Threads
- 형식: 이미지 + 제목 + 후킹글 / 댓글에 블로그 링크
"""
import os
import re
import json
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# ── 설정 ──────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "logs" / "social_post_state.json"

def _load_env():
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

_load_env()

FB_USER_TOKEN   = os.environ.get("FB_PAGE_ACCESS_TOKEN", "")
THREADS_TOKEN   = os.environ.get("THREADS_ACCESS_TOKEN", "")
THREADS_USER_ID = "26204591355835901"

BLOGS = {
    "goodisak": {
        "rss": "https://goodisak.tistory.com/rss",
        "fb_page_id": "981891965017107",   # 이거알아요
        "domain": "welfare.baremi542.com",
        "rss_domain": "goodisak.tistory.com",
    },
    "nolja100": {
        "rss": "https://nolja100.tistory.com/rss",
        "fb_page_id": "981891965017107",   # 이거알아요
        "domain": "issue.baremi542.com",
        "rss_domain": "nolja100.tistory.com",
    },
    "salim1su": {
        "rss": "https://rss.blog.naver.com/salim1su.xml",
        "fb_page_id": "955279141010789",   # 퇴근후살림
        "domain": None,                    # 네이버 링크 그대로 사용
        "rss_domain": None,
    },
    "triplog": {
        "rss": "https://app.baremi542.com/feed",
        "fb_page_id": "981891965017107",   # 이거알아요
        "domain": "app.baremi542.com",
        "rss_domain": None,
    },
    "baremi542": {
        "rss": "https://baremi542.com/feed",
        "fb_page_id": "981891965017107",   # 이거알아요
        "domain": "baremi542.com",
        "rss_domain": None,
    },
}

# 블로그 간 포스팅 최소 간격 (초)
POST_INTERVAL_BETWEEN_BLOGS = 1800   # 30분 간격
# 같은 블로그 재포스팅 최소 간격 (초)
POST_INTERVAL_SAME_BLOG = 14400      # 4시간


def _rewrite_link(link: str, cfg: dict) -> str:
    """RSS 링크의 tistory 도메인을 실제 서비스 도메인으로 교체."""
    rss_domain = cfg.get("rss_domain")
    real_domain = cfg.get("domain")
    if rss_domain and real_domain and rss_domain in link:
        return link.replace(rss_domain, real_domain)
    return link

# ── 상태 파일 ────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ── API 헬퍼 ─────────────────────────────────────────────────────────────────

def _api(url: str, data: dict | None = None) -> dict:
    try:
        if data:
            body = urllib.parse.urlencode(data).encode()
            req = urllib.request.Request(url, data=body, method="POST")
        else:
            req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "body": e.read().decode()}
    except Exception as e:
        return {"error": str(e)}


# ── Facebook 페이지 토큰 ─────────────────────────────────────────────────────

_PAGE_TOKENS: dict[str, str] = {}

def _get_page_token(page_id: str) -> str:
    if page_id in _PAGE_TOKENS:
        return _PAGE_TOKENS[page_id]
    resp = _api(f"https://graph.facebook.com/v19.0/me/accounts?access_token={FB_USER_TOKEN}")
    for page in resp.get("data", []):
        _PAGE_TOKENS[page["id"]] = page["access_token"]
    return _PAGE_TOKENS.get(page_id, "")


# ── RSS 파싱 (이미지 + 후킹글 포함) ─────────────────────────────────────────

def _strip_html(html: str) -> str:
    """HTML 태그 제거 후 순수 텍스트 반환."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&[a-z]+;", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_images(item_elem, max_images: int = 2) -> list[str]:
    """RSS 항목에서 이미지 URL 최대 max_images개 추출."""
    urls: list[str] = []

    # 1. media:content (여러 개)
    ns_media = "http://search.yahoo.com/mrss/"
    for mc in item_elem.findall(f"{{{ns_media}}}content"):
        url = mc.get("url", "")
        if url and url not in urls:
            urls.append(url)
        if len(urls) >= max_images:
            return urls

    # 2. enclosure
    enc = item_elem.find("enclosure")
    if enc is not None and "image" in enc.get("type", ""):
        url = enc.get("url", "")
        if url and url not in urls:
            urls.append(url)
    if len(urls) >= max_images:
        return urls

    # 3. description/content:encoded 내 <img> 태그 전체 추출
    desc = (
        item_elem.findtext("description", "")
        or item_elem.findtext("{http://purl.org/rss/1.0/modules/content/}encoded", "")
        or item_elem.findtext("content:encoded", "")
    )
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', desc, re.IGNORECASE):
        url = m.group(1)
        if url and url not in urls:
            urls.append(url)
        if len(urls) >= max_images:
            break

    return urls


def _extract_hook(item_elem) -> str:
    """RSS 본문에서 SNS 후킹글 생성 (외부유입 최적화).

    형식:
    - 첫 줄: 궁금증 유발 질문 또는 핵심 한 문장
    - 중간: 핵심 내용 2~3줄 (독자가 얻을 것)
    - 마지막: 댓글 링크 유도 CTA
    """
    desc = (
        item_elem.findtext("description", "")
        or item_elem.findtext("{http://purl.org/rss/1.0/modules/content/}encoded", "")
    )
    text = _strip_html(desc)

    # 의미 있는 문장만 추출 (15자 이상)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?。])\s+", text) if len(s.strip()) >= 15]

    if not sentences:
        body = text[:200].rsplit(" ", 1)[0] + "..." if len(text) > 200 else text
    else:
        # 첫 3문장으로 티저 구성
        body = "\n".join(sentences[:3])
        if len(body) > 250:
            body = body[:250].rsplit(" ", 1)[0] + "..."

    return body


def _build_post_text(title: str, hook: str, blog_id: str = "") -> str:
    """SNS 포스트 본문 구성 (제목 + 후킹 요약 + CTA)."""
    # 블로그별 대표 이모지
    emoji_map = {
        "nolja100": "✈️",
        "triplog": "🗺️",
        "salim1su": "🏠",
        "goodisak": "💡",
        "baremi542": "📋",
    }
    emoji = emoji_map.get(blog_id, "📌")

    return (
        f"{emoji} {title}\n\n"
        f"{hook}\n\n"
        f"👇 전체 내용은 댓글 링크에서 확인하세요"
    )


def _fetch_rss(url: str) -> list[dict]:
    """RSS 최신 10개 항목 반환 (이미지·후킹글 포함)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            content = r.read()
        root = ET.fromstring(content)
        items = []
        for item in root.findall(".//item")[:10]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            guid = item.findtext("guid", link).strip()
            image_urls = _extract_images(item, max_images=2)
            hook = _extract_hook(item)
            if title:
                items.append({
                    "title": title,
                    "link": link,
                    "guid": guid,
                    "image_urls": image_urls,
                    "hook": hook,
                })
        return items
    except Exception as e:
        print(f"  RSS 오류 ({url}): {e}")
        return []


# ── Facebook 포스팅 (멀티 이미지 + 댓글 링크) ───────────────────────────────

def _post_facebook(page_id: str, title: str, hook: str, image_urls: list[str], link: str, blog_id: str = "") -> str | None:
    token = _get_page_token(page_id)
    if not token:
        print(f"  [FB] 페이지 토큰 없음: {page_id}")
        return None

    message = _build_post_text(title, hook, blog_id) if hook else title
    post_id = None

    if len(image_urls) >= 2:
        # 멀티 이미지: 각 사진을 비공개 업로드 후 feed에 묶음
        media_ids = []
        for img_url in image_urls[:2]:
            r = _api(
                f"https://graph.facebook.com/v19.0/{page_id}/photos",
                {"url": img_url, "published": "false", "access_token": token},
            )
            mid = r.get("id")
            if mid:
                media_ids.append({"media_fbid": mid})
            time.sleep(1)

        if media_ids:
            resp = _api(
                f"https://graph.facebook.com/v19.0/{page_id}/feed",
                {
                    "message": message,
                    "attached_media": json.dumps(media_ids),
                    "access_token": token,
                },
            )
            post_id = resp.get("id")
            if not post_id:
                print(f"  [FB] 멀티이미지 포스트 실패: {resp.get('error','')}")

    elif len(image_urls) == 1:
        # 단일 이미지
        resp = _api(
            f"https://graph.facebook.com/v19.0/{page_id}/photos",
            {"url": image_urls[0], "message": message, "access_token": token},
        )
        post_id = resp.get("post_id") or resp.get("id")

    # 이미지 없거나 실패 시 텍스트 포스트
    if not post_id:
        resp = _api(
            f"https://graph.facebook.com/v19.0/{page_id}/feed",
            {"message": message, "access_token": token},
        )
        post_id = resp.get("id")

    if not post_id:
        print(f"  [FB] 포스팅 실패: {resp}")
        return None

    # 댓글에 링크 추가
    if link:
        time.sleep(2)
        comment_resp = _api(
            f"https://graph.facebook.com/v19.0/{post_id}/comments",
            {"message": f"🔗 자세히 보기 → {link}", "access_token": token},
        )
        if "id" in comment_resp:
            print(f"  [FB] 댓글 링크 추가 ✅")
        else:
            print(f"  [FB] 댓글 링크 실패: {comment_resp}")

    return post_id


# ── Threads 포스팅 (멀티 이미지 + 댓글 링크) ────────────────────────────────

def _post_threads(title: str, hook: str, image_urls: list[str], link: str, blog_id: str = "") -> str | None:
    text = _build_post_text(title, hook, blog_id) if hook else title
    creation_id = None

    if len(image_urls) >= 2:
        # 캐러셀: 각 이미지 아이템 컨테이너 생성 후 묶음
        item_ids = []
        for img_url in image_urls[:2]:
            r = _api(
                f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads",
                {"media_type": "IMAGE", "image_url": img_url,
                 "is_carousel_item": "true", "access_token": THREADS_TOKEN},
            )
            if r.get("id"):
                item_ids.append(r["id"])
            time.sleep(1)

        if len(item_ids) >= 2:
            resp = _api(
                f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads",
                {
                    "media_type": "CAROUSEL",
                    "children": ",".join(item_ids),
                    "text": text,
                    "access_token": THREADS_TOKEN,
                },
            )
            creation_id = resp.get("id")
            if not creation_id:
                print(f"  [Threads] 캐러셀 컨테이너 실패: {resp.get('error','')}")

    if not creation_id and image_urls:
        # 단일 이미지 또는 캐러셀 실패 폴백
        resp = _api(
            f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads",
            {"media_type": "IMAGE", "image_url": image_urls[0],
             "text": text, "access_token": THREADS_TOKEN},
        )
        creation_id = resp.get("id")

    if not creation_id:
        # 텍스트 폴백
        resp = _api(
            f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads",
            {"media_type": "TEXT", "text": text, "access_token": THREADS_TOKEN},
        )
        creation_id = resp.get("id")

    if not creation_id:
        print(f"  [Threads] 컨테이너 생성 실패: {resp}")
        return None

    time.sleep(3)

    # Step 2: 게시
    pub_resp = _api(
        f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads_publish",
        {"creation_id": creation_id, "access_token": THREADS_TOKEN},
    )
    thread_id = pub_resp.get("id")
    if not thread_id:
        print(f"  [Threads] 게시 실패: {pub_resp}")
        return None

    # 댓글에 링크 추가
    if link:
        time.sleep(3)
        reply_create = _api(
            f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads",
            {"media_type": "TEXT", "text": f"🔗 {link}", "reply_to_id": thread_id, "access_token": THREADS_TOKEN},
        )
        reply_id = reply_create.get("id")
        if reply_id:
            time.sleep(2)
            _api(
                f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads_publish",
                {"creation_id": reply_id, "access_token": THREADS_TOKEN},
            )
            print(f"  [Threads] 댓글 링크 추가 ✅")

    return thread_id


# ── 메인 ─────────────────────────────────────────────────────────────────────

def run(on_log=None):
    def log(msg):
        print(msg, flush=True)
        if on_log:
            on_log(msg)

    if not FB_USER_TOKEN or not THREADS_TOKEN:
        log("[소셜] .env에 FB_PAGE_ACCESS_TOKEN / THREADS_ACCESS_TOKEN 미설정")
        return

    state = _load_state()
    results = []
    last_blog_post_ts = 0.0  # 블로그 간 간격 추적

    for blog_id, cfg in BLOGS.items():
        blog_state = state.get(blog_id, {})
        posted_guids: set = set(blog_state.get("posted_guids", []))

        # 같은 블로그 재포스팅 간격 체크
        last_ts = blog_state.get("last_posted_ts", 0)
        elapsed = time.time() - last_ts
        if elapsed < POST_INTERVAL_SAME_BLOG:
            remaining = int((POST_INTERVAL_SAME_BLOG - elapsed) / 60)
            log(f"\n── {blog_id} 간격 미충족 ({remaining}분 후 가능) — 스킵")
            continue

        log(f"\n── {blog_id} RSS 확인 ──")
        items = _fetch_rss(cfg["rss"])
        if not items:
            log("  RSS 항목 없음")
            continue

        new_items = [it for it in items if it["guid"] not in posted_guids]
        if not new_items:
            log(f"  새 글 없음 (최신 {len(items)}개 모두 포스팅 완료)")
            continue

        item = new_items[0]
        log(f"  새 글: {item['title']}")
        log(f"  이미지: {len(item['image_urls'])}개")
        log(f"  후킹글: {item['hook'][:80]}...")

        # 블로그 간 간격 (30분) 대기
        gap_needed = POST_INTERVAL_BETWEEN_BLOGS - (time.time() - last_blog_post_ts)
        if gap_needed > 0 and last_blog_post_ts > 0:
            log(f"  블로그 간 간격 대기 {int(gap_needed)}초...")
            time.sleep(gap_needed)

        # 링크: tistory 내부 도메인 → 실제 서비스 도메인으로 교체 후 댓글에 추가
        link = _rewrite_link(item["link"], cfg)
        log(f"  링크: {link}")

        fb_ok = _post_facebook(
            cfg["fb_page_id"], item["title"], item["hook"], item["image_urls"], link, blog_id
        )
        log(f"  [FB] {'✅ ' + str(fb_ok) if fb_ok else '❌ 실패'}")

        th_ok = _post_threads(item["title"], item["hook"], item["image_urls"], link, blog_id)
        log(f"  [Threads] {'✅ ' + str(th_ok) if th_ok else '❌ 실패'}")

        if fb_ok or th_ok:
            posted_guids.add(item["guid"])
            state.setdefault(blog_id, {})
            state[blog_id]["posted_guids"] = list(posted_guids)[-50:]
            state[blog_id]["last_posted"] = datetime.now().isoformat()
            state[blog_id]["last_posted_ts"] = time.time()
            _save_state(state)
            last_blog_post_ts = time.time()

        results.append({
            "blog": blog_id, "title": item["title"],
            "fb": bool(fb_ok), "threads": bool(th_ok),
        })

    return results


if __name__ == "__main__":
    run()
