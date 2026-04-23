"""
Chrome DevTools Protocol 직접 WebSocket 호출로 게이밍노트북 이미지 삽입.
Playwright CDP 연결 타임아웃 문제를 우회.

1. goodisak 글쓰기 탭에서 임시저장 목록 열기 (직접 navigate)
2. 게이밍노트북 임시저장 글 찾아서 에디터로 열기
3. 기존 이미지 삭제 후 빙 이미지 4개 삽입
4. 임시저장
"""
import json
import time
import base64
import urllib.request
import websocket
from pathlib import Path

IMAGE_PATHS = [
    "/Users/hana/Downloads/blog-automation-v2/images/bing-gaming-final-1.jpg",
    "/Users/hana/Downloads/blog-automation-v2/images/bing-gaming-final-2.jpg",
    "/Users/hana/Downloads/blog-automation-v2/images/bing-gaming-final-3.jpg",
    "/Users/hana/Downloads/blog-automation-v2/images/bing-gaming-final-4.jpg",
]

def log(msg):
    print(f"[cdp_gaming] {msg}", flush=True)


class CDPSession:
    def __init__(self, ws_url: str, timeout: int = 10):
        self.ws = websocket.create_connection(
            ws_url,
            timeout=timeout,
            header={"Origin": "http://localhost:9222"},
        )
        self._id = 0

    def send(self, method: str, params: dict = None) -> dict:
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params or {}}
        self.ws.send(json.dumps(msg))
        # 응답 수신 (해당 id 응답이 올 때까지 대기)
        while True:
            raw = self.ws.recv()
            data = json.loads(raw)
            if data.get("id") == self._id:
                return data
            # 이벤트는 무시

    def navigate(self, url: str, wait_ms: int = 3000) -> dict:
        result = self.send("Page.navigate", {"url": url})
        time.sleep(wait_ms / 1000)
        return result

    def evaluate(self, expression: str) -> any:
        result = self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True,
        })
        if "error" in result:
            raise RuntimeError(f"CDP evaluate error: {result['error']}")
        val = result.get("result", {}).get("result", {})
        return val.get("value")

    def close(self):
        self.ws.close()


def get_goodisak_tab_ws():
    """goodisak 글쓰기 탭의 WebSocket URL 반환"""
    resp = urllib.request.urlopen("http://localhost:9222/json", timeout=5)
    tabs = json.loads(resp.read())
    for t in tabs:
        if t.get("type") == "page" and "goodisak.tistory.com" in t.get("url", ""):
            return t["webSocketDebuggerUrl"], t
    # 없으면 첫 번째 page 탭 사용
    for t in tabs:
        if t.get("type") == "page":
            return t["webSocketDebuggerUrl"], t
    raise RuntimeError("사용 가능한 page 탭 없음")


def find_gaming_draft(cdp: CDPSession) -> str | None:
    """
    임시저장 목록에서 게이밍노트북 글의 링크 반환.
    """
    # type=PRIVATE 방식 먼저 시도
    log("임시저장 목록으로 이동 (type=PRIVATE)...")
    cdp.navigate("https://www.tistory.com/manage/posts?type=PRIVATE", wait_ms=3000)

    href = cdp.evaluate("""
        (() => {
            const links = document.querySelectorAll('a');
            for (const a of links) {
                const text = (a.textContent || '').toLowerCase();
                if (text.includes('게이밍노트북') || text.includes('게이밍 노트북') || text.includes('gaming laptop') || text.includes('gaming notebook')) {
                    return a.href;
                }
            }
            // 글 목록 행에서 찾기
            const rows = document.querySelectorAll('tr, li, article, .post-item');
            for (const row of rows) {
                const text = (row.textContent || '').toLowerCase();
                if (text.includes('게이밍노트북') || text.includes('게이밍 노트북')) {
                    const a = row.querySelector('a');
                    if (a) return a.href;
                }
            }
            return null;
        })()
    """)

    if href:
        log(f"게이밍노트북 draft 발견 (tistory.com): {href}")
        return href

    # goodisak 직접 URL로 재시도
    log("goodisak 직접 URL로 재시도...")
    cdp.navigate("https://goodisak.tistory.com/manage/posts?state=temp", wait_ms=3000)

    href = cdp.evaluate("""
        (() => {
            const links = document.querySelectorAll('a');
            for (const a of links) {
                const text = (a.textContent || '').toLowerCase();
                if (text.includes('게이밍노트북') || text.includes('게이밍 노트북')) {
                    return a.href;
                }
            }
            const rows = document.querySelectorAll('tr, li, .post-item');
            for (const row of rows) {
                const text = (row.textContent || '').toLowerCase();
                if (text.includes('게이밍노트북') || text.includes('게이밍 노트북')) {
                    const a = row.querySelector('a');
                    if (a) return a.href;
                }
            }
            // 페이지 텍스트 일부 출력 (디버그)
            return 'DEBUG:' + document.body.innerText.substring(0, 500);
        })()
    """)

    if href and not href.startswith("DEBUG:"):
        log(f"게이밍노트북 draft 발견 (goodisak): {href}")
        return href

    if href and href.startswith("DEBUG:"):
        log(f"페이지 내용: {href[6:300]}")

    return None


def insert_images_in_editor(cdp: CDPSession, draft_url: str) -> dict:
    """에디터로 이동 후 이미지 삽입"""
    log(f"에디터로 이동: {draft_url}")
    cdp.navigate(draft_url, wait_ms=5000)

    current_url = cdp.evaluate("window.location.href")
    log(f"현재 URL: {current_url}")

    # TinyMCE iframe 내용 접근은 CDPSession.evaluate로 불가 (cross-frame)
    # TinyMCE API를 통해 최상단 window에서 접근
    img_before = cdp.evaluate("""
        (() => {
            try {
                const ed = tinymce.get('content') || tinymce.activeEditor;
                if (ed) return ed.getBody().querySelectorAll('img').length;
            } catch(e) {}
            // iframe 방식
            const iframes = document.querySelectorAll('iframe');
            for (const ifr of iframes) {
                try {
                    const count = ifr.contentDocument.body.querySelectorAll('img').length;
                    return count;
                } catch(e) {}
            }
            return -1;
        })()
    """)
    log(f"삭제 전 이미지 수: {img_before}")

    # 기존 이미지 삭제
    removed = cdp.evaluate("""
        (() => {
            let count = 0;
            // TinyMCE API 방식
            try {
                const ed = tinymce.get('content') || tinymce.activeEditor;
                if (ed) {
                    const imgs = ed.getBody().querySelectorAll('img');
                    imgs.forEach(img => { img.remove(); count++; });
                    return {method: 'tinymce', count: count};
                }
            } catch(e) {}
            // iframe 방식
            const iframes = document.querySelectorAll('iframe');
            for (const ifr of iframes) {
                try {
                    const imgs = ifr.contentDocument.body.querySelectorAll('img');
                    imgs.forEach(img => { img.remove(); count++; });
                    if (count > 0) return {method: 'iframe', count: count};
                } catch(e) {}
            }
            return {method: 'none', count: 0};
        })()
    """)
    log(f"이미지 삭제 결과: {removed}")
    time.sleep(0.5)

    # 소제목 파악
    headings = cdp.evaluate("""
        (() => {
            const result = [];
            let body = null;
            try {
                const ed = tinymce.get('content') || tinymce.activeEditor;
                if (ed) body = ed.getBody();
            } catch(e) {}
            if (!body) {
                const iframes = document.querySelectorAll('iframe');
                for (const ifr of iframes) {
                    try { body = ifr.contentDocument.body; break; } catch(e) {}
                }
            }
            if (!body) return result;
            const els = body.querySelectorAll('h2, h3');
            els.forEach((el, i) => {
                result.push({tag: el.tagName, text: el.innerText.trim().substring(0, 100), index: i});
            });
            return result;
        })()
    """)
    log(f"소제목 {len(headings) if headings else 0}개 발견:")
    if headings:
        for h in headings:
            log(f"  [{h['index']}] {h['tag']}: {h['text']}")

    # 이미지 4개 삽입
    inserted = 0
    for i, img_path in enumerate(IMAGE_PATHS):
        if not Path(img_path).exists():
            log(f"[{i+1}] 파일 없음: {img_path}")
            continue

        img_data = Path(img_path).read_bytes()
        b64 = base64.b64encode(img_data).decode()
        mime = "image/jpeg"
        log(f"[{i+1}/4] {Path(img_path).name} 삽입 중... ({len(img_data)//1024}KB)")

        result = cdp.evaluate(f"""
            ((idx) => {{
                let body = null;
                try {{
                    const ed = tinymce.get('content') || tinymce.activeEditor;
                    if (ed) body = ed.getBody();
                }} catch(e) {{}}
                if (!body) {{
                    const iframes = document.querySelectorAll('iframe');
                    for (const ifr of iframes) {{
                        try {{ body = ifr.contentDocument.body; break; }} catch(e) {{}}
                    }}
                }}
                if (!body) return 'error:no_body';

                const wrapper = document.createElement('p');
                wrapper.style.textAlign = 'center';
                wrapper.style.margin = '20px 0';

                const img = document.createElement('img');
                img.src = 'data:{mime};base64,{b64}';
                img.alt = '게이밍노트북 추천 이미지 ' + (idx + 1);
                img.style.maxWidth = '100%';
                img.style.height = 'auto';
                img.setAttribute('data-bing', '1');
                wrapper.appendChild(img);

                const headings = body.querySelectorAll('h2, h3');
                if (headings.length > idx) {{
                    const h = headings[idx];
                    if (h.nextSibling) {{
                        h.parentNode.insertBefore(wrapper, h.nextSibling);
                    }} else {{
                        h.parentNode.appendChild(wrapper);
                    }}
                    return 'ok:after_heading_' + idx + '_' + h.tagName;
                }} else if (headings.length > 0) {{
                    const lastH = headings[headings.length - 1];
                    let insertPoint = lastH;
                    let next = lastH.nextSibling;
                    while (next) {{
                        if (next.nodeType === 1 && next.querySelector && next.querySelector('img[data-bing]')) {{
                            insertPoint = next;
                            next = next.nextSibling;
                        }} else {{ break; }}
                    }}
                    if (insertPoint.nextSibling) {{
                        insertPoint.parentNode.insertBefore(wrapper, insertPoint.nextSibling);
                    }} else {{
                        insertPoint.parentNode.appendChild(wrapper);
                    }}
                    return 'ok:after_last_heading_' + idx;
                }} else {{
                    body.appendChild(wrapper);
                    return 'ok:appended_to_body_' + idx;
                }}
            }})({i})
        """)
        log(f"  결과: {result}")
        if result and result.startswith("ok:"):
            inserted += 1
        time.sleep(0.3)

    final_count = cdp.evaluate("""
        (() => {
            let body = null;
            try {
                const ed = tinymce.get('content') || tinymce.activeEditor;
                if (ed) body = ed.getBody();
            } catch(e) {}
            if (!body) {
                const iframes = document.querySelectorAll('iframe');
                for (const ifr of iframes) {
                    try { body = ifr.contentDocument.body; break; } catch(e) {}
                }
            }
            if (!body) return -1;
            return body.querySelectorAll('img').length;
        })()
    """)
    log(f"삽입 완료: {inserted}/4개, 최종 이미지 수: {final_count}")
    return {"inserted": inserted, "final_img_count": final_count}


def save_draft(cdp: CDPSession):
    """임시저장 버튼 클릭"""
    saved = cdp.evaluate("""
        (() => {
            const btns = document.querySelectorAll('button');
            for (const btn of btns) {
                const text = btn.textContent.trim();
                if (text.includes('임시저장') || text === '저장') {
                    btn.click();
                    return text;
                }
            }
            return null;
        })()
    """)
    if saved:
        log(f"임시저장 클릭: '{saved}'")
    else:
        log("임시저장 버튼 없음 — Ctrl+S 시뮬레이션")
        cdp.send("Input.dispatchKeyEvent", {
            "type": "keyDown",
            "modifiers": 2,  # Ctrl
            "key": "s",
            "code": "KeyS",
        })
        time.sleep(0.1)
        cdp.send("Input.dispatchKeyEvent", {
            "type": "keyUp",
            "modifiers": 2,
            "key": "s",
            "code": "KeyS",
        })
    time.sleep(2)


def main():
    log("=== goodisak 게이밍노트북 CDP 직접 이미지 삽입 시작 ===")

    # 이미지 파일 확인
    for p in IMAGE_PATHS:
        if not Path(p).exists():
            log(f"ERROR: 파일 없음: {p}")
            exit(1)
        log(f"이미지 확인: {Path(p).name} ({Path(p).stat().st_size:,} bytes)")

    # goodisak 탭 WebSocket URL 가져오기
    ws_url, tab_info = get_goodisak_tab_ws()
    log(f"대상 탭: {tab_info['title']} | {tab_info['url'][:60]}")
    log(f"WebSocket URL: {ws_url}")

    cdp = CDPSession(ws_url, timeout=15)
    log("CDP WebSocket 연결 성공")

    try:
        # 임시저장 글 찾기
        draft_url = find_gaming_draft(cdp)

        if not draft_url:
            body_text = cdp.evaluate("document.body.innerText.substring(0, 500)")
            log(f"현재 페이지 내용: {body_text}")
            log("ERROR: 게이밍노트북 임시저장 글을 찾을 수 없음!")
            exit(1)

        log(f"드래프트 URL: {draft_url}")

        # 이미지 삽입
        result = insert_images_in_editor(cdp, draft_url)
        log(f"이미지 삽입 결과: {result}")

        # 임시저장
        save_draft(cdp)

        log("=== 완료 ===")
        log(f"삽입된 이미지: {result['inserted']}/4개")
        log(f"최종 에디터 이미지 수: {result['final_img_count']}")

    finally:
        cdp.close()
        log("CDP WebSocket 연결 종료")


if __name__ == "__main__":
    main()
