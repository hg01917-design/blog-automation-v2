"""RSS → Facebook Pages + Threads 자동 포스팅
- goodisak/nolja100 → 이거알아요 Facebook Page + Threads
- salim1su → 퇴근후살림 Facebook Page + Threads
- 형식: 제목만 (링크 없음)
"""
import os
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

# .env 로드
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

# 블로그별 설정
BLOGS = {
    "goodisak": {
        "rss": "https://goodisak.tistory.com/rss",
        "fb_page_id": "981891965017107",   # 이거알아요
    },
    "nolja100": {
        "rss": "https://nolja100.tistory.com/rss",
        "fb_page_id": "981891965017107",   # 이거알아요
    },
    "salim1su": {
        "rss": "https://rss.blog.naver.com/salim1su.xml",
        "fb_page_id": "955279141010789",   # 퇴근후살림
    },
}

# ── 상태 파일 (중복 방지) ────────────────────────────────────────────────────

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
    """GET or POST JSON API 요청."""
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
        err_body = e.read().decode()
        return {"error": f"HTTP {e.code}", "body": err_body}
    except Exception as e:
        return {"error": str(e)}


# ── Facebook Page 토큰 취득 ───────────────────────────────────────────────────

_PAGE_TOKENS: dict[str, str] = {}

def _get_page_token(page_id: str) -> str:
    if page_id in _PAGE_TOKENS:
        return _PAGE_TOKENS[page_id]
    resp = _api(f"https://graph.facebook.com/v19.0/me/accounts?access_token={FB_USER_TOKEN}")
    for page in resp.get("data", []):
        _PAGE_TOKENS[page["id"]] = page["access_token"]
    return _PAGE_TOKENS.get(page_id, "")


# ── RSS 파싱 ─────────────────────────────────────────────────────────────────

def _fetch_rss(url: str) -> list[dict]:
    """RSS에서 최신 10개 항목 반환."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            content = r.read()
        root = ET.fromstring(content)
        ns = ""
        items = []
        for item in root.findall(f".//{ns}item")[:10]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            guid = item.findtext("guid", link).strip()
            pub = item.findtext("pubDate", "").strip()
            if title:
                items.append({"title": title, "link": link, "guid": guid, "pub": pub})
        return items
    except Exception as e:
        print(f"  RSS 오류 ({url}): {e}")
        return []


# ── Facebook 포스팅 ──────────────────────────────────────────────────────────

def _post_facebook(page_id: str, message: str) -> str | None:
    """Facebook Page에 텍스트 포스팅. 성공 시 post_id 반환."""
    token = _get_page_token(page_id)
    if not token:
        print(f"  [FB] 페이지 토큰 없음: {page_id}")
        return None
    resp = _api(
        f"https://graph.facebook.com/v19.0/{page_id}/feed",
        {"message": message, "access_token": token},
    )
    if "id" in resp:
        return resp["id"]
    print(f"  [FB] 포스팅 실패: {resp}")
    return None


# ── Threads 포스팅 ───────────────────────────────────────────────────────────

def _post_threads(text: str) -> str | None:
    """Threads에 텍스트 포스팅. 성공 시 media_id 반환."""
    # Step 1: 미디어 컨테이너 생성
    create_resp = _api(
        f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads",
        {"media_type": "TEXT", "text": text, "access_token": THREADS_TOKEN},
    )
    creation_id = create_resp.get("id")
    if not creation_id:
        print(f"  [Threads] 컨테이너 생성 실패: {create_resp}")
        return None

    time.sleep(3)  # 처리 대기

    # Step 2: 게시
    pub_resp = _api(
        f"https://graph.threads.net/v1.0/{THREADS_USER_ID}/threads_publish",
        {"creation_id": creation_id, "access_token": THREADS_TOKEN},
    )
    if "id" in pub_resp:
        return pub_resp["id"]
    print(f"  [Threads] 게시 실패: {pub_resp}")
    return None


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

    for blog_id, cfg in BLOGS.items():
        log(f"\n── {blog_id} RSS 확인 ──")
        items = _fetch_rss(cfg["rss"])
        if not items:
            log(f"  RSS 항목 없음")
            continue

        posted_guids: set = set(state.get(blog_id, {}).get("posted_guids", []))
        new_items = [it for it in items if it["guid"] not in posted_guids]

        if not new_items:
            log(f"  새 글 없음 ({len(items)}개 중 모두 이미 포스팅됨)")
            continue

        # 가장 최신 1개만 포스팅 (연속 도배 방지)
        item = new_items[0]
        title = item["title"]
        log(f"  새 글: {title}")

        fb_ok = _post_facebook(cfg["fb_page_id"], title)
        if fb_ok:
            log(f"  [FB] ✅ 포스팅 완료 (id: {fb_ok})")
        else:
            log(f"  [FB] ❌ 실패")

        th_ok = _post_threads(title)
        if th_ok:
            log(f"  [Threads] ✅ 포스팅 완료 (id: {th_ok})")
        else:
            log(f"  [Threads] ❌ 실패")

        if fb_ok or th_ok:
            posted_guids.add(item["guid"])
            if blog_id not in state:
                state[blog_id] = {}
            state[blog_id]["posted_guids"] = list(posted_guids)[-50:]  # 최근 50개만 유지
            state[blog_id]["last_posted"] = datetime.now().isoformat()
            _save_state(state)

        results.append({
            "blog": blog_id,
            "title": title,
            "fb": bool(fb_ok),
            "threads": bool(th_ok),
        })

        time.sleep(2)

    return results


if __name__ == "__main__":
    run()
