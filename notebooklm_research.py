"""
notebooklm_research.py — NotebookLM 기반 리서치 자동화
=====================================================
notebooklm-py 라이브러리 활용:
  pip install "notebooklm-py[browser]"
  notebooklm login   # 최초 1회 구글 로그인

overnight_run.py에서 호출:
  from notebooklm_research import research_sync
  ctx = research_sync(keyword, blog_id)  → extra_context에 추가
"""

import asyncio
import re
import urllib.request
import urllib.parse
from pathlib import Path

# 블로그별 리서치 쿼리 템플릿
_BLOG_QUERY = {
    "nolja100":  "{kw} 여행 볼거리 먹거리 코스 교통 주차 입장료 운영시간 팁",
    "triplog":   "{kw} 여행 명소 숙소 맛집 교통 추천 코스",
    "salim1su":  "{kw} 방법 비용 절차 주의사항 팁 활용법",
    "goodisak":  "{kw} 개념 기능 비교 최신 트렌드 활용법",
    "baremi542": "{kw} 신청방법 자격 대상 혜택 금액 기간",
    "default":   "{kw} 핵심 정보 요약 특징 장단점 활용",
}

# 블로그별 검색 언어 힌트
_BLOG_LANG = {
    "nolja100": "한국 여행",
    "salim1su": "한국 생활정보",
    "goodisak": "IT 금융",
    "baremi542": "정부지원",
    "triplog": "여행",
}


def _get_search_urls(keyword: str, blog_id: str, n: int = 3) -> list[str]:
    """네이버 웹 검색에서 URL 수집"""
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

        # og:url 또는 href 패턴에서 URL 추출
        hrefs = re.findall(r'href="(https?://[^"&]+)"', html)
        seen_domains = set()
        urls = []
        skip_domains = {"naver.com", "google.com", "youtube.com", "instagram.com",
                        "facebook.com", "twitter.com", "t.co", "tistory.com/tag"}
        for href in hrefs:
            try:
                domain = re.sub(r'https?://([^/]+).*', r'\1', href).lower()
            except Exception:
                continue
            # 너무 짧은 URL 제외
            if len(href) < 20:
                continue
            skip = any(s in domain for s in skip_domains)
            if not skip and domain not in seen_domains:
                seen_domains.add(domain)
                urls.append(href)
            if len(urls) >= n:
                break
        return urls
    except Exception as e:
        print(f"  [NLM] URL 수집 오류: {e}", flush=True)
        return []


async def _research_async(keyword: str, blog_id: str, delete_after: bool = True) -> str:
    """NotebookLM 비동기 리서치 코어"""
    try:
        from notebooklm import NotebookLMClient  # type: ignore
    except ImportError:
        print("  [NLM] notebooklm-py 미설치 — 스킵 (pip install 'notebooklm-py[browser]')", flush=True)
        return ""

    query = _BLOG_QUERY.get(blog_id, _BLOG_QUERY["default"]).format(kw=keyword)

    # 1. 소스 URL 수집
    urls = _get_search_urls(keyword, blog_id, n=3)
    if not urls:
        print(f"  [NLM] '{keyword}' 소스 없음 — 스킵", flush=True)
        return ""

    print(f"  [NLM] '{keyword}' 리서치 시작 | 소스 {len(urls)}개 | blog={blog_id}", flush=True)
    nb_id = None

    try:
        async with await NotebookLMClient.from_storage() as client:
            # 2. 노트북 생성
            nb = await client.notebooks.create(f"[auto] {keyword[:40]}")
            nb_id = nb.id
            print(f"  [NLM] 노트북 생성: {nb_id}", flush=True)

            # 3. 소스 추가
            added = 0
            for src_url in urls:
                try:
                    await client.sources.add_url(nb_id, src_url)
                    added += 1
                    print(f"  [NLM] 소스 추가: {src_url[:70]}", flush=True)
                except Exception as e:
                    print(f"  [NLM] 소스 실패 ({src_url[:50]}): {e}", flush=True)

            if added == 0:
                print("  [NLM] ❌ 소스 추가 실패 전체 — 스킵", flush=True)
                return ""

            # 4. 소스 인덱싱 대기
            print(f"  [NLM] 소스 인덱싱 대기 중...", flush=True)
            await asyncio.sleep(20)

            # 5. 리서치 쿼리
            print(f"  [NLM] 쿼리: {query[:60]}...", flush=True)
            result = await client.chat.ask(nb_id, query)
            text = ""
            if hasattr(result, "answer"):
                text = result.answer or ""
            elif isinstance(result, str):
                text = result

            if text:
                print(f"  [NLM] ✅ 리서치 완료 ({len(text)}자)", flush=True)
            else:
                print("  [NLM] ⚠️ 응답 없음", flush=True)

            return text

    except Exception as e:
        print(f"  [NLM] 리서치 오류: {e}", flush=True)
        return ""

    finally:
        # 6. 노트북 정리
        if nb_id and delete_after:
            try:
                from notebooklm import NotebookLMClient  # type: ignore
                async with await NotebookLMClient.from_storage() as client:
                    await client.notebooks.delete(nb_id)
                    print(f"  [NLM] 노트북 삭제 완료", flush=True)
            except Exception:
                pass


def research_sync(keyword: str, blog_id: str = "default", delete_after: bool = True) -> str:
    """
    동기 래퍼 — overnight_run.py에서 직접 호출 가능
    Returns: 리서치 텍스트 (실패 시 "")
    """
    try:
        return asyncio.run(_research_async(keyword, blog_id, delete_after))
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
