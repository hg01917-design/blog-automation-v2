"""Chrome DevTools Protocol을 직접 사용해 phn0502 발행 (Playwright 없음)"""
import asyncio
import json
import random
import re
import sys

TAB_WS = "ws://localhost:9222/devtools/page/5E3CD46710F51AADEDC25A85E4857401"
REPLACEMENTS = ["이 플랫폼", "해당 서비스", "스트리밍 서비스", "동영상 플랫폼", "OTT 서비스"]


async def cdp_eval(ws, expr, timeout=30):
    """CDP Runtime.evaluate 실행 후 결과 반환"""
    msg_id = random.randint(1000, 9999)
    payload = json.dumps({
        "id": msg_id,
        "method": "Runtime.evaluate",
        "params": {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": False
        }
    })
    await ws.send(payload)
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return None
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5))
            data = json.loads(raw)
            if data.get("id") == msg_id:
                result = data.get("result", {})
                if "exceptionDetails" in result:
                    err = result["exceptionDetails"].get("exception", {}).get("description", "?")
                    print(f"  JS 오류: {err[:200]}", flush=True)
                    return None
                val = result.get("result", {}).get("value")
                return val
        except asyncio.TimeoutError:
            pass


async def main():
    import websockets

    print("=== CDP 직접 연결 시작 ===", flush=True)
    async with websockets.connect(TAB_WS, ping_interval=20, ping_timeout=30) as ws:
        print("WebSocket 연결 성공!", flush=True)

        # 현재 URL 확인
        url = await cdp_eval(ws, "window.location.href")
        print(f"현재 URL: {url}", flush=True)

        # 에디터에 있는지 확인
        if url and "/manage/newpost" not in url:
            print("에디터 페이지 아님. 이동 필요.", flush=True)
            await cdp_eval(ws, "window.onbeforeunload = null; window.location.href = 'https://phn0502.tistory.com/manage/newpost/'")
            await asyncio.sleep(5)
            url = await cdp_eval(ws, "window.location.href")
            print(f"이동 후: {url}", flush=True)

        # 임시저장 드래프트 버튼 클릭
        print("임시저장 버튼 클릭...", flush=True)
        count_result = await cdp_eval(ws, """
            (() => {
                const btn = document.querySelector('a.count[aria-label*="임시저장"]');
                if (btn) { btn.click(); return btn.textContent.trim(); }
                return null;
            })()
        """)
        print(f"임시저장 버튼: {count_result}", flush=True)
        await asyncio.sleep(2)

        # 웨이브 드래프트 클릭
        draft_title = await cdp_eval(ws, """
            (() => {
                const links = [...document.querySelectorAll('a.link_info')];
                const target = links.find(l => l.textContent.includes('웨이브')) || links[0];
                if (target) {
                    const t = target.textContent.trim();
                    target.click();
                    return t;
                }
                return null;
            })()
        """)
        print(f"드래프트 클릭: {draft_title}", flush=True)
        await asyncio.sleep(5)

        # TinyMCE 대기
        print("TinyMCE 대기...", flush=True)
        for i in range(30):
            ok = await cdp_eval(ws, "typeof tinymce !== 'undefined' && tinymce.activeEditor !== null")
            if ok:
                print(f"TinyMCE 로드됨 ({i+1}회)", flush=True)
                break
            await asyncio.sleep(1)
        else:
            print("TinyMCE 실패", flush=True)
            return

        # 콘텐츠 가져오기
        content = await cdp_eval(ws, "tinymce.activeEditor.getContent()")
        if not content:
            print("콘텐츠 없음", flush=True)
            return
        print(f"콘텐츠 길이: {len(content)}", flush=True)

        # 키워드 밀도 수정
        keyword = "웨이브"
        plain = re.sub(r'<[^>]+>', '', content)
        words = plain.split()
        kw_count = sum(1 for w in words if keyword in w)
        density = kw_count / len(words) * 100 if words else 0
        print(f"밀도: {kw_count}/{len(words)} = {density:.1f}%", flush=True)

        if density > 4.0:
            target_count = int(len(words) * 0.035)
            remove_count = max(0, kw_count - target_count)
            fixed = content
            first = fixed.find(keyword)
            for _ in range(remove_count):
                idx = fixed.rfind(keyword)
                if idx < 0 or idx == first:
                    break
                fixed = fixed[:idx] + random.choice(REPLACEMENTS) + fixed[idx+len(keyword):]
            new_count = sum(1 for w in re.sub(r'<[^>]+>','',fixed).split() if keyword in w)
            print(f"수정 후: {new_count}개", flush=True)
            escaped = json.dumps(fixed)
            await cdp_eval(ws, f"tinymce.activeEditor.setContent({escaped})")
            print("콘텐츠 업데이트 완료", flush=True)
            await asyncio.sleep(2)

        # 완료 버튼 클릭 (발행 패널 열기)
        print("완료 버튼 클릭...", flush=True)
        layer_result = await cdp_eval(ws, """
            (() => {
                // #publish-layer-btn 또는 텍스트 '완료' 버튼
                const byId = document.getElementById('publish-layer-btn');
                if (byId && byId.offsetParent !== null) {
                    byId.click();
                    return 'id: ' + byId.textContent.trim();
                }
                const btns = [...document.querySelectorAll('button')].filter(b => b.offsetParent !== null);
                const t = btns.find(b => b.textContent.trim() === '완료');
                if (t) { t.click(); return 'text: 완료'; }
                return 'not found';
            })()
        """)
        print(f"완료 버튼: {layer_result}", flush=True)
        await asyncio.sleep(3)

        # 패널 버튼 확인
        panel_btns = await cdp_eval(ws, """
            (() => {
                const btns = [...document.querySelectorAll('button')].filter(b => b.offsetParent !== null);
                return JSON.stringify(btns.map(b => ({text: b.textContent.trim(), disabled: b.disabled})).filter(b => b.text));
            })()
        """)
        print(f"패널 버튼 목록: {panel_btns}", flush=True)

        # "공개 발행" 버튼 클릭
        print("공개 발행 버튼 클릭...", flush=True)
        pub_result = await cdp_eval(ws, """
            (() => {
                const btns = [...document.querySelectorAll('button')].filter(b => b.offsetParent !== null);
                // "공개 발행" 텍스트 버튼 (disabled 무관하게 찾기)
                const target = btns.find(b => b.textContent.trim() === '공개 발행');
                if (target) {
                    // disabled라도 강제 클릭
                    target.disabled = false;
                    target.removeAttribute('disabled');
                    target.click();
                    return 'clicked 공개 발행, was disabled=' + target.disabled;
                }
                // fallback: 발행하기, 발행, 확인
                for (const lbl of ['발행하기', '발행', '확인', '게시']) {
                    const b = btns.find(x => x.textContent.trim() === lbl);
                    if (b) {
                        b.disabled = false;
                        b.click();
                        return 'fallback: ' + lbl;
                    }
                }
                return 'not found';
            })()
        """)
        print(f"공개 발행: {pub_result}", flush=True)
        await asyncio.sleep(5)

        # 최종 URL 확인
        final_url = await cdp_eval(ws, "window.location.href")
        print(f"최종 URL: {final_url}", flush=True)

        if final_url and "/manage/newpost" not in final_url:
            print("=== 발행 성공! ===", flush=True)
        else:
            print("=== URL 변화 없음 — 발행 실패 가능성 ===", flush=True)
            # 현재 표시 중인 버튼 재확인
            btns2 = await cdp_eval(ws, """
                (() => {
                    const btns = [...document.querySelectorAll('button')].filter(b => b.offsetParent !== null);
                    return JSON.stringify(btns.map(b => ({text: b.textContent.trim(), disabled: b.disabled})).filter(b => b.text));
                })()
            """)
            print(f"현재 버튼: {btns2}", flush=True)

        print("=== 완료 ===", flush=True)


asyncio.run(main())
