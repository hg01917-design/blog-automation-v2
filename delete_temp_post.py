import asyncio
import requests
from playwright.async_api import async_playwright

TELEGRAM_TOKEN = None
TELEGRAM_CHAT_ID = "8674424194"

def load_telegram_token():
    token_paths = [
        "/Users/hana/.claude/projects/-Users-hana-Downloads-blog-automation-v2/memory/telegram_token.txt",
        "/Users/hana/Downloads/blog-automation-v2/.telegram_token",
    ]
    for p in token_paths:
        try:
            with open(p) as f:
                tok = f.read().strip()
                if tok:
                    return tok
        except Exception:
            pass
    return None

def send_telegram(message):
    token = load_telegram_token()
    if not token:
        print("텔레그램 토큰 없음 - 로컬 로그만 출력")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message})
    print(f"텔레그램 전송: {resp.status_code} {resp.text[:100]}")

async def delete_temp_post():
    target_title = "나스닥 선물 지수"

    async with async_playwright() as p:
        # CDP 포트 9222 연결
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        print(f"브라우저 연결 성공")

        contexts = browser.contexts
        if contexts:
            context = contexts[0]
        else:
            context = await browser.new_context()

        page = await context.new_page()

        try:
            # 임시저장 목록 페이지 접속
            url = "https://nolja100.tistory.com/manage/posts/?type=TEMPORARY"
            print(f"접속 중: {url}")
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            print(f"현재 URL: {page.url}")

            # 페이지 제목 확인
            title = await page.title()
            print(f"페이지 제목: {title}")

            # 페이지 로드 대기 (JS 렌더링 포함)
            await page.wait_for_timeout(5000)

            # 페이지 소스에서 타겟 제목 확인
            content = await page.content()
            print(f"페이지 소스 길이: {len(content)}")

            # 어떤 셀렉터가 있는지 확인
            for sel in ["table", "tbody", "tr", ".post-item", "[class*='list']", "[class*='table']", "[class*='manage']", "article"]:
                els = await page.query_selector_all(sel)
                if els:
                    print(f"셀렉터 '{sel}': {len(els)}개")

            if target_title in content:
                print(f"페이지 소스에서 '{target_title}' 발견")
            else:
                print(f"페이지 소스에서 '{target_title}' 미발견")
                # 제목 일부로도 확인
                for partial in ["나스닥", "선물", "지수"]:
                    if partial in content:
                        print(f"부분 검색 '{partial}' 발견")

            # 글 목록 행 찾기 - 다양한 셀렉터 시도
            rows = await page.query_selector_all("tr")
            print(f"tr 개수: {len(rows)}")
            target_post = None
            for row in rows:
                row_text = await row.inner_text()
                if target_title in row_text:
                    target_post = row
                    print(f"타겟 행 발견: {row_text[:80].strip()}")
                    break

            if target_post is None:
                # 다른 셀렉터 시도
                for sel in [".post-item", "li[class*='post']", "div[class*='post-list'] > div", "tbody > tr"]:
                    items = await page.query_selector_all(sel)
                    for item in items:
                        item_text = await item.inner_text()
                        if target_title in item_text:
                            target_post = item
                            print(f"타겟 발견 (셀렉터 {sel}): {item_text[:80].strip()}")
                            break
                    if target_post:
                        break

            if target_post is None:
                print(f"'{target_title}' 글을 찾을 수 없음")
                # 버튼과 링크 목록 출력
                links = await page.query_selector_all("a")
                for link in links[:30]:
                    link_text = await link.inner_text()
                    link_href = await link.get_attribute("href")
                    if link_text.strip():
                        print(f"링크: {link_text.strip()[:50]} -> {link_href}")
                send_telegram(f"[nolja100] 임시저장 목록에서 '{target_title}' 글을 찾을 수 없습니다.")
                return

            # 체크박스 선택
            checkbox = await target_post.query_selector("input[type='checkbox']")
            if checkbox:
                await checkbox.click()
                print("체크박스 선택 완료")
                await page.wait_for_timeout(500)

            # 삭제 버튼 찾기
            # 다이얼로그 핸들러 먼저 등록
            page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.accept()))

            delete_btn = await target_post.query_selector("a[href*='delete'], button[class*='delete'], .btn-delete, a.delete, button[title*='삭제'], a[title*='삭제']")
            if delete_btn:
                await delete_btn.click()
                print("행 내 삭제 버튼 클릭")
            else:
                # 체크박스 선택 후 상단/하단 삭제 버튼
                delete_btn_global = await page.query_selector("#btn-delete, .btn-delete-selected, button[onclick*='delete'], a[onclick*='delete']")
                if delete_btn_global:
                    await delete_btn_global.click()
                    print("전체 삭제 버튼 클릭")
                else:
                    print("삭제 버튼을 찾을 수 없음 - 페이지 버튼 목록:")
                    buttons = await page.query_selector_all("button, input[type='button'], input[type='submit']")
                    for btn in buttons:
                        btn_text = await btn.inner_text()
                        btn_id = await btn.get_attribute("id")
                        btn_class = await btn.get_attribute("class")
                        print(f"버튼: '{btn_text.strip()}' id={btn_id} class={btn_class}")
                    send_telegram(f"[nolja100] '{target_title}' 삭제 버튼을 찾지 못했습니다.")
                    return

            await page.wait_for_timeout(2000)

            # 결과 확인
            current_content = await page.content()
            if target_title not in current_content:
                print(f"'{target_title}' 삭제 성공!")
                send_telegram(f"[nolja100] 임시저장 글 삭제 완료\n제목: {target_title}")
            else:
                print(f"삭제 후에도 '{target_title}' 존재 - 추가 처리 필요")
                send_telegram(f"[nolja100] '{target_title}' 삭제 시도했으나 확인 필요")

        except Exception as e:
            print(f"오류 발생: {e}")
            import traceback
            traceback.print_exc()
            send_telegram(f"[nolja100] 임시저장 글 삭제 중 오류: {e}")
        finally:
            await page.close()
            print("페이지 닫기 완료")

if __name__ == "__main__":
    asyncio.run(delete_temp_post())
