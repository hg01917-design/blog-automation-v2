#!/usr/bin/env python3
"""
WordPress 발행 글 마크다운 잔재 / 내부 마커 / 금지 표현 수정 스크립트
baremi542 + triplog 최근 10개씩 대상
"""
import re
import json
import requests
from requests.auth import HTTPBasicAuth

BLOGS = {
    "baremi542": {
        "url": "https://baremi542.com",
        "user": "hg01917@gmail.com",
        "password": "7gij zLxb 7xe8 bE3n RdXC 1f8a",
        "check_title_forbidden": False,
    },
    "triplog": {
        "url": "https://app.baremi542.com",
        "user": "hg01917@gmail.com",
        "password": "4dUp 9MLs efgZ PLif WGdz zwWa",
        "check_title_forbidden": True,
    },
}

def fix_content(raw: str) -> tuple[str, list[str]]:
    """본문 수정. 수정된 raw와 수정 내역 리스트 반환."""
    changes = []
    original = raw

    # 1. **텍스트** → <strong>텍스트</strong>
    # HTML 태그 속성 안의 것은 제외하기 위해 태그 밖에서만 치환
    # 간단하게 전체에서 치환 (속성값 안에 ** 는 현실적으로 없음)
    count_before = len(re.findall(r'\*\*[^*\n]+\*\*', raw))
    raw = re.sub(r'\*\*([^*\n]+)\*\*', r'<strong>\1</strong>', raw)
    if count_before > 0:
        changes.append(f'**bold** → <strong> {count_before}건 치환')

    # 2. *텍스트* → <em>텍스트</em>  (단독 * 만, **는 이미 처리됨)
    count_before = len(re.findall(r'(?<!\*)\*(?!\*)([^*\n]+)(?<!\*)\*(?!\*)', raw))
    raw = re.sub(r'(?<!\*)\*(?!\*)([^*\n]+)(?<!\*)\*(?!\*)', r'<em>\1</em>', raw)
    if count_before > 0:
        changes.append(f'*italic* → <em> {count_before}건 치환')

    # 3. p 태그 안의 ## heading → <h2>, ### → <h3>
    # 패턴: <p>## 제목</p> 또는 줄 시작 ## (HTML 안)
    def replace_heading(m):
        hashes = m.group(1)
        text = m.group(2).strip()
        level = len(hashes)
        return f'<h{level}>{text}</h{level}>'

    count_before = len(re.findall(r'<p>(#{1,3})\s+(.+?)</p>', raw))
    raw = re.sub(r'<p>(#{1,3})\s+(.+?)</p>', replace_heading, raw)
    if count_before > 0:
        changes.append(f'<p>## 제목</p> → <h2> {count_before}건 치환')

    # HTML 안 텍스트로 노출된 ## (p 태그 안 아닌 경우도 포함)
    count_before = len(re.findall(r'(?m)^(#{1,3})\s+(.+)$', raw))
    raw = re.sub(r'(?m)^(#{1,3})\s+(.+)$', replace_heading, raw)
    if count_before > 0:
        changes.append(f'## 줄 시작 heading → <h> {count_before}건 치환')

    # 4. 내부 마커 포함 문장/단락 삭제
    for marker in ['[검증 필요]', '[확인 필요]', '[출처 필요]']:
        if marker in raw:
            # 해당 마커가 포함된 <p>...</p> 블록 전체 삭제
            pattern = r'<p>[^<]*' + re.escape(marker) + r'[^<]*</p>'
            count = len(re.findall(pattern, raw))
            raw = re.sub(pattern, '', raw)
            # 태그 밖에 남은 잔재도 삭제
            count2 = raw.count(marker)
            raw = raw.replace(marker, '')
            total = count + count2
            if total > 0:
                changes.append(f'{marker} {total}건 삭제')

    # 5. 함께 읽으면 좋은 글 단락 삭제
    # 패턴: <div style="...함께 읽으면 좋은 글... </ul>\n</div>
    if '함께 읽으면 좋은 글' in raw:
        # div 블록 전체 삭제 (greedy 최소 매칭)
        pattern = r'<div[^>]*>(?:<strong>)?[^<]*📌\s*함께 읽으면 좋은 글[^<]*(?:</strong>)?.*?</div>'
        count = len(re.findall(pattern, raw, re.DOTALL))
        raw = re.sub(pattern, '', raw, flags=re.DOTALL)
        if count > 0:
            changes.append(f'함께 읽으면 좋은 글 div 블록 {count}건 삭제')
        # 혹시 남아있으면 p 태그 단위로 한번 더
        if '함께 읽으면 좋은 글' in raw:
            pattern2 = r'<p>[^<]*함께 읽으면 좋은 글[^<]*</p>'
            count2 = len(re.findall(pattern2, raw))
            raw = re.sub(pattern2, '', raw)
            if count2 > 0:
                changes.append(f'함께 읽으면 좋은 글 p태그 {count2}건 삭제')

    # 6. pick flick / 픽 플릭 단락 삭제
    for term in ['pick flick', 'Pick Flick', 'PICK FLICK', '픽 플릭']:
        if term in raw:
            pattern = r'<p>[^<]*' + re.escape(term) + r'[^<]*</p>'
            count = len(re.findall(pattern, raw, re.IGNORECASE))
            raw = re.sub(pattern, '', raw, flags=re.IGNORECASE)
            if count == 0:
                # 혹시 div 안에 있는 경우
                raw = raw.replace(term, '')
                changes.append(f'{term} 텍스트 삭제')
            else:
                changes.append(f'{term} 단락 {count}건 삭제')

    return raw, changes


def fix_title(title: str) -> tuple[str, list[str]]:
    """제목 수정. 수정된 제목과 변경 내역 반환."""
    changes = []
    original = title

    # 완벽정리 삭제
    if '완벽정리' in title:
        title = title.replace('완벽정리', '').strip()
        # 앞뒤 남은 ' — ' 정리
        title = re.sub(r'\s*—\s*—\s*', ' — ', title)
        title = re.sub(r'^\s*—\s*', '', title)
        title = re.sub(r'\s*—\s*$', '', title)
        title = re.sub(r'\s+', ' ', title).strip()
        changes.append(f'완벽정리 삭제: "{original}" → "{title}"')

    # 숫자+가지/곳/개 삭제 (예: "5가지", "7곳")
    # 뒤에 오는 전체 구문도 같이 정리
    m = re.search(r'\s*[0-9]+(?:가지|곳|개)\s*(?:와|과|의|를|을|이|가|은|는|,|$)?', title)
    if m:
        new_title = re.sub(r'\s*[0-9]+(?:가지|곳|개)\s*(?:와|과|의|를|을|이|가|은|는|,)?', '', title).strip()
        # 다시 깔끔하게
        new_title = re.sub(r'\s+', ' ', new_title).strip()
        new_title = re.sub(r'\s*—\s*$', '', new_title).strip()
        changes.append(f'숫자나열 삭제: "{title}" → "{new_title}"')
        title = new_title

    return title, changes


def patch_post(blog_name, cfg, post_id, payload, dry_run=False):
    url = f"{cfg['url']}/wp-json/wp/v2/posts/{post_id}"
    auth = HTTPBasicAuth(cfg['user'], cfg['password'])
    if dry_run:
        print(f"  [DRY RUN] PATCH {url} payload keys: {list(payload.keys())}")
        return True
    resp = requests.patch(url, json=payload, auth=auth, timeout=30)
    if resp.status_code in (200, 201):
        return True
    else:
        print(f"  ERROR PATCH {resp.status_code}: {resp.text[:200]}")
        return False


def process_blog(blog_name, cfg):
    print(f"\n{'='*60}")
    print(f"블로그: {blog_name} ({cfg['url']})")
    print('='*60)

    auth = HTTPBasicAuth(cfg['user'], cfg['password'])
    url = f"{cfg['url']}/wp-json/wp/v2/posts?status=publish&per_page=10&context=edit"
    resp = requests.get(url, auth=auth, timeout=30)
    posts = resp.json()

    total_fixed = 0
    report = []

    for post in posts:
        post_id = post['id']
        title_raw = post.get('title', {}).get('raw', '')
        content_raw = post.get('content', {}).get('raw', '')

        all_changes = []
        payload = {}

        # 본문 수정
        new_content, content_changes = fix_content(content_raw)
        if content_changes:
            payload['content'] = new_content
            all_changes.extend(content_changes)

        # 제목 수정 (triplog만)
        if cfg['check_title_forbidden']:
            new_title, title_changes = fix_title(title_raw)
            if title_changes:
                payload['title'] = new_title
                all_changes.extend(title_changes)

        if all_changes:
            print(f"\n  ID {post_id}: {title_raw[:55]}")
            for c in all_changes:
                print(f"    - {c}")
            ok = patch_post(blog_name, cfg, post_id, payload)
            if ok:
                print(f"    → PATCH 저장 완료")
                total_fixed += 1
                report.append({
                    'id': post_id,
                    'title': title_raw[:55],
                    'changes': all_changes
                })
            else:
                print(f"    → PATCH 실패!")
        else:
            print(f"  ID {post_id}: OK (수정 없음)")

    print(f"\n  총 {total_fixed}개 글 수정 완료")
    return report


if __name__ == '__main__':
    all_reports = {}
    for blog_name, cfg in BLOGS.items():
        all_reports[blog_name] = process_blog(blog_name, cfg)

    print("\n\n" + "="*60)
    print("전체 수정 요약")
    print("="*60)
    for blog_name, reports in all_reports.items():
        print(f"\n[{blog_name}] {len(reports)}개 글 수정")
        for r in reports:
            print(f"  ID {r['id']}: {r['title']}")
            for c in r['changes']:
                print(f"    - {c}")
