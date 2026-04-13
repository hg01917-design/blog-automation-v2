"""
notebooklm_research.py — Chrome 9222 CDP로 NotebookLM 완전 자동화
==================================================================
흐름: 키워드 → 웹 스크래핑 → NotebookLM 텍스트 소스 추가 → 자동 요약 추출 → 반환
별도 설치/로그인 불필요 (Chrome 9222 재사용)
"""

import asyncio
import re
import urllib.request
import urllib.parse
from playwright.async_api import async_playwright

CDP_URL = "http://localhost:9222"
NLM_HOME = "https://notebooklm.google.com"


def _scrape_text(keyword: str, max_chars: int = 10000) -> str:
    """네이버 검색 결과 페이지 텍스트 스크래핑"""
    try:
        q = urllib.parse.quote(keyword)
        url = f"https://search.naver.com/search.naver?query={q}&where=web"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                   "AppleWebKit/537.36 Chrome/120 Safari/537.36"}
        )
        html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")
        # HTML 태그 제거
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'&[a-z]+;', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        # 한글 포함 문장만 추출
        sentences = [s.strip() for s in text.split('.') if len(s.strip()) > 20 and re.search(r'[가-힣]{3,}', s)]
        result = '. '.join(sentences[:150])
        return result[:max_chars]
    except Exception as e:
        print(f"  [NLM] 스크래핑 오류: {e}", flush=True)
        return ""


async def _research_async(keyword: str, blog_id: str) -> str:
    # 1. 웹 스크래핑
    print(f"  [NLM] '{keyword}' 웹 스크래핑 중...", flush=True)
    scraped = _scrape_text(keyword)
    if not scraped:
        print("  [NLM] 스크래핑 실패 — 스킵", flush=True)
        return ""
    print(f"  [NLM] 스크래핑 완료 ({len(scraped)}자)", flush=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        page = await ctx.new_page()

        try:
            # 2. NotebookLM 홈 이동
            await page.goto(NLM_HOME, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # 3. 새 노트북 생성
            await page.locator('[aria-label="새 노트 만들기"]').first.click(timeout=10000)
            await asyncio.sleep(4)
            notebook_url = page.url
            print(f"  [NLM] 노트북 생성: {notebook_url}", flush=True)

            # 4. 소스 다이얼로그에서 "복사된 텍스트" 탭 클릭
            # (?addSource=true URL일 때 다이얼로그 자동 열림)
            await asyncio.sleep(2)

            paste_tab_selectors = [
                'button:has-text("복사된 텍스트")',
                '[role="tab"]:has-text("복사된 텍스트")',
                'span:has-text("복사된 텍스트")',
            ]
            paste_tab_found = False
            for sel in paste_tab_selectors:
                try:
                    await page.locator(sel).first.click(force=True, timeout=5000)
                    paste_tab_found = True
                    print(f"  [NLM] 복사된 텍스트 탭 클릭", flush=True)
                    break
                except Exception:
                    continue

            if not paste_tab_found:
                # 다이얼로그 닫혔으면 출처 추가 버튼으로 재진입
                await page.locator('[aria-label="출처 추가"]').first.click(force=True, timeout=10000)
                await asyncio.sleep(2)
                for sel in paste_tab_selectors:
                    try:
                        await page.locator(sel).first.click(force=True, timeout=5000)
                        paste_tab_found = True
                        break
                    except Exception:
                        continue

            await asyncio.sleep(2)

            # 5. 텍스트 붙여넣기
            paste_content = f"[{keyword} 관련 리서치 자료]\n\n{scraped}"
            paste_box_selectors = [
                'textarea[aria-label="붙여넣은 텍스트"]',
                'textarea[placeholder*="붙여넣"]',
                '.paste-text-area textarea',
            ]
            paste_box_found = False
            for sel in paste_box_selectors:
                try:
                    await page.locator(sel).first.fill(paste_content, timeout=8000)
                    paste_box_found = True
                    print(f"  [NLM] 텍스트 입력 완료 ({len(paste_content)}자)", flush=True)
                    break
                except Exception:
                    continue

            if not paste_box_found:
                print("  [NLM] ❌ 텍스트 입력 실패", flush=True)
                return ""

            await asyncio.sleep(1)

            # 삽입 버튼 클릭
            insert_btn_selectors = [
                'button:has-text("삽입하기")',
                'button:has-text("삽입")',
                'button:has-text("추가하기")',
                'button:has-text("추가")',
                'button:has-text("확인")',
            ]
            inserted = False
            for sel in insert_btn_selectors:
                try:
                    await page.locator(sel).last.click(force=True, timeout=5000)
                    inserted = True
                    print(f"  [NLM] 삽입 버튼 클릭", flush=True)
                    break
                except Exception:
                    continue

            if not inserted:
                print("  [NLM] ❌ 삽입 버튼 없음", flush=True)
                return ""

            # 6. NLM 자동 요약 생성 대기 (인덱싱 + 요약 생성)
            print("  [NLM] 소스 인덱싱 및 자동 요약 생성 중...", flush=True)
            result = ""
            for attempt in range(20):  # 최대 60초
                await asyncio.sleep(3)
                txt = await page.evaluate("""
                    () => {
                        // NLM이 소스 추가 후 자동 생성하는 노트북 요약
                        const emptyState = document.querySelector('.chat-panel-empty-state');
                        if (!emptyState) return '';

                        // 버튼/인터랙티브 요소 텍스트 제외하고 순수 텍스트 노드만 추출
                        const skip = new Set(['BUTTON', 'MAT-ICON', 'FOLLOW-UP', 'A']);
                        let parts = [];

                        function walk(node) {
                            if (node.nodeType === 3) {  // 텍스트 노드
                                const t = node.textContent.trim();
                                if (t.length > 3) parts.push(t);
                            } else if (node.nodeType === 1) {
                                if (skip.has(node.tagName)) return;
                                for (const child of node.childNodes) walk(child);
                            }
                        }

                        // 헤더 부분 제외: 이모지/제목/소스개수 div 이후부터 처리
                        const children = Array.from(emptyState.children);
                        let pastHeader = false;
                        for (const child of children) {
                            const t = child.innerText || '';
                            if (!pastHeader) {
                                if (/소스\\s*\\d+개/.test(t)) pastHeader = true;
                                continue;
                            }
                            walk(child);
                        }

                        return parts.join(' ').replace(/\\s+/g, ' ').trim();
                    }
                """)
                if txt and len(txt.strip()) > 100:
                    result = txt.strip()
                    print(f"  [NLM] ✅ 자동 요약 추출 완료 ({len(result)}자)", flush=True)
                    break

            if not result:
                print("  [NLM] ⚠️ 자동 요약 생성 실패", flush=True)

            # 7. 노트북 삭제 (JS 방식 — cdk-overlay 우회)
            try:
                await page.goto(NLM_HOME, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
                # 메뉴 열기
                await page.evaluate("""
                    () => {
                        const btn = document.querySelector('[aria-label="프로젝트 작업 메뉴"]');
                        if (btn) btn.click();
                    }
                """)
                await asyncio.sleep(1)
                # 삭제 메뉴 아이템 클릭
                await page.evaluate("""
                    () => {
                        const items = document.querySelectorAll('[role="menuitem"]');
                        const del = Array.from(items).find(i => i.textContent.includes('삭제'));
                        if (del) del.click();
                    }
                """)
                await asyncio.sleep(1.5)
                # 확인 다이얼로그 클릭
                await page.evaluate("""
                    () => {
                        const container = document.querySelector('.cdk-overlay-container');
                        if (!container) return;
                        const btns = Array.from(container.querySelectorAll('button'));
                        const confirm = btns.find(b => b.textContent.includes('삭제') || b.textContent.includes('Delete'));
                        if (confirm) confirm.click();
                    }
                """)
                await asyncio.sleep(1)
                print("  [NLM] 노트북 삭제 완료", flush=True)
            except Exception:
                pass

            return result

        except Exception as e:
            print(f"  [NLM] 오류: {e}", flush=True)
            return ""
        finally:
            await page.close()


def research_sync(keyword: str, blog_id: str = "default") -> str:
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
