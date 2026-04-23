"""welfare.baremi542.com 임시저장 목록에서 게이밍노트북 글 찾기"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from browser import connect_cdp


def log(msg):
    print(f"[welfare] {msg}", flush=True)


def main():
    pw, browser = connect_cdp(on_log=log)
    try:
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.bring_to_front()

        # welfare.baremi542.com 임시저장 목록
        for pg in range(1, 6):
            url = f"https://welfare.baremi542.com/manage/posts?state=temp&page={pg}"
            log(f"탐색: {url}")
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            drafts = page.evaluate("""() => {
                const results = [];
                const links = document.querySelectorAll('a[href*="manage/post/"]');
                for (const a of links) {
                    const m = (a.href||'').match(/manage\\/post\\/(\\d+)/);
                    const num = m ? parseInt(m[1]) : 0;
                    if (num === 0) continue;
                    const li = a.closest('li,tr,.item') || a.parentElement;
                    const text = (li ? li.textContent : a.textContent).trim().replace(/\\s+/g, ' ');
                    results.push({num, href: a.href, text: text.substring(0, 120)});
                }
                return results;
            }""")

            if not drafts:
                log(f"페이지 {pg}: 글 없음")
                break

            log(f"페이지 {pg}: {len(drafts)}개")
            for d in drafts:
                gaming = "★" if ("게이밍" in d["text"] or "gaming" in d["text"].lower() or "97" in str(d["num"])) else " "
                log(f"  {gaming}[{d['num']}] {d['text'][:80]}")

        # welfare 게이밍 검색
        log("\n검색: 게이밍노트북")
        page.goto("https://welfare.baremi542.com/manage/posts?searchKeyword=게이밍&searchType=title",
                  wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        r = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href*="manage/post/"]')).map(a => {
                const m = (a.href||'').match(/manage\\/post\\/(\\d+)/);
                const li = a.closest('li,tr,.item') || a.parentElement;
                return {num: m ? parseInt(m[1]) : 0, href: a.href,
                        text: ((li ? li.textContent : a.textContent)||'').trim().replace(/\\s+/g, ' ').substring(0, 100)};
            }).filter(x => x.num > 0);
        }""")
        log(f"welfare 게이밍 검색: {len(r)}개")
        for d in r:
            log(f"  [{d['num']}] {d['text']}")

    finally:
        pw.stop()
        log("완료")


if __name__ == "__main__":
    main()
