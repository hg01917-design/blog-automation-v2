#!/usr/bin/env python3
"""
wp_queue/publish_queue.py
wp_queue/ 폴더의 HTML 파일을 WordPress REST API로 발행.

사용법:
    python3 wp_queue/publish_queue.py

필요 환경변수 (remote_secrets.json 또는 환경변수):
    WP_USER, WP_APP_PASSWORD           -> baremi542.com
    TRIPLOG_WP_USER, TRIPLOG_WP_APP_PASSWORD -> app.baremi542.com
"""
import os
import re
import json
import base64
import urllib.request
import ssl
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
QUEUE_DIR = Path(__file__).parent

BLOG_CONFIG = {
    "baremi542": {
        "url": "https://baremi542.com",
        "user_key": "WP_USER",
        "pass_key": "WP_APP_PASSWORD",
    },
    "triplog": {
        "url": "https://app.baremi542.com",
        "user_key": "TRIPLOG_WP_USER",
        "pass_key": "TRIPLOG_WP_APP_PASSWORD",
    },
}

def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def _load_secrets():
    sec = {}
    sec_path = BASE_DIR / "remote_secrets.json"
    if sec_path.exists():
        sec = json.loads(sec_path.read_text(encoding="utf-8"))
    return sec

def _get_cred(sec, key):
    return sec.get(key) or os.environ.get(key, "")

def _wp_post(wp_url, auth, title, content, category_ids=None):
    payload = {
        "title": title,
        "content": content,
        "status": "publish",
    }
    if category_ids:
        payload["categories"] = category_ids
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{wp_url}/wp-json/wp/v2/posts",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30, context=_ssl_ctx()) as r:
        return json.loads(r.read())

def _get_category_id(wp_url, auth, category_name):
    req = urllib.request.Request(
        f"{wp_url}/wp-json/wp/v2/categories?search={urllib.request.quote(category_name)}&per_page=5",
        headers={"Authorization": f"Basic {auth}"},
    )
    with urllib.request.urlopen(req, timeout=15, context=_ssl_ctx()) as r:
        cats = json.loads(r.read())
    for c in cats:
        if c.get("name") == category_name:
            return c["id"]
    return None

def _char_count(html):
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return len(text)

def process_queue():
    sec = _load_secrets()
    results = []

    for html_file in sorted(QUEUE_DIR.glob("*.html")):
        content_raw = html_file.read_text(encoding="utf-8")

        blog_id = re.search(r'<!-- BLOG: (\S+) -->', content_raw)
        title   = re.search(r'<!-- TITLE: (.+?) -->', content_raw)
        status  = re.search(r'<!-- STATUS: (\S+) -->', content_raw)

        if not blog_id or not title:
            print(f"[스킵] 메타 정보 없음: {html_file.name}")
            continue

        blog_id = blog_id.group(1)
        title   = title.group(1).strip()
        status  = status.group(1) if status else "unknown"

        if status != "ready":
            print(f"[스킵] STATUS={status}: {html_file.name}")
            continue

        if blog_id not in BLOG_CONFIG:
            print(f"[스킵] 미지원 블로그: {blog_id}")
            continue

        cfg      = BLOG_CONFIG[blog_id]
        wp_url   = cfg["url"]
        wp_user  = _get_cred(sec, cfg["user_key"])
        wp_pass  = _get_cred(sec, cfg["pass_key"])

        if not (wp_user and wp_pass):
            print(f"[오류] {blog_id} 자격증명 없음 — {cfg['user_key']} / {cfg['pass_key']} 를 설정하세요.")
            results.append({"blog": blog_id, "title": title, "status": "cred_missing"})
            continue

        auth = base64.b64encode(f"{wp_user}:{wp_pass}".encode()).decode()

        body = re.sub(r'<!-- .+? -->\n?', '', content_raw).strip()

        char_len = _char_count(body)
        img_count = len(re.findall(r'<img ', body))
        print(f"[검수] {html_file.name}: {char_len}자, 이미지 {img_count}개")

        if char_len < 1700:
            print(f"[경고] 글자 수 부족 ({char_len}자) — 발행 스킵")
            results.append({"blog": blog_id, "title": title, "status": "too_short"})
            continue
        if img_count < 3:
            print(f"[경고] 이미지 {img_count}개 (최소 3개 필요) — 발행 스킵")
            results.append({"blog": blog_id, "title": title, "status": "no_images"})
            continue

        cat_ids = None
        if blog_id == "baremi542":
            cat_id = _get_category_id(wp_url, auth, "정부지원금")
            if cat_id:
                cat_ids = [cat_id]

        try:
            resp = _wp_post(wp_url, auth, title, body, cat_ids)
            post_id  = resp.get("id")
            post_url = resp.get("link", "")
            ts       = datetime.now().strftime("%Y-%m-%d %H:%M")
            print(f"[발행 완료] {blog_id} | ID:{post_id} | {title}")
            print(f"  URL: {post_url}")
            results.append({
                "blog": blog_id,
                "title": title,
                "post_id": post_id,
                "url": post_url,
                "published_at": ts,
                "status": "published",
            })
            html_file.rename(html_file.with_suffix(".done.html"))
        except Exception as e:
            print(f"[오류] 발행 실패: {e}")
            results.append({"blog": blog_id, "title": title, "status": f"error:{e}"})

    result_path = QUEUE_DIR / "publish_results.json"
    result_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\n결과 저장: {result_path}")
    return results

if __name__ == "__main__":
    import sys
    results = process_queue()
    published = [r for r in results if r.get("status") == "published"]
    errors    = [r for r in results if r.get("status") not in ("published", "ready")]
    print(f"\n=== 요약 ===")
    print(f"발행 성공: {len(published)}건")
    print(f"오류/스킵: {len(errors)}건")
    sys.exit(0 if not errors else 1)
