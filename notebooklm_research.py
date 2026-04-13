"""
notebooklm_research.py — 기존 Chrome 9222 CDP로 NotebookLM 리서치 자동화
=========================================================================
별도 설치/로그인 불필요 — Chrome 9222가 이미 구글 계정 로그인 상태임을 이용.
"""

import asyncio
import re
import urllib.request
import urllib.parse
from playwright.async_api import async_playwright

CDP_URL = "http://localhost:9222"
NLM_HOME = "https://notebooklm.google.com"

# 블로그별 리서치 쿼리 템플릿
_BLOG_QUERY = {
    "nolja100":  "{kw} 여행 볼거리 먹거리 교통 주차 입장료 운영시간 팁 추천",
    "triplog":   "{kw} 여행 명소 숙소 맛집 코스 교통 추천",
    "salim1su":  "{kw} 방법 비용 절차 주의사항 팁 활용법",
    "goodisak":  "{kw} 개념 기능 비교 트렌드 활용법",
    "baremi542": "{kw} 신청방법 자격 대상 혜택 금액 기간",
    "default":   "{kw} 핵심 정보 특징 장단점 활용",
}

_BLOG_LANG = {
    "nolja100": "한국 여행",
    "salim1su": "한국 생활정보",
    "goodisak": "IT 금융",
    "baremi542": "정부지원",
    "triplog": "여행",
}


def _get_search_urls(keyword: str, blog_id: str, n: int = 3) -> list:
    """네이버 웹 검색에서 소스 URL 수집"""
    try:
        lang_hint = _BLOG_LANG.get(blog_id, "")
        q = urllib.parse.quote(f"{keyword} {lang_hint}".strip())
        url = f"https://search.naver.com/search.naver?query={q}&where=web"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
        )
        html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")
        hrefs = re.findall(r'href="(https?://[^"&]+)"', html)
        seen_domains = set()
        urls = []
        skip = {"naver.com", "google.com", "youtube.com", "instagram.com", "facebook.com"}
        for href in hrefs:
            if len(href) < 20:
                continue
            domain = re.sub(r'https?://([^/]+).*', r'\1', href).lower()
            if not any(s in domain for s in skip) and domain not in seen_domains:
                seen_domains.add(domain)
                urls.append(href)
            if len(urls) >= n:
                break
        return urls
    except Exception as e:
        print(f"  [NLM] URL 수집 오류: {e}", flush=True)
        return []


async def _research_async(keyword: str, blog_id: str) -> str:
    """Chrome 9222 CDP로 NotebookLM 리서치"""
    query = _BLOG_QUERY.get(blog_id, _BLOG_QUERY["default"]).format(kw=keyword)
    urls = _get_search_urls(keyword, blog_id, n=3)

    if not urls:
        print(f"  [NLM] '{keyword}' 소스 없음 — 스킵", flush=True)
        return ""

    print(f"  [NLM] '{keyword}' 리서치 시작 (소스 {len(urls)}개)", flush=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        page = await ctx.new_page()

        try:
            # 1. NotebookLM 홈 이동
            await page.goto(NLM_HOME, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # 2. 새 노트북 생성 버튼 클릭
            new_btn = page.locator('button:has-text("New notebook"), button:has-text("새 노트북"), [data-test-id="new-notebook-button"]')
            await new_btn.first.click(timeout=15000)
            await asyncio.sleep(2)

            # 3. 소스 URL 추가
            added = 0
            for src_url in urls:
                try:
                    # "Add source" 버튼
                    add_src = page.locator('button:has-text("Add source"), button:has-text("소스 추가")')
                    await add_src.first.click(timeout=10000)
                    await asyncio.sleep(1)

                    # "Website" 탭 선택
                    website_tab = page.locator('button:has-text("Website"), [role="tab"]:has-text("Website"), div:has-text("Website URL")')
                    await website_tab.first.click(timeout=8000)
                    await asyncio.sleep(0.8)

                    # URL 입력
                    url_input = page.locator('input[type="url"], input[placeholder*="URL"], input[placeholder*="url"], input[placeholder*="http"]')
                    await url_input.first.click()
                    await url_input.first.fill(src_url)
                    await asyncio.sleep(0.5)

                    # Insert 버튼
                    insert_btn = page.locator('button:has-text("Insert"), button:has-text("삽입"), button:has-text("Add")')
                    await insert_btn.first.click(timeout=8000)
                    await asyncio.sleep(1.5)

                    added += 1
                    print(f"  [NLM] 소스 추가: {src_url[:60]}", flush=True)
                except Exception as e:
                    print(f"  [NLM] 소스 실패 ({src_url[:40]}...): {e}", flush=True)

            if added == 0:
                print("  [NLM] ❌ 소스 추가 전체 실패", flush=True)
                return ""

            # 4. 소스 처리 대기
            print("  [NLM] 소스 인덱싱 대기 중...", flush=True)
            await asyncio.sleep(25)

            # 5. 채팅 입력창에 질문
            print(f"  [NLM] 쿼리: {query[:60]}...", flush=True)
            chat = page.locator('[contenteditable="true"][data-placeholder], textarea[placeholder*="Ask"], div[role="textbox"]')
            await chat.first.click(timeout=10000)
            await chat.first.fill(query)
            await asyncio.sleep(0.5)
            await page.keyboard.press("Enter")

            # 6. 응답 대기 (최대 60초)
            result = ""
            for _ in range(20):
                await asyncio.sleep(3)
                result = await page.evaluate("""
                    () => {
                        const candidates = [
                            ...document.querySelectorAll('.response-container .response-text'),
                            ...document.querySelectorAll('[class*="response"] p'),
                            ...document.querySelectorAll('.chat-response, .answer-content'),
                            ...document.querySelectorAll('note-response, [data-test*="response"]'),
                        ];
                        if (candidates.length > 0) {
                            return candidates[candidates.length - 1].innerText || '';
                        }
                        // 최후 수단: 모든 답변 영역 텍스트
                        const allText = document.querySelectorAll('.chat-turn:last-child');
                        return allText.length > 0 ? allText[allText.length-1].innerText : '';
                    }
                """)
                if result and len(result) > 100:
                    break

            if result:
                print(f"  [NLM] ✅ 완료 ({len(result)}자)", flush=True)
            else:
                print("  [NLM] ⚠️ 응답 추출 실패", flush=True)

            # 7. 노트북 삭제 (홈으로 돌아가서 삭제)
            try:
                await page.goto(NLM_HOME, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                # 첫 번째 노트북 (방금 만든 것) 우클릭 or 메뉴
                nb_menu = page.locator('[aria-label*="more options"], button[aria-label*="More"], .notebook-card button').first
                await nb_menu.click(timeout=5000)
                await asyncio.sleep(0.8)
                del_item = page.locator('[role="menuitem"]:has-text("Delete"), button:has-text("Delete")')
                await del_item.first.click(timeout=5000)
                await asyncio.sleep(0.8)
                confirm = page.locator('button:has-text("Delete"), button:has-text("확인")')
                await confirm.first.click(timeout=5000)
                print("  [NLM] 노트북 삭제 완료", flush=True)
            except Exception:
                pass  # 삭제 실패해도 무관

            return result

        except Exception as e:
            print(f"  [NLM] 오류: {e}", flush=True)
            return ""
        finally:
            await page.close()


def research_sync(keyword: str, blog_id: str = "default") -> str:
    """동기 래퍼 — overnight_run.py에서 직접 호출"""
    try:
        return asyncio.run(_research_async(keyword, blog_id))
    except Exception as e:
        print(f"  [NLM] asyncio 오류: {e}", flush=True)
        return ""


if __name__ == "__main__":
    import sys
    kw = sys.argv[1] if len(sys.argv) > 1 else "강릉 커피거리 여행"
    blog = sys.argv[2] if len(sys.argv) > 2 else "nolja100"
    print(f"\n테스트: keyword='{kw}', blog_id='{blog}'")
    result = research_sync(kw, blog)
    print("\n=== NotebookLM 리서치 결과 ===")
    print(result or "(결과 없음)")
