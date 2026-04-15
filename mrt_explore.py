"""마이리얼트립 파트너 사이트 구조 파악 (기존 Chrome CDP 연결)
실행: python3 mrt_explore.py
→ 기존 Chrome 탭 1개에서 로그인 후 구조 출력. 창 닫지 않음.
"""
import os
import time
from pathlib import Path

# .env 로드
_root = Path(__file__).parent
_env = _root / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, _, v = _line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

MRT_EMAIL    = os.environ.get("MRT_EMAIL", "")
MRT_PASSWORD = os.environ.get("MRT_PASSWORD", "")
PARTNER_URL  = "https://partner.myrealtrip.com"


def explore():
    from browser import connect_cdp, get_or_create_page

    pw, browser = connect_cdp()
    # 기존 탭 재사용 or 새 탭 1개만 생성
    page = get_or_create_page(browser, url_contains="myrealtrip", navigate_to=f"{PARTNER_URL}/welcome")
    time.sleep(2)

    print(f"\n[1] URL: {page.url}")
    print(f"    제목: {page.title()}")

    # welcome 페이지 버튼 목록
    buttons = page.evaluate("""() => [...document.querySelectorAll('button')].map(el => ({
        text: el.innerText.trim(), className: el.className.substring(0,60)
    }))""")
    print(f"\n  버튼 {len(buttons)}개: {[b['text'] for b in buttons]}")

    # ── 파트너 로그인 버튼 클릭 ──────────────────────────────────────
    login_clicked = False
    for sel in ['button:has-text("파트너 로그인")', 'button:has-text("로그인")', 'a:has-text("로그인")']:
        try:
            if page.locator(sel).count() > 0:
                page.locator(sel).first.click()
                print(f"\n[2] 로그인 버튼 클릭: {sel}")
                time.sleep(2)
                login_clicked = True
                break
        except Exception as e:
            print(f"  {sel} 실패: {e}")

    print(f"  클릭 후 URL: {page.url}")

    # 현재 페이지 입력 필드 파악
    inputs = page.evaluate("""() => [...document.querySelectorAll('input')].map(el => ({
        type: el.type, name: el.name, id: el.id, placeholder: el.placeholder
    }))""")
    print(f"\n  입력 필드 {len(inputs)}개:")
    for inp in inputs:
        print(f"    type={inp['type']} id={inp['id']} placeholder={inp['placeholder']}")

    if not inputs:
        print("\n  ⚠️ 입력 필드 없음 — 이미 로그인된 상태이거나 다른 흐름")
        # 현재 페이지 전체 구조 덤프
        struct = page.evaluate("""() => {
            const els = [...document.querySelectorAll('nav a, header a, [class*=menu] a, [class*=nav] a, aside a')];
            return els.slice(0, 20).map(el => ({ text: el.innerText.trim(), href: el.href }));
        }""")
        print(f"\n  메뉴/링크 {len(struct)}개:")
        for s in struct:
            print(f"    '{s['text']}' → {s['href']}")
        # 페이지 body 텍스트 앞 500자
        body = page.evaluate("() => document.body.innerText.substring(0, 500)")
        print(f"\n  페이지 본문 앞 500자:\n{body}")
        # 탐색 끝 — 창 유지
        print("\n✅ 창 유지 중. 직접 확인 후 Ctrl+C로 종료하세요.")
        pw.stop()
        return

    # ── 로그인 폼 입력 ────────────────────────────────────────────────
    print(f"\n[3] 로그인 폼 입력 ({MRT_EMAIL})...")
    for sel in ['input[type="email"]', 'input[name="email"]', 'input[id*="email"]', 'input[placeholder*="이메일"]']:
        try:
            if page.locator(sel).count() > 0:
                page.locator(sel).first.fill(MRT_EMAIL)
                print(f"  이메일 셀렉터: {sel}")
                break
        except Exception:
            continue

    for sel in ['input[type="password"]', 'input[name="password"]']:
        try:
            if page.locator(sel).count() > 0:
                page.locator(sel).first.fill(MRT_PASSWORD)
                print(f"  비밀번호 셀렉터: {sel}")
                break
        except Exception:
            continue

    for sel in ['button[type="submit"]', 'button:has-text("로그인")', 'button:has-text("로그인하기")']:
        try:
            if page.locator(sel).count() > 0:
                page.locator(sel).first.click()
                print(f"  제출 버튼: {sel}")
                break
        except Exception:
            continue

    time.sleep(3)
    print(f"\n  로그인 후 URL: {page.url}")
    print(f"  로그인 후 제목: {page.title()}")

    # ── 로그인 후 메뉴/검색/딥링크 구조 파악 ───────────────────────
    nav = page.evaluate("""() => {
        const sels = ['nav a','header a','[class*=menu] a','[class*=nav] a','aside a','[class*=sidebar] a'];
        for (const s of sels) {
            const els = [...document.querySelectorAll(s)];
            if (els.length > 1) return els.slice(0, 20).map(el => ({ text: el.innerText.trim(), href: el.href }));
        }
        return [];
    }""")
    print(f"\n[4] 메뉴 {len(nav)}개:")
    for n in nav:
        print(f"  '{n['text']}' → {n['href']}")

    search = page.evaluate("""() => [...document.querySelectorAll('input')].map(el => ({
        type: el.type, id: el.id, name: el.name, placeholder: el.placeholder
    }))""")
    print(f"\n[5] 입력 필드 {len(search)}개:")
    for s in search:
        print(f"  type={s['type']} id={s['id']} placeholder={s['placeholder']}")

    deeplink = page.evaluate("""() => {
        const kws = ['제휴','딥링크','deeplink','affiliate','링크생성'];
        return [...document.querySelectorAll('a,button')].filter(el =>
            kws.some(k => el.innerText.includes(k) || (el.href||'').includes(k))
        ).slice(0, 10).map(el => ({ tag: el.tagName, text: el.innerText.trim(), href: el.href||'' }));
    }""")
    print(f"\n[6] 딥링크/제휴 관련 {len(deeplink)}개:")
    for d in deeplink:
        print(f"  <{d['tag']}> '{d['text']}' → {d['href']}")

    body = page.evaluate("() => document.body.innerText.substring(0, 600)")
    print(f"\n[7] 페이지 본문 앞 600자:\n{body}")

    print("\n✅ 탐색 완료. 창 유지 중 — 직접 확인 후 Ctrl+C로 종료하세요.")
    pw.stop()  # playwright 연결 해제 (Chrome 창은 유지)


if __name__ == "__main__":
    explore()
