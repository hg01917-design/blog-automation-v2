"""
goodisak 임시저장 목록 전체 순회 → 게이밍노트북 글 찾기 + 번호 확인
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from browser import connect_cdp, get_or_create_page


def log(msg):
    print(f"[find] {msg}", flush=True)


def main():
    pw, browser = connect_cdp(on_log=log)

    try:
        page = None
        for ctx in browser.contexts:
            for p in ctx.pages:
                if "goodisak.tistory.com" in p.url:
                    page = p
                    break
            if page:
                break

        if not page:
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

        page.bring_to_front()

        # 모든 임시저장 글 전체 탐색
        all_drafts = []
        for pg in range(1, 10):
            url = f"https://goodisak.tistory.com/manage/posts?state=temp&page={pg}"
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            drafts = page.evaluate("""() => {
                const results = [];
                const links = document.querySelectorAll('a[href*="manage/post/"]');
                for (const a of links) {
                    const href = a.href || '';
                    const m = href.match(/manage\\/post\\/(\\d+)/);
                    const num = m ? parseInt(m[1]) : 0;
                    if (num === 0) continue;
                    const li = a.closest('li, tr, .item') || a.parentElement;
                    const text = (li ? li.textContent : a.textContent).trim().replace(/\\s+/g, ' ');
                    results.push({num, href, text: text.substring(0, 120)});
                }
                return results;
            }""")

            if not drafts:
                log(f"페이지 {pg}: 글 없음. 종료.")
                break

            log(f"페이지 {pg}: {len(drafts)}개")
            for d in drafts:
                log(f"  [{d['num']}] {d['text'][:80]}")
            all_drafts.extend(drafts)

        log(f"\n전체 임시저장 글: {len(all_drafts)}개")
        log(f"번호 범위: {min(d['num'] for d in all_drafts) if all_drafts else 'N/A'} ~ {max(d['num'] for d in all_drafts) if all_drafts else 'N/A'}")

        # 게이밍노트북 글 찾기
        gaming = [d for d in all_drafts if "게이밍" in d["text"] or "gaming" in d["text"].lower()]
        log(f"\n게이밍 관련 글: {len(gaming)}개")
        for d in gaming:
            log(f"  [{d['num']}] {d['text'][:100]}")

        # 제목으로 "게이밍노트북추천" 검색
        log("\n검색: 게이밍노트북추천")
        page.goto("https://goodisak.tistory.com/manage/posts?state=temp&searchKeyword=게이밍노트북&searchType=title",
                  wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        page.screenshot(path="/tmp/gaming_search.png")
        search_result = page.evaluate("""() => {
            const links = document.querySelectorAll('a[href*="manage/post/"]');
            return Array.from(links).map(a => {
                const m = (a.href||'').match(/manage\\/post\\/(\\d+)/);
                const li = a.closest('li,tr,.item') || a.parentElement;
                const text = (li ? li.textContent : a.textContent).trim().replace(/\\s+/g, ' ');
                return {num: m ? parseInt(m[1]) : 0, href: a.href, text: text.substring(0, 120)};
            }).filter(x => x.num > 0);
        }""")
        log(f"검색결과 {len(search_result)}개:")
        for d in search_result:
            log(f"  [{d['num']}] {d['text'][:100]}")

    finally:
        pw.stop()
        log("완료")


if __name__ == "__main__":
    main()
