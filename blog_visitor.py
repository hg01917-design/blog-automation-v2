"""블로그 일 평균 방문자 수 크롤링 → 동적 키워드 검색량 범위 결정"""
import re
import json
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path

# ── 방문자 수 → 검색량 범위 매핑 ──────────────────────────────────────────────
VOLUME_RANGES = {
    "low":  {"min": 100,   "max": 3_000,  "label": "0~10명"},
    "mid":  {"min": 1_000, "max": 10_000, "label": "10~50명"},
    "high": {"min": 3_000, "max": 30_000, "label": "50명↑"},
}

VISITOR_TIERS = [(50, "high"), (10, "mid"), (0, "low")]

# 블로그별 통계 설정
BLOG_STATS_CONFIG = {
    "salim1su":  {"type": "naver",   "id": "salim1su"},
    "goodisak":  {"type": "tistory", "domain": "goodisak.tistory.com"},
    "nolja100":  {"type": "tistory", "domain": "nolja100.tistory.com"},
    "baremi542": {"type": "tistory", "domain": "issue.baremi542.com"},
}

_CACHE_FILE = Path(__file__).parent / "logs" / "visitor_stats.json"
_CACHE_TTL_HOURS = 4
_lock = threading.Lock()


# ── 캐시 ──────────────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    try:
        if _CACHE_FILE.exists():
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_cache(cache: dict):
    _CACHE_FILE.parent.mkdir(exist_ok=True)
    _CACHE_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _is_fresh(entry: dict) -> bool:
    if not entry:
        return False
    try:
        return datetime.now() - datetime.fromisoformat(entry["updated_at"]) \
               < timedelta(hours=_CACHE_TTL_HOURS)
    except Exception:
        return False


# ── 방문자 티어 ────────────────────────────────────────────────────────────────

def get_visitor_level(visitors: int) -> str:
    for threshold, level in VISITOR_TIERS:
        if visitors >= threshold:
            return level
    return "low"


def get_volume_range(visitors: int) -> dict:
    return VOLUME_RANGES[get_visitor_level(visitors)]


# ── 크롤링: 네이버 ────────────────────────────────────────────────────────────

def _scrape_naver(blog_id: str, page, on_log=None):
    def log(msg):
        if on_log: on_log(msg)

    # 1차: 통계 관리 페이지 (로그인 세션 활용)
    try:
        url = f"https://blog.naver.com/{blog_id}/manage/statistic"
        log(f"[방문자] 네이버 통계 페이지 접속: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)

        # 프레임 포함 전체 탐색
        targets = [page] + list(page.frames)
        for target in targets:
            for sel in [
                ".visitor_count", ".item_count", ".count_daily",
                "[class*='visitor'] .num", ".daily_num", "td.visitor",
            ]:
                try:
                    els = target.locator(sel)
                    if els.count() == 0:
                        continue
                    raw = els.first.inner_text(timeout=1500).strip()
                    num = re.sub(r"[^\d]", "", raw)
                    if num:
                        log(f"[방문자] 네이버 {blog_id}: {num}명 (sel: {sel})")
                        return int(num)
                except Exception:
                    continue
    except Exception as e:
        log(f"[방문자] 네이버 통계 페이지 실패: {e}")

    # 2차: 통계 페이지 JS 기반 추출
    try:
        result = page.evaluate("""() => {
            // 통계 페이지 내 숫자 탐색
            const selectors = [
                '.item_visitor .num', '.visitor_daily', '.count_today',
                '.statistics_visitor .count', '.num_today', '.daily_visitor',
                '[class*="visitor"] [class*="num"]', '[class*="today"] [class*="count"]',
                '.area_visitor .num', '.visitor_count .num',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    const n = parseInt(el.innerText.replace(/[^0-9]/g,''));
                    if (!isNaN(n)) return n;
                }
            }
            // 프레임 내 탐색
            return null;
        }""")
        if result is not None and result >= 0:
            log(f"[방문자] 네이버 {blog_id} JS추출: {result}명")
            return result
    except Exception:
        pass

    # 3차: 블로그 메인 페이지 — 프로필 아래 통계 위젯
    try:
        blog_url = f"https://blog.naver.com/{blog_id}"
        log(f"[방문자] 네이버 블로그 메인 접속: {blog_url}")
        page.goto(blog_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)

        # iframe 내부 탐색 (네이버 블로그는 iframe 기반)
        frames = page.frames
        for frame in frames:
            try:
                result = frame.evaluate("""() => {
                    const selectors = [
                        '.blog_visitor_cnt', '.visitor_cnt', '.cnt_visitor',
                        '#visitorcntWrap .cnt', '.statistics_area .count',
                        '[class*="visitor_cnt"]', '[class*="visitorcnt"]',
                        '.area_info_visitor .cnt', '.info_visitor .count',
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el) {
                            const n = parseInt(el.innerText.replace(/[^0-9]/g,''));
                            if (!isNaN(n)) return n;
                        }
                    }
                    // 텍스트 "오늘" 옆 숫자 탐색
                    const allText = document.body ? document.body.innerText : '';
                    const m = allText.match(/오늘\s*[:\s]*([0-9,]+)/);
                    if (m) return parseInt(m[1].replace(/,/g,''));
                    return null;
                }""")
                if result is not None and result >= 0:
                    log(f"[방문자] 네이버 {blog_id} 메인페이지: {result}명")
                    return result
            except Exception:
                continue
    except Exception as e:
        log(f"[방문자] 네이버 메인 페이지 실패: {e}")

    return None


# ── 크롤링: 티스토리 ──────────────────────────────────────────────────────────

def _scrape_tistory(domain: str, page, on_log=None):
    def log(msg):
        if on_log: on_log(msg)

    try:
        url = f"https://{domain}/manage/stats"
        log(f"[방문자] 티스토리 통계 페이지 접속: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)

        # 선택자 우선순위 탐색
        for sel in [
            ".statistics_daily .count", ".count_today", ".num_today",
            "[class*='today'] .num", "[class*='visitor'] .count",
            ".statistics_item .count", "td.num", ".visit_count",
        ]:
            try:
                els = page.locator(sel)
                if els.count() == 0:
                    continue
                raw = els.first.inner_text(timeout=1500).strip()
                num = re.sub(r"[^\d]", "", raw)
                if num:
                    log(f"[방문자] 티스토리 {domain}: {num}명 (sel: {sel})")
                    return int(num)
            except Exception:
                continue

        # JS 기반 추출 (chartData 또는 통계 변수)
        try:
            result = page.evaluate("""() => {
                // 티스토리 통계 페이지 chartData 탐색
                const candidates = [
                    window.chartData, window.visitorData, window.statData
                ];
                for (const d of candidates) {
                    if (d && Array.isArray(d)) {
                        const nums = d.map(x => parseInt(x) || 0).filter(n => n >= 0);
                        if (nums.length) return Math.round(nums.reduce((a,b)=>a+b,0)/nums.length);
                    }
                }
                // 페이지에서 숫자가 담긴 첫 번째 통계 셀 탐색
                const cells = document.querySelectorAll('td, .count, .num, [class*="count"]');
                for (const c of cells) {
                    const t = c.innerText.trim().replace(/[,\\s]/g,'');
                    if (/^\\d{1,6}$/.test(t) && parseInt(t) >= 0) return parseInt(t);
                }
                return null;
            }""")
            if result is not None:
                log(f"[방문자] 티스토리 {domain} JS: {result}명")
                return int(result)
        except Exception:
            pass

    except Exception as e:
        log(f"[방문자] 티스토리 {domain} 실패: {e}")

    return None


# ── 메인 진입점 ────────────────────────────────────────────────────────────────

def fetch_visitor_count(blog_id: str, on_log=None) -> int:
    """블로그 일 방문자 수 반환. 캐시 유효 시 캐시 사용, 만료 시 크롤링."""
    def log(msg):
        if on_log: on_log(msg)

    # 캐시 확인
    with _lock:
        cache = _load_cache()
        entry = cache.get(blog_id, {})

    if _is_fresh(entry):
        v = entry["visitors"]
        log(f"[방문자] {blog_id} 캐시 ({entry['updated_at'][:16]}): {v}명")
        return v

    # 크롤링
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from browser import connect_cdp

    cfg = BLOG_STATS_CONFIG.get(blog_id)
    if not cfg:
        log(f"[방문자] {blog_id} 설정 없음 — 0 반환")
        return entry.get("visitors", 0)

    visitors = None
    pw = None
    try:
        pw, browser = connect_cdp(on_log)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        try:
            if cfg["type"] == "naver":
                visitors = _scrape_naver(cfg["id"], page, on_log)
            else:
                visitors = _scrape_tistory(cfg["domain"], page, on_log)
        finally:
            try: page.close()
            except Exception: pass
    except Exception as e:
        log(f"[방문자] {blog_id} CDP 연결 실패: {e}")
    finally:
        try:
            if pw: pw.stop()
        except Exception:
            pass

    # 크롤링 실패 시 이전 캐시값 유지
    if visitors is None:
        visitors = entry.get("visitors", 0)
        log(f"[방문자] {blog_id} 크롤링 실패 → 이전값 {visitors}명 유지")
    else:
        log(f"[방문자] {blog_id} 갱신 완료: {visitors}명")

    # 캐시 저장
    with _lock:
        cache = _load_cache()
        cache[blog_id] = {
            "visitors": visitors,
            "updated_at": datetime.now().isoformat(),
        }
        _save_cache(cache)

    return visitors


def get_volume_range_for_blog(blog_id: str, on_log=None) -> dict:
    """블로그 방문자 수 기반 검색량 범위 반환.

    Returns:
        {"min": int, "max": int, "label": str}
    """
    def log(msg):
        if on_log: on_log(msg)

    visitors = fetch_visitor_count(blog_id, on_log)
    vrange = get_volume_range(visitors)
    level = get_visitor_level(visitors)
    log(
        f"[방문자] {blog_id} {visitors}명 → {level}"
        f"({vrange['label']}): 검색량 {vrange['min']:,}~{vrange['max']:,}"
    )
    return vrange


def refresh_all(on_log=None):
    """모든 블로그 방문자 수 강제 갱신 (4시간 스케줄러 호출용)."""
    def log(msg):
        if on_log: on_log(msg)

    log("[방문자] 전체 갱신 시작")

    # 캐시 강제 만료
    with _lock:
        cache = _load_cache()
        for bid in BLOG_STATS_CONFIG:
            if bid in cache:
                cache[bid]["updated_at"] = "2000-01-01T00:00:00"
        _save_cache(cache)

    # 순차 크롤링 (CDP 단일 세션)
    for bid in BLOG_STATS_CONFIG:
        try:
            count = fetch_visitor_count(bid, on_log)
            log(f"[방문자] {bid}: {count}명")
            time.sleep(2)
        except Exception as e:
            log(f"[방문자] {bid} 갱신 오류: {e}")

    log("[방문자] 전체 갱신 완료")
