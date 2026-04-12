"""이슈봇 — 실시간 트렌드 키워드 → 정보성 글 생성 → Tistory 발행

흐름:
1. Google Trends (pytrends) + Naver 자동완성으로 트렌드 키워드 수집
2. 정치/성인/법적리스크 키워드 필터링
3. 최근 발행 키워드 중복 제거
4. 이슈 에이전트로 글 + Gemini 이미지 생성
5. Tistory 발행 + AdSense 삽입
6. 쿠팡파트너스 관련 상품 링크 삽입
7. Telegram 발행 보고

실행:
    python3 issue_bot.py          # 1회 발행
    python3 issue_bot.py --daemon # 하루 2회 자동 실행 (9~22시 랜덤)

설정 (.env):
    ISSUE_BLOG_ID=issue01
    ISSUE_BLOG_URL=https://issue01.tistory.com
    ISSUE_KAKAO_ID=baremi542
    ISSUE_POSTS_PER_DAY=2
"""
import os
import sys
import re
import json
import time
import random
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, date

sys.path.insert(0, str(Path(__file__).parent))

# .env 로드
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# ─── 설정 ──────────────────────────────────────────────────────────────────
BLOG_ID = os.getenv("ISSUE_BLOG_ID", "issue01")
BLOG_URL = os.getenv("ISSUE_BLOG_URL", f"https://{BLOG_ID}.tistory.com")
KAKAO_ID = os.getenv("ISSUE_KAKAO_ID", "baremi542")   # 티스토리 카카오 계정
POSTS_PER_DAY = int(os.getenv("ISSUE_POSTS_PER_DAY", "2"))
TELEGRAM_CHAT_ID = "8674424194"

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "issue_bot.log"
USED_KEYWORDS_FILE = LOG_DIR / "issue_used_keywords.json"

_log_lines = []


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    _log_lines.append(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ─── 사용 키워드 관리 ────────────────────────────────────────────────────────
def _load_used_keywords() -> set:
    if USED_KEYWORDS_FILE.exists():
        data = json.loads(USED_KEYWORDS_FILE.read_text(encoding="utf-8"))
        # 오늘 날짜 항목만 유지 (당일 중복 방지)
        today = str(date.today())
        return set(data.get(today, []))
    return set()


def _save_used_keyword(keyword: str):
    today = str(date.today())
    data = {}
    if USED_KEYWORDS_FILE.exists():
        data = json.loads(USED_KEYWORDS_FILE.read_text(encoding="utf-8"))
    data.setdefault(today, [])
    if keyword not in data[today]:
        data[today].append(keyword)
    # 오래된 날짜 정리 (최근 7일만 유지)
    from datetime import timedelta
    cutoff = str(date.today() - timedelta(days=7))
    data = {k: v for k, v in data.items() if k >= cutoff}
    USED_KEYWORDS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── 트렌드 키워드 수집 ─────────────────────────────────────────────────────
# 필터링할 민감 키워드
_BLOCK_PATTERNS = [
    # 정치/사회 분열
    r'(대통령|국회|탄핵|계엄|정당|여당|야당|민주당|국민의힘|진보|보수)',
    r'(윤석열|이재명|한동훈|이낙연)',
    # 성인
    r'(성인|야동|포르노|섹스|에로)',
    # 법적 리스크
    r'(불법|도박|마약|사기|범죄)',
    # 종교 분쟁
    r'(이단|사이비|신천지)',
]
_BLOCK_RE = re.compile("|".join(_BLOCK_PATTERNS))


def _is_safe_keyword(kw: str) -> bool:
    return not bool(_BLOCK_RE.search(kw))


def collect_google_trends() -> list:
    """Google Trends 한국 실시간 트렌드 수집 (pytrends 사용)."""
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl='ko', tz=540, timeout=(10, 25))
        df = pytrends.trending_searches(pn='south_korea')
        keywords = df[0].tolist()[:20]
        log(f"[트렌드] Google Trends 수집: {len(keywords)}개")
        return [kw for kw in keywords if isinstance(kw, str) and len(kw) >= 2]
    except ImportError:
        log("[트렌드] pytrends 미설치 — pip install pytrends")
        return []
    except Exception as e:
        log(f"[트렌드] Google Trends 실패: {e}")
        return []


def collect_naver_autocomplete(seed_words: list = None) -> list:
    """Naver 자동완성 API로 인기 키워드 수집."""
    if not seed_words:
        seed_words = ["오늘", "최근", "2026", "요즘", "화제"]
    keywords = []
    for seed in seed_words[:3]:
        try:
            encoded = urllib.parse.quote(seed)
            url = f"https://ac.search.naver.com/nx/ac?q={encoded}&q_enc=UTF-8&st=100&frm=nv&r_format=json&r_enc=UTF-8&r_unicode=0&t_koreng=1&ans=2&run=2&rev=4&callback=_jsonp"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                raw = r.read().decode("utf-8")
            # JSONP → JSON 파싱
            json_str = re.sub(r'^_jsonp\(|\);?\s*$', '', raw.strip())
            data = json.loads(json_str)
            items = data.get("items", [[]])[0]
            for item in items[:5]:
                kw = item[0] if isinstance(item, list) else str(item)
                if len(kw) >= 3:
                    keywords.append(kw)
            time.sleep(0.5)
        except Exception as e:
            log(f"[트렌드] Naver 자동완성 '{seed}' 실패: {e}")
    log(f"[트렌드] Naver 자동완성 수집: {len(keywords)}개")
    return keywords


# 폴백용 한국 트렌드 키워드 로테이션 (pytrends/네이버 모두 실패 시)
_FALLBACK_TOPICS = [
    # 생활정보
    "전기요금 인상 대응법", "건강보험료 절약 방법", "알뜰폰 요금제 비교",
    "2026 최저임금 변화", "실업급여 신청 조건", "청년도약계좌 가입 방법",
    # 소비/생활
    "1인가구 생활비 줄이는 법", "식비 절약 앱 추천", "편의점 할인 활용법",
    "중고거래 안전하게 하는 법", "구독서비스 정리 방법",
    # 건강
    "봄철 알레르기 대처법", "수면 부족 해결법", "눈 피로 해소 방법",
    "정기검진 받는 방법", "치과 치료 비용 절약법",
    # 트렌드
    "AI 활용법 일상", "유튜브 쇼츠 수익화", "스마트폰 배터리 오래 쓰는 법",
    "와이파이 속도 개선법", "클라우드 무료 저장공간 활용",
]
_fallback_idx = 0


def collect_trending_keywords() -> list:
    """트렌드 키워드 수집 — Google Trends → Naver 자동완성 → 폴백 순"""
    keywords = []

    # 1. Google Trends
    gt = collect_google_trends()
    keywords.extend(gt)

    # 2. Naver 자동완성 (보완)
    if len(keywords) < 10:
        nv = collect_naver_autocomplete()
        keywords.extend(nv)

    # 3. 폴백
    if len(keywords) < 5:
        global _fallback_idx
        batch = _FALLBACK_TOPICS[_fallback_idx:_fallback_idx + 10]
        if not batch:
            _fallback_idx = 0
            batch = _FALLBACK_TOPICS[:10]
        keywords.extend(batch)
        _fallback_idx = (_fallback_idx + len(batch)) % len(_FALLBACK_TOPICS)
        log(f"[트렌드] 폴백 키워드 {len(batch)}개 사용")

    # 중복 제거
    seen = set()
    result = []
    for kw in keywords:
        kw = kw.strip()
        if kw and kw not in seen:
            seen.add(kw)
            result.append(kw)

    log(f"[트렌드] 총 수집: {len(result)}개")
    return result


def pick_keyword(candidates: list) -> str | None:
    """필터링 + 중복 제거 후 최적 키워드 선택."""
    used = _load_used_keywords()
    safe = [kw for kw in candidates if _is_safe_keyword(kw) and kw not in used]
    if not safe:
        log("[키워드] 사용 가능한 키워드 없음")
        return None

    # 롱테일 우선 (단어 2개 이상 선호)
    longtail = [kw for kw in safe if len(kw.split()) >= 2 or len(kw) >= 6]
    chosen = random.choice(longtail) if longtail else random.choice(safe)
    log(f"[키워드] 선택: '{chosen}'")
    return chosen


# ─── 발행 시간 관리 ──────────────────────────────────────────────────────────
PUBLISH_TIMES_FILE = LOG_DIR / "blog_publish_times.json"


def _get_last_publish_time() -> float:
    """마지막 발행 시각 (Unix timestamp)."""
    if PUBLISH_TIMES_FILE.exists():
        data = json.loads(PUBLISH_TIMES_FILE.read_text(encoding="utf-8"))
        ts_str = data.get(BLOG_ID, "")
        if ts_str:
            try:
                dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                return dt.timestamp()
            except Exception:
                pass
    return 0.0


def _can_publish_now(min_interval_hours: float = 3.5) -> bool:
    last = _get_last_publish_time()
    if last == 0:
        return True
    elapsed = (datetime.now().timestamp() - last) / 3600
    if elapsed < min_interval_hours:
        log(f"[간격] 마지막 발행 {elapsed:.1f}h 전 — {min_interval_hours}h 미충족")
        return False
    return True


def _update_publish_time():
    data = {}
    if PUBLISH_TIMES_FILE.exists():
        data = json.loads(PUBLISH_TIMES_FILE.read_text(encoding="utf-8"))
    data[BLOG_ID] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    PUBLISH_TIMES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ─── 쿠팡 링크 삽입 ─────────────────────────────────────────────────────────
def _insert_coupang_link(body: str, keyword: str) -> str:
    """본문에 쿠팡파트너스 관련 상품 링크 삽입 (본문 끝 추천 섹션)."""
    try:
        from coupang_api import search_products
        products = search_products(keyword, limit=2)
        if not products:
            return body
        links_html = "\n".join(
            f'<p>👉 <a href="{p["url"]}" target="_blank" rel="noopener">{p["name"]}</a></p>'
            for p in products
        )
        section = f'\n\n##H2:관련 상품##\n{links_html}\n<p><small>이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.</small></p>'
        return body + section
    except Exception as e:
        log(f"[쿠팡] 링크 삽입 실패 (무시): {e}")
        return body


# ─── Tistory 발행 ────────────────────────────────────────────────────────────
def publish_to_tistory(result: dict, keyword: str) -> bool:
    """Tistory에 발행한다. poster.py의 기존 로직 활용."""
    from browser import connect_cdp, get_or_create_page
    from login_playwright import login_blog
    from poster import post_single
    from config import ACCOUNT_MAP

    account = ACCOUNT_MAP.get(BLOG_ID)
    if not account:
        log(f"[발행] ⚠ config에 {BLOG_ID} 없음 — config.py에 블로그 추가 필요")
        return False

    try:
        pw, browser, ctx = connect_cdp()
        page = get_or_create_page(ctx, account["editor_url"])

        # 쿠팡 링크 삽입
        result["body"] = _insert_coupang_link(result["body"], keyword)

        ok = post_single(
            page=page,
            blog_id=BLOG_ID,
            title=result["title"],
            body=result["body"],
            tags=result["tags"],
            images=result["images"],
            image_paths=result["image_paths"],
            account=account,
            on_log=log,
        )

        pw.stop()
        return ok
    except Exception as e:
        log(f"[발행] 오류: {e}")
        import traceback
        log(traceback.format_exc())
        return False


# ─── Telegram 보고 ───────────────────────────────────────────────────────────
def _telegram_notify(title: str, success: bool, keyword: str, notes: list = None):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return
    if success:
        msg = (
            f"✅ 발행 완료\n"
            f"블로그: {BLOG_ID}\n"
            f"키워드: {keyword}\n"
            f"제목: {title}\n"
            f"발행시각: {datetime.now().strftime('%H:%M')}\n"
        )
        if notes:
            msg += "\n🔧 검수 수정:\n" + "\n".join(f"- {n}" for n in notes)
        else:
            msg += "\n🔧 검수: 이상 없음"
    else:
        msg = f"❌ 발행 실패\n블로그: {BLOG_ID}\n키워드: {keyword}"

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": msg}).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log(f"[텔레그램] 알림 실패: {e}")


# ─── 발행 품질 검수 ──────────────────────────────────────────────────────────
def quality_check(result: dict) -> tuple[bool, list]:
    """발행 전 품질 검수. (pass, notes) 반환."""
    notes = []
    body = result.get("body", "")

    # 마크다운 잔재
    md_found = re.findall(r'\*\*[^*]+\*\*|^#{1,3}\s', body, re.MULTILINE)
    if md_found:
        result["body"] = re.sub(r'\*\*([^*]+)\*\*', r'\1', body)
        result["body"] = re.sub(r'^#{1,3}\s+(.+)$', r'##H2:\1##', result["body"], flags=re.MULTILINE)
        notes.append("마크다운 잔재 제거")
        body = result["body"]

    # 내부 마커
    markers = re.findall(r'\[(검증 필요|출처 필요|TODO|확인 필요)[^\]]*\]', body)
    if markers:
        result["body"] = re.sub(r'\[(검증 필요|출처 필요|TODO|확인 필요)[^\]]*\]', '', body)
        notes.append(f"내부 마커 제거: {markers[:3]}")
        body = result["body"]

    # 글자수
    plain = re.sub(r'##[^#]+##|\{\{[^}]+\}\}|\s+', '', body)
    char_count = len(plain)
    if char_count < 1700:
        log(f"[검수] ⚠ 글자수 부족: {char_count}자 (1700자 기준)")
        return False, notes + [f"글자수 부족: {char_count}자"]

    # 이미지
    img_count = len(result.get("image_paths", {}))
    if img_count < 3:
        log(f"[검수] ⚠ 이미지 부족: {img_count}장")
        return False, notes + [f"이미지 부족: {img_count}장"]

    return True, notes


# ─── 1회 실행 ────────────────────────────────────────────────────────────────
def run_once() -> bool:
    """트렌드 수집 → 글 생성 → 검수 → 발행. 성공 여부 반환."""
    log("=" * 50)
    log(f"[이슈봇] 실행 시작 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 발행 간격 확인
    if not _can_publish_now(min_interval_hours=3.5):
        return False

    # 트렌드 키워드 수집
    candidates = collect_trending_keywords()
    keyword = pick_keyword(candidates)
    if not keyword:
        log("[이슈봇] 적합한 키워드 없음 — 종료")
        return False

    _save_used_keyword(keyword)

    # 글 + 이미지 생성
    from agents.issue_agent import run as agent_run
    log(f"[이슈봇] 에이전트 실행: '{keyword}'")
    result = agent_run(keyword, on_log=log)

    if not result:
        log("[이슈봇] 글 생성 실패")
        _telegram_notify("(생성 실패)", False, keyword)
        return False

    # 품질 검수
    ok, notes = quality_check(result)
    if not ok:
        log(f"[이슈봇] 검수 실패: {notes}")
        _telegram_notify(result.get("title", ""), False, keyword, notes)
        return False

    # 발행
    log(f"[이슈봇] 발행 시작: '{result['title']}'")
    pub_ok = publish_to_tistory(result, keyword)

    if pub_ok:
        _update_publish_time()
        log(f"[이슈봇] ✅ 발행 완료: '{result['title']}'")
        _telegram_notify(result["title"], True, keyword, notes)
    else:
        log("[이슈봇] ❌ 발행 실패")
        _telegram_notify(result.get("title", ""), False, keyword)

    return pub_ok


# ─── 데몬 스케줄러 ───────────────────────────────────────────────────────────
def run_daemon():
    """하루 POSTS_PER_DAY회 9~22시 사이 랜덤 발행."""
    import signal

    _running = True
    def _stop(sig, frame):
        nonlocal _running
        log("[이슈봇] 종료 신호 수신")
        _running = False
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    log(f"[이슈봇] 데몬 시작 — 하루 {POSTS_PER_DAY}회 발행 예정")

    today_count = 0
    today_date = date.today()
    next_run_times = _schedule_today()
    log(f"[이슈봇] 오늘 발행 예정 시각: {[t.strftime('%H:%M') for t in next_run_times]}")

    while _running:
        now = datetime.now()

        # 날짜 바뀌면 스케줄 재설정
        if now.date() != today_date:
            today_date = now.date()
            today_count = 0
            next_run_times = _schedule_today()
            log(f"[이슈봇] 새 날짜 — 오늘 예정: {[t.strftime('%H:%M') for t in next_run_times]}")

        # 예약 시각 도달 확인
        for rt in list(next_run_times):
            if now >= rt:
                next_run_times.remove(rt)
                if today_count < POSTS_PER_DAY:
                    log(f"[이슈봇] 예약 시각 도달: {rt.strftime('%H:%M')}")
                    ok = run_once()
                    if ok:
                        today_count += 1
                        log(f"[이슈봇] 오늘 {today_count}/{POSTS_PER_DAY}회 완료")

        time.sleep(60)

    log("[이슈봇] 데몬 종료")


def _schedule_today() -> list:
    """오늘 발행 예정 시각 목록 생성 (9~22시 사이 랜덤)."""
    from datetime import timedelta

    now = datetime.now()
    slots = []
    # 오전 (9~13시), 오후 (15~21시) 각 1개씩
    morning_h = random.randint(9, 12)
    morning_m = random.randint(0, 59)
    afternoon_h = random.randint(15, 20)
    afternoon_m = random.randint(0, 59)

    times = [
        datetime(now.year, now.month, now.day, morning_h, morning_m),
        datetime(now.year, now.month, now.day, afternoon_h, afternoon_m),
    ]
    # 이미 지난 시각 제외
    times = [t for t in times if t > now]
    return times[:POSTS_PER_DAY]


# ─── 진입점 ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if "--daemon" in sys.argv:
        run_daemon()
    else:
        success = run_once()
        sys.exit(0 if success else 1)
