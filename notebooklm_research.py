"""
notebooklm_research.py — notebooklm-py 공식 라이브러리로 키워드 웹 리서치
===========================================================================
흐름: 키워드 → NotebookLM 웹 리서치(소스 자동 수집) → AI 요약 추출 → 반환
Chrome 9222 CDP 세션으로 인증 자동 추출 (별도 로그인 불필요)
"""

import asyncio
from pathlib import Path

CDP_URL = "http://localhost:9222"
NLM_STORAGE = Path.home() / ".notebooklm" / "storage_state.json"


async def _ensure_auth() -> bool:
    """Chrome CDP에서 NotebookLM 인증 상태 추출 → storage_state.json 생성."""
    if NLM_STORAGE.exists():
        return True

    print("  [NLM] storage_state.json 없음 — Chrome CDP에서 인증 추출 중...", flush=True)
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(CDP_URL)
            ctx = browser.contexts[0]
            page = await ctx.new_page()
            await page.goto("https://notebooklm.google.com", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            NLM_STORAGE.parent.mkdir(parents=True, exist_ok=True)
            await ctx.storage_state(path=str(NLM_STORAGE))
            await page.close()
            print("  [NLM] 인증 상태 저장 완료", flush=True)
            return True
    except Exception as e:
        print(f"  [NLM] 인증 추출 실패: {e}", flush=True)
        return False


async def _research_async(keyword: str, blog_id: str) -> str:
    if not await _ensure_auth():
        print("  [NLM] 인증 없음 — 스킵", flush=True)
        return ""

    print(f"  [NLM] '{keyword}' 웹 리서치 시작...", flush=True)

    try:
        from notebooklm import NotebookLMClient
    except ImportError:
        print("  [NLM] notebooklm-py 미설치 — pip3 install notebooklm-py", flush=True)
        return ""

    try:
        async with await NotebookLMClient.from_storage(str(NLM_STORAGE)) as client:

            # 1. 노트북 생성
            notebook = await client.notebooks.create(f"리서치: {keyword[:40]}")
            print(f"  [NLM] 노트북 생성: {notebook.id}", flush=True)

            try:
                # 2. 웹 리서치 시작 (NotebookLM이 직접 소스 검색·수집)
                research = await client.research.start(
                    notebook.id,
                    query=keyword,
                    source="web",
                    mode="fast",
                )
                task_id = research.get("task_id")
                print(f"  [NLM] 리서치 요청: task_id={task_id}", flush=True)

                # 3. 완료 대기 (최대 90초, 5초 간격)
                result = {}
                for i in range(18):
                    await asyncio.sleep(5)
                    result = await client.research.poll(notebook.id)
                    status = result.get("status", "")
                    print(f"  [NLM] 상태: {status} ({(i+1)*5}s)", flush=True)
                    if status == "completed":
                        break
                    if status == "no_research":
                        print("  [NLM] 리서치 결과 없음", flush=True)
                        return ""

                sources = result.get("sources", [])
                print(f"  [NLM] 소스 {len(sources)}개 발견", flush=True)

                # 4. 소스 노트북에 import
                if sources and task_id:
                    await client.research.import_sources(notebook.id, task_id, sources)
                    print(f"  [NLM] 소스 import 완료 — 인덱싱 대기...", flush=True)
                    await asyncio.sleep(8)

                # 5. NotebookLM AI 요약 추출
                description = await client.notebooks.get_description(notebook.id)
                summary = (description.summary or "").strip()

                # 소스 제목 목록도 함께 포함 (참고용)
                source_titles = [
                    s.get("title", "") for s in sources[:8] if s.get("title")
                ]
                if source_titles:
                    summary += "\n\n[참고 소스]\n" + "\n".join(f"- {t}" for t in source_titles)

                print(f"  [NLM] ✅ 리서치 완료 ({len(summary)}자)", flush=True)
                return summary

            finally:
                # 6. 노트북 삭제 (정리)
                try:
                    await client.notebooks.delete(notebook.id)
                    print("  [NLM] 노트북 삭제 완료", flush=True)
                except Exception:
                    pass

    except Exception as e:
        print(f"  [NLM] 오류: {e}", flush=True)
        # storage_state 만료 가능성 → 삭제 후 다음 실행에서 재생성
        if "auth" in str(e).lower() or "401" in str(e) or "403" in str(e):
            NLM_STORAGE.unlink(missing_ok=True)
            print("  [NLM] 인증 만료 — storage_state.json 삭제 (다음 실행 시 재생성)", flush=True)
        return ""


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
