"""야간 자동 실행 — 키워드 수집 → 글 생성 → 포스팅"""
import os
import re
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "overnight_result.txt"

# .env 로드
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

logs = []

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    logs.append(line)


def save_log():
    LOG_FILE.write_text("\n".join(logs), encoding="utf-8")
    log(f"로그 저장: {LOG_FILE}")


def _ssl_ctx():
    """SSL 인증서 검증 비활성화 컨텍스트 (자체 서명 인증서 대응용)"""
    import ssl as _ssl
    ctx = _ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _ssl.CERT_NONE
    return ctx


# ─── 블로그 테마 적합성 검사 ───
_BLOG_THEMES = {
    "nolja100": ["여행", "관광", "숙소", "맛집", "코스", "캠핑", "펜션", "호텔", "드라이브",
                 "당일치기", "트레킹", "등산", "해수욕", "바다", "산", "계곡", "레저", "축제",
                 "케이블카", "한옥", "올레길", "둘레길", "차박", "글램핑", "리조트",
                 "벚꽃", "단풍", "매화", "유채꽃", "군항제", "꽃놀이", "나들이", "피크닉",
                 "주차", "입장료", "운영시간", "명소", "포토스팟", "뷰", "야경", "산책",
                 "가볼만한", "여행지", "추천", "봄여행", "봄나들이",
                 "경주", "하동", "광양", "진해", "여의도", "안양", "왕십리",
                 # 해외 여행
                 "해외여행", "다낭", "세부", "방콕", "오사카", "도쿄", "대만", "타이베이",
                 "싱가포르", "발리", "파리", "나트랑", "하노이", "하롱베이", "코타키나발루",
                 "홍콩", "마카오", "후쿠오카", "교토", "나라", "비자", "환전", "유심",
                 "항공권", "패키지", "자유여행", "배낭여행", "4박5일", "3박4일", "일정"],
    "salim1su": ["살림", "절약", "가스", "전기", "요금", "주방", "청소", "정리", "수납",
                 "가계", "생활비", "난방", "냉방", "가전", "요리", "레시피", "기름때",
                 "세탁", "빨래", "냉장고", "에어컨", "보일러", "다이소",
                 "화장실", "욕실", "물때", "곰팡이", "집안", "먼지", "바닥", "베란다",
                 "주부", "신혼", "인테리어", "수납", "정돈", "소독", "탈취", "제거",
                 "관리비", "수도", "가습기", "건조기", "식기", "행주", "찌든"],
    "goodisak": ["아이폰", "갤럭시", "스마트폰", "노트북", "태블릿", "AI", "앱", "앱스토어",
                 "카드", "적금", "예금", "투자", "주식", "펀드", "청약",
                 "페이", "포인트", "캐시백", "환전", "핀테크", "은행", "증권",
                 "IT", "기술", "소프트웨어", "하드웨어", "가전", "전자",
                 # 추가: 실제 IT 키워드 패턴
                 "구글", "카카오", "네이버", "유튜브", "인스타", "틱톡", "챗", "GPT",
                 "드라이브", "클라우드", "와이파이", "블루투스", "USB", "충전",
                 "이어폰", "헤드폰", "스피커", "마우스", "키보드", "모니터", "웹캠",
                 "요금제", "통신", "SKT", "KT", "LG유플", "알뜰폰",
                 "삼성", "LG", "애플", "소니", "다이슨",
                 "스마트워치", "워치", "패드", "이커머스", "쇼핑", "배달",
                 "연금", "세금", "절세", "환급", "공제", "신용점수"],
    "baremi542": ["지원금", "보조금", "지원사업", "복지", "수당", "혜택", "신청", "환급",
                  "정부", "공공", "청년", "취업", "바우처", "감면", "지원"],
    "triplog": ["호텔", "항공", "맛집", "국내여행", "해외여행", "여행", "숙소", "리조트",
                "투어", "관광", "비행기", "티켓", "패키지", "배낭여행", "자유여행",
                "가볼만한", "여행지", "추천", "코스", "일정", "경비", "항공권", "렌터카", "렌트카",
                "당일치기", "트레킹", "등산", "바다", "계곡", "축제", "글램핑", "캠핑", "펜션"],
    "woll100": ["공항", "공항버스", "리무진버스", "시외버스", "교통", "시간표", "요금", "소요시간",
                "예매", "정류장", "인천공항", "김포공항", "김해공항", "제주공항", "대구공항",
                "청주공항", "무안공항", "KTX", "SRT", "GTX", "공항철도", "버스", "노선", "출발", "도착",
                "렌트카", "렌터카", "주차", "환승", "셔틀", "고속버스", "첫차", "막차", "배차",
                "교통카드", "지하철", "전철", "신분당선", "MRT", "신칸센", "JR패스", "ICOCA"],
    "phn0502": ["영화", "넷플릭스", "왓챠", "웨이브", "티빙", "OTT", "결말", "줄거리", "해석",
                "쿠키영상", "등장인물", "배우", "출연작", "근황", "추천", "신작", "장르",
                "액션", "로맨스", "스릴러", "공포", "애니", "드라마", "시리즈"],
    "me1091":  ["리뷰", "후기", "추천", "사용기", "써봤어요", "솔직", "장단점", "비교",
                "구매", "쿠팡", "다이소", "생활용품", "주방용품", "청소용품", "뷰티",
                "화장품", "스킨케어", "헤어", "건강", "건강식품", "영양제", "다이어트",
                "가전", "소형가전", "주방가전", "가성비", "핫딜", "신상", "베스트"],
    # Blogspot 블로그 — 테마 제한 없음
    "blogspot_daily": [],   # Korea travel for foreigners (English)
    "blogspot_travel": [],  # 한국어 여행 블로그
    "blogspot_it": [],      # IT/테크 영어 블로그
}


def is_keyword_suitable(blog_id: str, keyword: str) -> bool:
    """키워드가 블로그 테마에 적합한지 확인"""
    # goodisak(Tistory): 대출 관련 키워드 차단
    if blog_id == "goodisak":
        _LOAN_BLOCK = ["대출", "금리", "대출비교", "신용대출", "주택담보대출", "카드론", "대출이자", "대출금리", "핀다",
                       "보험", "보험료", "보험사", "실비보험", "자동차보험", "생명보험", "종신보험", "의료보험"]
        if any(w in keyword for w in _LOAN_BLOCK):
            return False

    # baremi542: 법률/법령 관련 키워드 차단 (정부지원/복지만 허용)
    if blog_id == "baremi542":
        _LAW_BLOCK = ["법", "법률", "법령", "법조문", "조항", "형법", "민법", "상법",
                      "고용보험법", "산재법", "근로기준법", "소득세법", "부가세법",
                      "법안", "법원", "소송", "판결", "재판", "변호사", "법적"]
        if any(w in keyword for w in _LAW_BLOCK):
            return False

    theme_words = _BLOG_THEMES.get(blog_id)
    if not theme_words:
        return True
    return any(w in keyword for w in theme_words)



def _naver_competition_check(keyword: str, on_log=None) -> bool:
    """Naver 검색결과 수 확인. 경쟁 너무 심하면 False 반환."""
    # 공백 포함 키워드: 2단어 이상 필요
    # 공백 없는 한국어 복합어: 7자 이상이면 롱테일 키워드로 허용
    words = keyword.strip().split()
    if len(words) < 2:
        # 공백 없는 단어 — 글자 수로 판단 (7자 미만은 경쟁도 높음)
        if len(keyword.strip()) < 7:
            if on_log: on_log(f"[경쟁도] '{keyword}' 너무 짧음({len(keyword.strip())}자) — 롱테일 아님 스킵")
            return False
        return True
    if len(keyword) < 7:
        if on_log: on_log(f"[경쟁도] '{keyword}' 너무 짧음({len(keyword)}자) — 롱테일 아님 스킵")
        return False
    return True


def _extract_core_words(keyword, blog_id=None):
    """키워드에서 핵심 단어를 추출한다.

    예: "도시가스 요금 절약" → ["도시가스", "요금", "절약"]
    1글자 단어, 조사, 일반 접속사는 제외.
    blog_id가 있으면 블로그별 stop words 조정.
    """
    STOP_WORDS = {
        '방법', '추천', '정리', '비교', '후기', '종류', '가이드',
        '및', '또는', '그리고', '하는', '위한', '대한', '좋은', '최고',
        '가장', '진짜', '완벽', '꿀팁', '팁', '꿀',
        # 여행/블로그 자주 쓰는 수식어
        '코스', '여행', '일정', '동선', '정복', '완주', '완전', '정보',
        '소개', '총정리', '핵심', '필수', '최신', '2026', '2025',
        # 교통/공항 관련 일반 수식어 (이것만으로 중복 판정 금지)
        '시간표', '요금', '노선', '운행', '탑승', '예약',
    }
    # woll100: 요금/시간표/소요시간이 교통 블로그의 핵심 식별어 → stop word에서 제외
    if blog_id == 'woll100':
        STOP_WORDS -= {'시간표', '요금', '노선', '운행', '탑승', '예약'}
        STOP_WORDS.add('소요시간')  # '소요시간'은 아직 일반 수식어로 유지
    # phn0502: OTT 플랫폼명은 모든 키워드에 포함되므로 첫 단어로 중복 판정하면 안 됨
    elif blog_id == 'phn0502':
        STOP_WORDS.update({'넷플릭스', '웨이브', '왓챠', '티빙', '시즌', '쿠팡플레이', '디즈니'})
    words = keyword.split()
    core = [w for w in words if len(w) >= 2 and w not in STOP_WORDS]
    return core if core else words[:2]



def check_duplicate_post(blog_id, keyword, on_log=None):
    """블로그 타입에 맞게 중복 글 여부를 확인한다.

    1단계: SQLite DB에서 이미 발행/임시저장된 유사 키워드 확인 (모든 블로그 공통)
    2단계: 블로그별 실제 발행 글 검색 (Naver/WP/Tistory 각각 다른 방법)

    Returns: (is_duplicate: bool, matched_title: str or None)
    """
    def _log(msg):
        if on_log:
            on_log(msg)

    core_words = _extract_core_words(keyword, blog_id=blog_id)
    _log(f"[유사문서] 핵심 단어: {core_words}")

    # ── 1단계: SQLite DB 중복 체크 (모든 블로그 공통) ─────────────────
    # 메인키워드 = 핵심어 중 첫 번째 (가장 주제-특정적 단어)
    main_kw = core_words[0] if core_words else keyword.split()[0]
    try:
        from keyword_engine.db_handler import _conn
        with _conn() as db:
            rows = db.execute(
                """SELECT keyword FROM keyword_blog_status
                   WHERE blog_id = ? AND status IN ('published', 'draft_saved', 'in_progress')
                   AND keyword != ?""",
                (blog_id, keyword),
            ).fetchall()
        existing_keywords = [r[0] for r in rows]
        for ek in existing_keywords:
            ek_core = _extract_core_words(ek, blog_id=blog_id)
            ek_main = ek_core[0] if ek_core else ek.split()[0]
            # ① 메인키워드 일치 → 중복 판단 (단, 3글자 이하 장소명이 첫 단어인 경우 추가 단어도 겹쳐야 함)
            # 예: "가스레인지 청소" vs "가스레인지 청소 방법" → 중복 O
            # 반례: "서울 김포공항 시간표" vs "서울 인천공항 시간표" → 첫 단어만 같고 내용은 달라서 중복 X
            if main_kw == ek_main:
                if len(core_words) >= 3 or len(main_kw) <= 2:
                    # 짧은 장소명(서울, 인천, 부산 등) 또는 키워드가 길면
                    # 2번째 핵심어도 일치해야 중복으로 판정
                    # 예: "서울 김포공항" vs "서울 인천공항" → 2번째가 다르면 중복 X

                    # 기존 키워드가 1단어(예: '부산 여행 코스' → core=['부산'])이고
                    # 현재 키워드가 더 구체적(2단어 이상)이면 중복 아님
                    # 예: '부산 김해공항 리무진버스' vs '부산 여행 코스'(core=['부산']) → 중복 X
                    if len(ek_core) < 2 and len(core_words) >= 2:
                        continue

                    if len(ek_core) >= 2 and len(core_words) >= 2 and core_words[1] != ek_core[1]:
                        continue  # 2번째 핵심어 다름 → 중복 아님

                    # 기존 키워드가 2단어이고 현재 키워드가 3단어 이상이면 더 구체적 → 중복 아님
                    # 예: '서울 제주공항'(ek_core 2개) vs '서울 제주공항 리무진버스'(3개) → 중복 X
                    if len(ek_core) == 2 and len(core_words) >= 3:
                        continue

                    # 3번째 핵심어까지 있으면 추가 비교
                    # 예: "서울 김포공항 요금" vs "서울 김포공항 시간표" → 3번째가 다르면 중복 X
                    if len(core_words) >= 3 and len(ek_core) >= 3 and core_words[2] != ek_core[2]:
                        continue  # 3번째 핵심어 다름 → 중복 아님
                _log(f"[유사문서] ⚠ DB 메인키워드 중복: '{ek}' (메인: '{main_kw}')")
                return True, ek
            # ② 핵심 단어 겹침 체크 (교통 키워드 오탐 방지: 최소 3개 & 60% 이상)
            # 예: '대구공항 리무진버스 시간표 요금' vs '서울 대구공항 시간표' → 겹침 2개만으로 차단 X
            ek_core_set = set(ek_core)
            kw_core = set(core_words)
            overlap = ek_core_set & kw_core
            if len(overlap) >= max(3, len(kw_core) * 0.6):
                _log(f"[유사문서] ⚠ DB 중복 키워드: '{ek}' (겹침: {overlap})")
                return True, ek
    except Exception as e:
        _log(f"[유사문서] DB 체크 실패: {e}")

    # ── 2단계: 블로그별 실제 발행 글 확인 ───────────────────────────
    WP_BLOGS = {
        "baremi542": ("TRIPLOG_WP_URL", "TRIPLOG_WP_USER", "TRIPLOG_WP_APP_PASSWORD"),  # 오타 방어
        "triplog":   ("TRIPLOG_WP_URL", "TRIPLOG_WP_USER", "TRIPLOG_WP_APP_PASSWORD"),
    }
    # remote_secrets.json에서 실제 키 확인
    try:
        _sec = json.loads(Path(__file__).parent.joinpath("remote_secrets.json").read_text())
    except Exception:
        _sec = {}

    if blog_id == "baremi542":
        _wp_url = _sec.get("WP_URL", "")
        _wp_user = _sec.get("WP_USER", "")
        _wp_pass = _sec.get("WP_APP_PASSWORD", "")
    elif blog_id == "triplog":
        _wp_url = _sec.get("TRIPLOG_WP_URL", "")
        _wp_user = _sec.get("TRIPLOG_WP_USER", "")
        _wp_pass = _sec.get("TRIPLOG_WP_APP_PASSWORD", "")
    else:
        _wp_url = _wp_user = _wp_pass = ""

    if _wp_url and _wp_user:
        # WordPress REST API로 유사 제목 검색 (최대 2회 재시도)
        import base64 as _b64
        _auth = _b64.b64encode(f"{_wp_user}:{_wp_pass}".encode()).decode()
        _search_q = urllib.parse.urlencode({"search": " ".join(core_words[:3]), "per_page": 20, "status": "publish"})
        _req = urllib.request.Request(
            f"{_wp_url}/wp-json/wp/v2/posts?{_search_q}",
            headers={"Authorization": f"Basic {_auth}"},
        )
        _posts = None
        for _attempt in range(2):
            try:
                with urllib.request.urlopen(_req, timeout=15, context=_ssl_ctx()) as _r:
                    _posts = json.loads(_r.read())
                break
            except Exception as e:
                _log(f"[유사문서] WP 검색 실패 (시도 {_attempt+1}/2): {e}")
        if _posts is not None:
            for p in _posts:
                title = re.sub(r'<[^>]+>', '', p.get("title", {}).get("rendered", ""))
                match_count = sum(1 for w in core_words if w in title)
                _wp_thresh = len(core_words) if len(core_words) <= 3 else max(3, int(len(core_words) * 0.75))
                if match_count >= _wp_thresh:
                    _log(f"[유사문서] ⚠ WP 중복 발견: \"{title}\" (id={p['id']})")
                    return True, title
            _log(f"[유사문서] WP 검색 완료 — {len(_posts)}개 중 중복 없음")

    elif blog_id in ("nolja100", "goodisak", "woll100", "phn0502"):
        # Tistory RSS로 최근 글 확인
        TISTORY_RSS = {
            "nolja100": "https://issue.baremi542.com/rss",
            "goodisak": "https://welfare.baremi542.com/rss",
            "woll100":  "https://info.baremi542.com/rss",
            "phn0502":  "https://film.baremi542.com/rss",
        }
        rss_url = TISTORY_RSS.get(blog_id, "")
        if rss_url:
            try:
                _ctx2 = _ssl_ctx()
                _rreq = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(_rreq, timeout=10, context=_ctx2) as _r:
                    _rss = _r.read().decode("utf-8", errors="ignore")
                _rtitles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', _rss)
                if not _rtitles:
                    _rtitles = re.findall(r'<title>(.*?)</title>', _rss)
                _log(f"[유사문서] Tistory RSS {len(_rtitles)-1}개 제목 수집")
                for t in _rtitles[1:21]:  # 첫 번째는 블로그 제목
                    t_clean = re.sub(r'<[^>]+>', '', t).strip()
                    match_count = sum(1 for w in core_words if w in t_clean)
                    # 3단어 이상 키워드: 전부 일치해야 중복 판정 (2/3 일치는 오탐 너무 많음)
                    _rss_thresh = len(core_words) if len(core_words) <= 3 else max(3, int(len(core_words) * 0.75))
                    if match_count >= _rss_thresh:
                        _log(f"[유사문서] ⚠ Tistory RSS 중복: \"{t_clean}\"")
                        return True, t_clean
                _log(f"[유사문서] Tistory RSS 확인 완료 — 중복 없음 (최근 20개)")
                # RSS는 최근 글만 포함 → Tistory 검색 API로 전체 글 추가 확인
                TISTORY_DOMAINS = {
                    "nolja100": "issue.baremi542.com",
                    "goodisak": "welfare.baremi542.com",
                    "woll100":  "info.baremi542.com",
                    "phn0502":  "film.baremi542.com",
                }
                _domain = TISTORY_DOMAINS.get(blog_id, "")
                if _domain and core_words:
                    try:
                        _search_q = urllib.parse.quote(" ".join(core_words[:2]))
                        _search_url = f"https://{_domain}/search/{_search_q}"
                        _sreq = urllib.request.Request(_search_url, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(_sreq, timeout=10, context=_ctx2) as _r:
                            _shtml = _r.read().decode("utf-8", errors="ignore")
                        _stitles = re.findall(r'<h3[^>]*class="[^"]*tit[^"]*"[^>]*>(.*?)</h3>', _shtml, re.S)
                        if not _stitles:
                            _stitles = re.findall(r'<a[^>]+class="[^"]*link[^"]*"[^>]*>(.*?)</a>', _shtml, re.S)
                        for _st in _stitles[:20]:
                            _st_clean = re.sub(r'<[^>]+>', '', _st).strip()
                            if not _st_clean:
                                continue
                            # Tistory 사이드바 카테고리/검색헤더 필터: "제목 (숫자)" 패턴 제외
                            if re.search(r'\(\d+\)\s*$', _st_clean):
                                continue
                            _mc = sum(1 for w in core_words if w in _st_clean)
                            if _mc >= max(2, len(core_words) * 0.5):
                                _log(f"[유사문서] ⚠ Tistory 검색 중복: \"{_st_clean}\"")
                                return True, _st_clean
                        _log(f"[유사문서] Tistory 검색 확인 완료 — 중복 없음")
                    except Exception as _se:
                        _log(f"[유사문서] Tistory 검색 실패: {_se}")
            except Exception as e:
                _log(f"[유사문서] Tistory RSS 실패: {e}")

    elif blog_id == "salim1su":
        # 기존 Naver 블로그 검색
        search_query = "+".join(core_words)
        search_url = (
            f"https://blog.naver.com/PostSearchList.naver?"
            f"blogId={blog_id}&searchText={urllib.parse.quote(search_query)}"
            f"&orderType=sim&directAccess=false"
        )
        try:
            req = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as _r:
                html = _r.read().decode("utf-8", errors="ignore")
            titles = re.findall(r'<span class="ell">(.*?)</span>', html)
            if not titles:
                titles = re.findall(r'class="pcol2"[^>]*>(.*?)</a>', html)
            clean_titles = [re.sub(r'<[^>]+>', '', t).strip() for t in titles if len(t) > 5]
            _log(f"[유사문서] Naver 검색 결과 {len(clean_titles)}개")
            for t in clean_titles[:10]:
                match_count = sum(1 for w in core_words if w in t)
                if match_count >= 2 or (len(core_words) == 1 and match_count >= 1):
                    _log(f"[유사문서] ⚠ Naver 중복: \"{t}\"")
                    return True, t
            _log(f"[유사문서] Naver 검색 완료 — 중복 없음")
        except Exception as e:
            _log(f"[유사문서] Naver 검색 실패: {e}")

    _log(f"[유사문서] 중복 없음 — 진행 가능")
    return False, None


def _truncate_title(title, max_len=40):
    """제목을 max_len자(기본 40자) 이내로 자른다.

    40자 초과 시:
    1. 구두점(.?!)에서 자르기 (20~40자 범위)
    2. 공백(띄어쓰기)에서 자르기 — 명사 뒤 단어 경계
    3. 조사/접속사 뒤면 한 단어 더 앞으로 (은/는/이/가/을/를/에/의/로/와/과/도/만)
    4. 그래도 없으면 max_len자 강제 자르기
    """
    # 본문 혼입 방지: 줄바꿈이 있으면 첫 줄만
    title = title.split('\n')[0].strip()

    if len(title) <= max_len:
        return title

    # 1. 20~max_len 범위에서 마지막 구두점 찾기
    for i in range(min(max_len, len(title)) - 1, 19, -1):
        if title[i] in '.?!。？！':
            return title[:i + 1]

    # 2. 공백(단어 경계)에서 자르기 — 조사 뒤 자르기 방지
    # 한국어 조사 패턴: 1~2글자 (은,는,이,가,을,를,에,의,로,와,과,도,만,에서,으로,까지,부터)
    JOSA = {'은', '는', '이', '가', '을', '를', '에', '의', '로', '와', '과',
            '도', '만', '에서', '으로', '까지', '부터', '에게', '한테', '처럼'}

    # max_len 이내에서 마지막 공백 위치들 (뒤에서부터)
    for i in range(min(max_len, len(title)) - 1, 14, -1):
        if title[i] == ' ':
            # 공백 앞 단어가 조사인지 확인
            before_space = title[:i]
            last_word = before_space.split()[-1] if before_space.split() else ""
            if last_word in JOSA:
                continue  # 조사 뒤에서 자르면 어색 → 건너뜀
            return title[:i]

    # 3. 강제 자르기
    return title[:max_len]


# ─── 내부링크 삽입 ───
_BLOG_RSS = {
    "nolja100": ("https://issue.baremi542.com/rss", "https://issue.baremi542.com"),
    "goodisak": ("https://welfare.baremi542.com/rss", "https://welfare.baremi542.com"),
    "woll100":  ("https://info.baremi542.com/rss", "https://info.baremi542.com"),
    "phn0502":  ("https://film.baremi542.com/rss", "https://film.baremi542.com"),
    "triplog":  ("https://app.baremi542.com/feed", "https://app.baremi542.com"),
    "baremi542": ("https://baremi542.com/feed", "https://baremi542.com"),
}


_TISTORY_BLOGS = {"goodisak", "nolja100", "woll100", "phn0502"}  # HTML이 에디터에서 이스케이프되므로 제외

# ─── triplog → nolja100 교차 백링크 ───
_CROSSLINK_FILE = LOG_DIR / "crosslink_urls.json"

def _naver_short_url(url: str) -> str:
    """네이버 qr.naver.com/create 3단계 폼으로 m.site.naver.com 단축 URL 생성 (실패 시 원본 반환)"""
    import re as _re
    try:
        from playwright.sync_api import sync_playwright as _spw
        _pw = _spw().start()
        try:
            _browser = _pw.chromium.connect_over_cdp("http://localhost:9222")
            _ctx = _browser.contexts[0]

            # naver.com 탭 재사용
            _page = None
            for _p in _ctx.pages:
                if "naver.com" in _p.url:
                    _page = _p
                    break
            if not _page:
                _page = _ctx.new_page()

            log("[단축URL] qr.naver.com/create 이동...")
            _page.goto("https://qr.naver.com/create", wait_until="networkidle", timeout=30000)
            _page.wait_for_timeout(2000)

            if "nidlogin" in _page.url or "login" in _page.url:
                log("[단축URL] Naver 로그인 필요 — 원본 URL 반환")
                return url

            def _js_click(sel_text):
                _page.evaluate(f"""() => {{
                    const btns = Array.from(document.querySelectorAll('button'));
                    const btn = btns.find(b => b.innerText.trim() === '{sel_text}');
                    if (btn) btn.click();
                }}""")

            # 단계1 → 2: 다음 클릭
            _js_click("다음")
            _page.wait_for_timeout(1500)

            # 단계2: URL 링크 선택 → 다음
            _page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button, label'));
                const urlBtn = btns.find(b => b.innerText.includes('URL 링크'));
                if (urlBtn) urlBtn.click();
            }""")
            _page.wait_for_timeout(500)
            _js_click("다음")
            _page.wait_for_timeout(1500)

            # 단계3: 제목 입력 (필수)
            _page.evaluate("""() => {
                const inputs = document.querySelectorAll('input[type="text"]');
                for (const inp of inputs) {
                    if (inp.placeholder && inp.placeholder.includes('제목')) {
                        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        setter.call(inp, '카카오맵 네이버지도 비교');
                        ['input', 'change'].forEach(ev => inp.dispatchEvent(new Event(ev, {bubbles: true})));
                        break;
                    }
                }
            }""")
            _page.wait_for_timeout(300)

            # 단계3: URL 입력 (JS 이벤트 방식)
            _safe_url = url.replace("'", "\\'")
            _page.evaluate(f"""() => {{
                const inp = document.querySelector('input[name="sections[1].url"], input[placeholder="https://"]');
                if (inp) {{
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    setter.call(inp, '{_safe_url}');
                    ['input', 'change', 'blur'].forEach(ev => inp.dispatchEvent(new Event(ev, {{bubbles: true}})));
                }}
            }}""")
            _page.wait_for_timeout(300)

            # 링크첨부 버튼 클릭
            _page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const btn = btns.find(b => b.innerText.includes('링크첨부'));
                if (btn) btn.click();
            }""")
            _page.wait_for_timeout(1000)

            # 팝업(오류) 있으면 닫기
            try:
                popup_ok = _page.locator("[role='dialog'] button:has-text('확인')")
                if popup_ok.count() > 0:
                    popup_ok.click()
                    _page.wait_for_timeout(500)
            except Exception:
                pass

            # 다음 (최종 생성)
            _js_click("다음")
            _page.wait_for_timeout(3000)

            # 결과에서 m.site.naver.com URL 추출
            _content = _page.evaluate("() => document.body.innerText")
            for _pat in [
                r'https?://m\.site\.naver\.com/[A-Za-z0-9]+',
                r'https?://naver\.me/[A-Za-z0-9]+',
            ]:
                _matches = _re.findall(_pat, _content)
                if _matches:
                    log(f"[단축URL] 생성 성공: {_matches[0]}")
                    return _matches[0]

            log("[단축URL] 단축URL 추출 실패 — 원본 반환")
        finally:
            _pw.stop()
    except Exception as e:
        log(f"[단축URL] 변환 실패 (원본 사용): {e}")
    return url


def _store_crosslink_url(keyword: str, url: str, tier: str = "triplog"):
    """발행 URL을 키워드+계층별로 저장 (링크 피라미드 체인용).
    tier: 'triplog' | 'baremi542' | 'blogspot_travel' | 'blogspot_it'
    """
    try:
        data = json.loads(_CROSSLINK_FILE.read_text()) if _CROSSLINK_FILE.exists() else {}
    except Exception:
        data = {}
    entry = data.get(keyword, {})
    # 구 형식({url, ts}) → 신 형식({tier: {url, ts}}) 자동 마이그레이션
    if "url" in entry and not any(k in entry for k in ("triplog", "baremi542", "blogspot_travel", "blogspot_it")):
        entry = {"triplog": entry}
    entry[tier] = {"url": url, "ts": datetime.now().isoformat()}
    data[keyword] = entry
    _CROSSLINK_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def _get_crosslink_url(keyword: str, tier: str = "triplog") -> str:
    """키워드+계층의 발행 URL 조회 (없으면 빈 문자열).
    tier: 'triplog' | 'baremi542' | 'blogspot_travel' | 'blogspot_it'
    """
    try:
        if not _CROSSLINK_FILE.exists():
            return ""
        data = json.loads(_CROSSLINK_FILE.read_text())
        entry = data.get(keyword, {})
        # 구 형식 호환 (tier=triplog 기본)
        if "url" in entry and tier == "triplog":
            return entry.get("url", "")
        tier_data = entry.get(tier, {})
        return tier_data.get("url", "")
    except Exception:
        return ""


def _publish_triplog_immediately(keyword: str, title: str, blog_id: str = "triplog") -> str:
    """WP draft를 즉시 발행하고 published URL 반환 (triplog/baremi542, 실패 시 빈 문자열)"""
    try:
        sec = {}
        _sec_path = Path(__file__).parent / "remote_secrets.json"
        if _sec_path.exists():
            sec = json.loads(_sec_path.read_text())
        if blog_id == "baremi542":
            wp_url  = sec.get("WP_URL",          os.environ.get("WP_URL", ""))
            wp_user = sec.get("WP_USER",          os.environ.get("WP_USER", ""))
            wp_pass = sec.get("WP_APP_PASSWORD",  os.environ.get("WP_APP_PASSWORD", ""))
        else:  # triplog
            wp_url  = sec.get("TRIPLOG_WP_URL",          os.environ.get("TRIPLOG_WP_URL", ""))
            wp_user = sec.get("TRIPLOG_WP_USER",          os.environ.get("TRIPLOG_WP_USER", ""))
            wp_pass = sec.get("TRIPLOG_WP_APP_PASSWORD",  os.environ.get("TRIPLOG_WP_APP_PASSWORD", ""))
        if not (wp_url and wp_user and wp_pass):
            log(f"[{blog_id} 즉시발행] WP 자격증명 없음 — 스킵")
            return ""
        import base64
        auth = base64.b64encode(f"{wp_user}:{wp_pass}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}

        # 최신 draft 검색 (제목 기준)
        core = title[:20].replace(" ", "+")
        search_q = urllib.parse.urlencode({"search": core, "status": "draft", "per_page": 5})
        req = urllib.request.Request(
            f"{wp_url}/wp-json/wp/v2/posts?{search_q}",
            headers={"Authorization": f"Basic {auth}"},
        )
        with urllib.request.urlopen(req, timeout=15, context=_ssl_ctx()) as r:
            drafts = json.loads(r.read())

        post_id = None
        for d in drafts:
            dtitle = re.sub(r'<[^>]+>', '', d.get("title", {}).get("rendered", ""))
            if dtitle.strip()[:15] == title.strip()[:15]:
                post_id = d["id"]
                break
        if not post_id and drafts:
            post_id = drafts[0]["id"]  # 최신 draft 폴백

        if not post_id:
            log(f"[{blog_id} 즉시발행] draft 미발견: '{title[:30]}'")
            return ""

        # PATCH → publish
        patch_data = json.dumps({"status": "publish"}).encode()
        patch_req = urllib.request.Request(
            f"{wp_url}/wp-json/wp/v2/posts/{post_id}",
            data=patch_data,
            headers=headers,
            method="PATCH",
        )
        with urllib.request.urlopen(patch_req, timeout=20, context=_ssl_ctx()) as r:
            result = json.loads(r.read())
        pub_link = result.get("link", "")
        log(f"[{blog_id} 즉시발행] ✅ 발행 완료: {pub_link}")
        return pub_link
    except Exception as e:
        log(f"[{blog_id} 즉시발행] 오류: {e}")
        return ""

def _inject_internal_links(body: str, blog_id: str, on_log=None) -> str:
    """본문 하단에 같은 블로그 최근 글 3개 내부링크 섹션 추가"""
    if blog_id not in _BLOG_RSS:
        return body
    # Tistory 블로그는 에디터에서 HTML div가 이스케이프되어 raw text로 노출됨 — 주입 생략
    if blog_id in _TISTORY_BLOGS:
        return body
    rss_url, base_url = _BLOG_RSS[blog_id]
    try:
        req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8, context=_ssl_ctx()) as _r:
            rss = _r.read().decode("utf-8", errors="ignore")
        # 제목 + 링크 파싱
        items = re.findall(r'<item>.*?<title><!\[CDATA\[(.*?)\]\]></title>.*?<link>(.*?)</link>.*?</item>', rss, re.DOTALL)
        if not items:
            items_t = re.findall(r'<title>(.*?)</title>', rss)[1:4]
            items_l = re.findall(r'<link>(.*?)</link>', rss)[1:4]
            items = list(zip(items_t, items_l))
        import html as _html
        items = [(_html.unescape(t.strip()), l.strip()) for t, l in items[:3] if t.strip() and l.strip()]
        if not items:
            return body
        links_html = '\n'.join(
            f'<li><a href="{url}" target="_blank">{title}</a></li>'
            for title, url in items
        )
        section = (
            f'\n\n<div style="margin-top:30px;padding:16px;background:#f8f9fa;border-left:4px solid #4285f4;border-radius:4px">'
            f'<strong>📌 함께 읽으면 좋은 글</strong>'
            f'<ul style="margin:8px 0 0 0;padding-left:20px">{links_html}</ul>'
            f'</div>'
        )
        if on_log:
            on_log(f"[내부링크] {blog_id}: {len(items)}개 삽입")
        return body + section
    except Exception as e:
        if on_log:
            on_log(f"[내부링크] {blog_id} 실패 (무시): {e}")
        return body


# ─── 텍스트 버퍼 (이미지/포스팅 실패 시 텍스트 재사용) ───
_TEXT_BUFFER_DIR = LOG_DIR / "text_buffers"

def _save_text_buffer(blog_id: str, keyword: str, title: str, body: str, tags: list, images: list):
    """텍스트 생성 완료 후 버퍼 저장 — 이미지/Playwright 실패해도 텍스트 보존"""
    import fcntl
    _TEXT_BUFFER_DIR.mkdir(parents=True, exist_ok=True)
    buf = {"keyword": keyword, "title": title, "body": body, "tags": tags, "images": images,
           "saved_at": datetime.now().isoformat()}
    p = _TEXT_BUFFER_DIR / f"{blog_id}.json"
    with open(p, "w", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(buf, ensure_ascii=False, indent=2))
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    log(f"[버퍼] {blog_id} 텍스트 저장 완료 ('{title}')")

def _load_text_buffer(blog_id: str):
    """저장된 텍스트 버퍼 로드. 없거나 파손 시 None 반환."""
    import fcntl
    p = _TEXT_BUFFER_DIR / f"{blog_id}.json"
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                data = json.loads(f.read())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return data
    except Exception:
        p.unlink(missing_ok=True)
        return None

def _clear_text_buffer(blog_id: str):
    """텍스트 버퍼 삭제 (포스팅 성공 후 정리)"""
    p = _TEXT_BUFFER_DIR / f"{blog_id}.json"
    if p.exists():
        p.unlink()


# ─── 전체 포스팅 파이프라인 ───
def run_posting_pipeline(blog_id, keyword, _resume=None):
    """유사문서 체크 → 글 생성 → 이미지 → 포스팅 전체 파이프라인

    Returns: (ok: bool, title: str)
    """
    try:
        from claude_direct import generate_text
    except ImportError:
        from claude_playwright import generate_text
    from image_router import generate_images_for_blog
    from poster import post_single
    from public_api import fetch_context_for_blog

    # 버퍼 복원 경로: 텍스트는 이미 있고 이미지/포스팅만 재시도
    if _resume:
        title  = _resume["title"]
        body   = _resume["body"]
        tags   = _resume["tags"]
        images = _resume["images"]
        log(f"[파이프라인] 텍스트 버퍼 복원: '{title}' ({len(body)}자) — 이미지/포스팅만 실행")
        ok = _run_image_and_post(blog_id, keyword, title, body, tags, images)
        return (ok, title)

    # 0-2. 유사문서 체크 (블로그 내 기존 글)
    log(f"[파이프라인] {blog_id} / '{keyword}' — 유사문서 체크")
    is_dup, matched = check_duplicate_post(blog_id, keyword, on_log=log)
    if is_dup:
        log(f"[파이프라인] ⚠ 유사문서 발견 — 키워드 '{keyword}' 건너뜀")
        return False, ""

    # 1. triplog: MRT 제휴 링크 조회 후 프롬프트에 포함
    keyword_with_mrt = keyword
    if blog_id == "triplog":
        try:
            from mrt_affiliate import get_affiliate_links
            log(f"[파이프라인] triplog — MRT 제휴 링크 조회 중: '{keyword}'")
            mrt_links = get_affiliate_links(keyword, top_n=5, on_log=log)

            # 관련성 필터: 키워드의 핵심 지역/도시가 상품 제목에 포함되어야 함
            if mrt_links:
                dest_words = _extract_core_words(keyword)  # 핵심 단어 추출
                # 국내 여행 지역 키워드 (1글자 이상)
                dest_keywords = [w for w in dest_words if len(w) >= 2 and w not in {
                    '여행', '코스', '여행코스', '당일치기', '뚜벅이', '드라이브',
                    '맛집', '숙소', '카페', '일정', '추천', '2박3일', '1박2일',
                }]
                relevant_links = []
                for link in mrt_links:
                    title = link.get("title", "")
                    # 지역 키워드가 상품 제목에 하나라도 있어야 관련 있음
                    if any(dw in title for dw in dest_keywords):
                        relevant_links.append(link)
                if len(relevant_links) < len(mrt_links):
                    log(f"[파이프라인] MRT 관련성 필터: {len(mrt_links)}개 → {len(relevant_links)}개 (지역: {dest_keywords})")
                mrt_links = relevant_links[:3]

            # affiliate_url이 None/빈 것 제거 (원본 URL 폴백 없음 — 제휴링크만 허용)
            valid_links = [p for p in mrt_links if p.get("affiliate_url")]
            if not valid_links and mrt_links:
                log(f"[파이프라인] ⚠️ MRT 제휴 링크 생성 실패 — triplog 발행 스킵")

            if valid_links:
                mrt_ctx = (
                    "\n\n[마이리얼트립 제휴 상품 — 링크 2회 필수 삽입]\n"
                    "글 최상단(첫 문단 전)에 반드시 이 한 줄을 삽입해:\n"
                    "「이 글에는 마이리얼트립 파트너스 프로그램을 통해 소정의 수수료를 받을 수 있는 제휴 링크가 포함되어 있습니다.」\n\n"
                    "아래 제휴 상품 링크를 본문에 2회 삽입해 (CTR 최적화):\n"
                    "  1회차: 첫 번째 소제목(##) 바로 아래 — 후킹 문구 1줄 + 링크\n"
                    "         후킹 예시: '이 투어는 성수기에 금방 마감돼요 — 날짜 먼저 잡아두세요'\n"
                    "  2회차: 맺음말 직전 — '지금 예약 확인해보세요' CTA + 링크\n"
                    "링크 형식: <a href=\"URL\" target=\"_blank\" style=\"color:#1a73e8;font-weight:bold;\">상품명 예약하기</a>\n\n"
                    "아래 상품 중 글 내용과 가장 관련된 것 1~2개 선택해서 삽입:\n"
                )
                for i, p in enumerate(valid_links, 1):
                    name = p["title"][:60]
                    aff_url = p.get('affiliate_url', '')
                    mrt_ctx += f"{i}. 상품명: {name}\n   URL: {aff_url}\n"
                keyword_with_mrt = keyword + mrt_ctx
                log(f"[파이프라인] MRT {len(valid_links)}개 관련 제휴 링크 주입 완료")
            else:
                log(f"[파이프라인] MRT 관련 상품 없음 — 제휴 섹션 생략")
        except Exception as e:
            log(f"[파이프라인] MRT 조회 실패 (무시): {e}")

    # 1. Claude.ai 글 생성
    # 시즌 키워드 감지: 현재 월과 다른 월 키워드면 미리 준비 관점 컨텍스트 추가
    _cur_month = datetime.now().month
    _SEASON_HINTS = {
        1: "1월", 2: "2월", 3: "3월", 4: "4월", 5: "5월", 6: "6월",
        7: "7월", 8: "8월", 9: "9월", 10: "10월", 11: "11월", 12: "12월",
    }
    _season_ctx = ""
    for _sm, _sh in _SEASON_HINTS.items():
        if _sh in keyword_with_mrt and _sm != _cur_month:
            _diff = min(abs(_sm - _cur_month), 12 - abs(_sm - _cur_month))
            if _diff >= 2:
                _season_ctx = (
                    f"\n\n[작성 지침] 현재 {_cur_month}월 기준으로 작성. "
                    f"'{_sh}' 시즌 키워드이므로 '미리 알아두면 좋은', '지금부터 준비하면' 등 "
                    f"현재 시점에서 자연스럽게 연결되도록 작성할 것."
                )
                log(f"[파이프라인] 시즌 키워드 감지 ({_sh}) → 현재 시점 연결 컨텍스트 추가")
            break
    keyword_final = keyword_with_mrt + _season_ctx

    # nolja100: blogspot_travel 우선, 없으면 triplog 백링크 삽입 (링크 피라미드)
    # nolja100은 Tistory → 네이버 단축URL 불필요, 직접 URL 사용
    if blog_id == "nolja100":
        _crosslink = _get_crosslink_url(keyword, tier="blogspot_travel") or _get_crosslink_url(keyword, tier="triplog")
        if _crosslink:
            keyword_final += (
                f"\n\n[백링크 삽입 지침]\n"
                f"본문 중간(소제목 아래 또는 마지막 단락 전)에 아래 버튼형 링크를 1회 삽입해.\n"
                f"링크 URL: {_crosslink}\n"
                f"\n"
                f"삽입 형식 (HTML 그대로 사용):\n"
                f"<a href=\"{_crosslink}\" target=\"_blank\" "
                f"style=\"display:inline-block;background:#FF6B35;color:#fff;"
                f"padding:11px 22px;border-radius:6px;text-decoration:none;"
                f"font-weight:bold;font-size:15px;letter-spacing:-0.3px;\">"
                f"→ {{keyword 핵심어}} 상세 정보 보기</a>\n"
                f"\n"
                f"앵커텍스트 규칙:\n"
                f"- '{keyword}' 핵심어를 살려서 자연스럽게 작성\n"
                f"- 예시: '→ {keyword} 일정 전체 보기', '→ {keyword} 준비 가이드', '📍 {keyword} 코스 확인'\n"
                f"- 금지: '클릭', '누르세요', '바로가기', '여기' 등 직접 클릭 유도 문구\n"
                f"- 버튼 앞뒤로 줄바꿈 1줄씩 추가해 버튼이 단독으로 보이게 할 것"
            )
            log(f"[파이프라인] nolja100 백링크 주입: {_crosslink}")

    # woll100: blogspot_travel 백링크 삽입 (링크 피라미드: WP → Blogspot → Tistory)
    if blog_id == "woll100":
        _bs_travel_url = _get_crosslink_url(keyword, tier="blogspot_travel")
        if _bs_travel_url:
            keyword_final += (
                f"\n\n[백링크 삽입 지침]\n"
                f"본문 중간(소제목 아래 또는 마지막 단락 전)에 아래 버튼형 링크를 1회 삽입해.\n"
                f"링크 URL: {_bs_travel_url}\n"
                f"\n"
                f"삽입 형식 (HTML 그대로 사용):\n"
                f"<a href=\"{_bs_travel_url}\" target=\"_blank\" "
                f"style=\"display:inline-block;background:#1a73e8;color:#fff;"
                f"padding:11px 22px;border-radius:6px;text-decoration:none;"
                f"font-weight:bold;font-size:15px;letter-spacing:-0.3px;\">"
                f"→ {keyword} 관련 정보 더 보기</a>\n"
                f"\n"
                f"앵커텍스트는 '{keyword}' 핵심어를 살려서 자연스럽게 작성. "
                f"'클릭', '누르세요', '바로가기', '여기' 등 직접 클릭 유도 문구 금지."
            )
            log(f"[파이프라인] woll100 blogspot_travel 백링크 주입: {_bs_travel_url}")

    # goodisak: blogspot_it 백링크 (링크 피라미드: Tistory → Blogspot IT)
    # poster.py가 <a href> 라인을 TinyMCE insertContent로 처리하므로 HTML 태그 노출 없음
    # URL은 네이버 단축URL로 변환 후 삽입 (SEO 신뢰도)
    if blog_id == "goodisak":
        _bs_it_url = _get_crosslink_url(keyword, tier="blogspot_it")
        if _bs_it_url:
            _short_url = _naver_short_url(_bs_it_url)
            log(f"[파이프라인] goodisak blogspot_it 백링크: {_bs_it_url} → {_short_url}")
            keyword_final += (
                f"\n\n[백링크 삽입 지침]\n"
                f"본문 중간(두 번째 소제목 아래 또는 마지막 단락 전)에 아래 버튼형 링크를 1회 삽입해.\n"
                f"링크 URL: {_short_url}\n"
                f"\n"
                f"삽입 형식 (HTML 그대로, 수정 없이 한 줄로 삽입):\n"
                f"<a href=\"{_short_url}\" target=\"_blank\" "
                f"style=\"display:inline-block;background:#1a73e8;color:#fff;"
                f"padding:11px 22px;border-radius:6px;text-decoration:none;"
                f"font-weight:bold;font-size:15px;letter-spacing:-0.3px;\">"
                f"→ {keyword} 관련 IT 정보 더 보기</a>\n"
                f"\n"
                f"앵커텍스트는 '{keyword}' 핵심어를 살려서 자연스럽게 작성. "
                f"'클릭', '누르세요', '바로가기', '여기' 등 직접 클릭 유도 문구 금지."
            )

    # 공공API 데이터 주입 (축제·공공서비스 실제 데이터 → 할루시네이션 방지)
    _api_ctx = fetch_context_for_blog(blog_id, keyword, on_log=log)

    # NotebookLM 리서치 비활성화 (인덱싱 대기 중 sys.exit 호출로 프로세스 크래시)
    # try:
    #     from notebooklm_research import research_sync as _nlm_research
    #     _nlm_ctx = _nlm_research(keyword, blog_id)
    # except Exception:
    #     pass

    log(f"[파이프라인] {blog_id} / '{keyword}' — Claude.ai 글 생성 시작")
    raw = generate_text("", blog_id=blog_id, keyword=keyword_final, on_log=log,
                        extra_context=_api_ctx if _api_ctx else None)

    if not raw or "추출 실패" in raw:
        log(f"[파이프라인] 글 생성 실패")
        return False, keyword

    # 2. 전처리 — MRT 메타 헤더 및 백틱 마커 정규화
    # 마이리얼트립 메타 정보 블록 제거 (═══...【메타 정보】...회차/앵글/문체 등)
    raw = re.sub(r'(?s)[`"]*\s*[═=─]{5,}.*?마이리얼트립 여행후기 생성 결과.*?[═=─]{5,}\s*\n'
                 r'【메타 정보】.*?(?=📌|===제목|`===제목)', '', raw).strip()
    # 백틱으로 감싸진 마커 정규화: `===제목===` → ===제목===
    raw = re.sub(r'`\s*(===(?:제목|본문|태그|이미지)(?:끝)?===)\s*`', r'\1', raw)
    # 📌 제목 / 📝 본문 헤더 줄 제거
    raw = re.sub(r'📌\s*\*?\*?제목\*?\*?\s*\n', '', raw)
    raw = re.sub(r'📝\s*\*?\*?본문\*?\*?\s*\n', '', raw)
    # ===본문=== 마커 없을 때 대비: 내용이 ===제목끝=== 뒤에 오면 ===본문===...===본문끝=== 추가
    if '===제목끝===' in raw and '===본문===' not in raw:
        raw = re.sub(r'(===제목끝===\s*\n)', r'\1===본문===\n', raw)
        raw = raw.rstrip() + '\n===본문끝==='

    # 3. 파싱 — 각 섹션 정확히 분리
    title_m = re.search(r"===제목===\s*\n(.*?)\n*===제목끝===", raw, re.DOTALL)
    body_m = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===", raw, re.DOTALL)
    tag_m = re.search(r"===태그===\s*\n(.*?)\n*===태그끝===", raw, re.DOTALL)
    img_m = re.search(r"===이미지===\s*\n(.*?)\n*===이미지끝===", raw, re.DOTALL)
    meta_m = re.search(r"===메타===\s*\n(.*?)\n*===메타끝===", raw, re.DOTALL)

    # 제목: ===제목===~===제목끝=== 사이에서 첫 줄만 추출 + 55자 제한 (SEO 최적화)
    if title_m:
        title_block = title_m.group(1).strip()
        raw_title = title_block.split('\n')[0].strip()
    else:
        raw_title = keyword
    title = _truncate_title(raw_title, max_len=55)

    body = body_m.group(1).strip() if body_m else raw

    # [이미지N]프롬프트:...alt:...[/이미지N] 멀티라인 블록 파싱:
    #   1) 프롬프트/alt 추출 → _body_images 목록에 저장
    #   2) 블록 → {{이미지N}} 플레이스홀더로 교체
    _body_images = []
    def _replace_img_block(m):
        idx = int(m.group(1))
        block = m.group(0)
        p_m = re.search(r'프롬프트:\s*(.+)', block)
        a_m = re.search(r'alt:\s*(.+)', block)
        f_m = re.search(r'파일명:\s*(.+)', block)
        prompt = p_m.group(1).strip() if p_m else f"{keyword} image {idx}"
        alt    = a_m.group(1).strip() if a_m else keyword
        fname  = f_m.group(1).strip() if f_m else f"{blog_id}-{idx}.webp"
        _body_images.append({"index": idx, "prompt": prompt, "alt": alt, "filename": fname})
        return f'\n{{{{이미지{idx}}}}}\n'
    body = re.sub(r'\[이미지\s*(\d+)\][\s\S]*?\[/이미지\s*\1\]', _replace_img_block, body).strip()
    # H2 제목 등에 붙은 인라인 [이미지N] / [/이미지N] 잔재 제거
    body = re.sub(r'\[/?이미지\s*\d+\]', '', body).strip()
    # 이미지 블록 파싱 실패 시 남은 프롬프트/alt 줄 강제 제거
    body = re.sub(r'(?m)^\s*(프롬프트|alt|Gemini프롬프트|파일명):.*$', '', body)
    body = re.sub(r'\n{3,}', '\n\n', body).strip()
    # {{이미지N}} 플레이스홀더를 단독 줄로 정규화
    body = re.sub(r'(?<!\n)(\{\{이미지\d+\}\})', r'\n\1', body).strip()

    # 품질 검수 체크리스트가 본문에 포함된 경우 제거
    body = re.sub(
        r'\n*항목기준충족.*$', '', body,
        flags=re.DOTALL
    ).strip()
    # ===검수=== 섹션이 본문 내 포함된 경우 제거
    body = re.sub(r'\n*===검수===.*?(?:===검수끝===|$)', '', body, flags=re.DOTALL).strip()
    # ✅/❌ 로 시작하는 체크리스트 줄 제거
    body = re.sub(r'\n[✅❌☑️].{0,60}(?:\n[✅❌☑️].{0,60}){2,}', '', body).strip()
    # [검증 필요], [출처 필요], [사실 확인] 등 내부 마커 제거
    body = re.sub(r'\[검증\s*필요\]|\[출처\s*필요\]|\[사실\s*확인\]|\[확인\s*필요\]', '', body).strip()
    # JSON-LD 스키마 / <script> 태그 전체 제거 (SEO 스키마가 본문에 섞이는 경우)
    body = re.sub(r'<script\b[^>]*>.*?</script>', '', body, flags=re.DOTALL | re.IGNORECASE).strip()
    # 노출된 HTML 블록 태그 제거 (<div>, <section>, <article> 등 — 인라인 태그는 유지)
    body = re.sub(r'</?(?:div|section|article|aside|header|footer|nav|main|figure|figcaption)(\s[^>]*)?>',
                  '', body, flags=re.IGNORECASE).strip()
    # <br> 태그를 줄바꿈으로 변환 (핵심요약 박스 등 HTML 잔재 처리)
    body = re.sub(r'<br\s*/?>', '\n', body, flags=re.IGNORECASE)
    # 마크다운 구분선 제거 (---, ***, ___ 단독 줄 — WordPress에서 그대로 노출됨)
    body = re.sub(r'(?m)^\s*[-*_]{3,}\s*$', '', body).strip()

    # 마크다운 잔재 변환 — 플랫폼별 처리
    _pw_blogs = {"goodisak", "nolja100", "salim1su", "me1091", "woll100", "phn0502"}
    if blog_id in _pw_blogs:
        # ## 제목 → [H2]제목[/H2]
        body = re.sub(r'(?m)^#{1,3}\s+(.+)$', r'[H2]\1[/H2]', body)
        # **bold** → [BOLD]bold[/BOLD]
        body = re.sub(r'\*\*(.+?)\*\*', r'[BOLD]\1[/BOLD]', body)
    else:
        # ## 제목 → <h2>제목</h2>
        body = re.sub(r'(?m)^#{1,3}\s+(.+)$', r'<h2>\1</h2>', body)
        # **bold** → <strong>bold</strong>
        body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', body)

    # 태그: 첫 줄만 (여러 줄이면 첫 줄의 쉼표 구분)
    if tag_m:
        tag_line = tag_m.group(1).strip().split('\n')[0].strip()
        tags = [t.strip() for t in tag_line.split(",") if t.strip()]
    else:
        tags = [keyword]

    images = []
    # 이미지 섹션 미발견 시 raw에서 직접 탐색 (===본문=== 내부에 포함된 경우 대응)
    if not img_m:
        img_m = re.search(r"===이미지===\s*(.*?)\s*===이미지끝===", raw, re.DOTALL)
    if not img_m:
        # 디버그: raw에 ===이미지=== 텍스트가 있는지 확인
        if "이미지" in raw:
            idx = raw.find("이미지")
            log(f"[파싱] ⚠ ===이미지=== 섹션 불일치. 'raw' 내 '이미지' 주변: {repr(raw[max(0,idx-10):idx+80])}")
        else:
            log(f"[파싱] ⚠ raw에 '이미지' 텍스트 없음. raw 끝 200자: {repr(raw[-200:])}")
    if img_m:
        img_text = img_m.group(1)
        log(f"[파싱] 이미지 섹션 발견 (길이={len(img_text)}자), 내용: {repr(img_text[:300])}")
        for m in re.finditer(
            r"\[이미지\s*(\d+)\][^\n]*\n.*?(?:Gemini\s*)?프롬프트:\s*(.+?)\n.*?파일명:\s*(.+?)\n.*?alt:\s*(.+?)(?=\[이미지|\Z)",
            img_text,
            re.DOTALL,
        ):
            images.append({
                "index": int(m.group(1)),
                "prompt": m.group(2).strip(),
                "filename": m.group(3).strip(),
                "alt": m.group(4).strip(),
            })
        if not images:
            # 더 단순한 fallback 파싱: 각 [이미지N] 블록을 찾아 필드 추출
            for block in re.findall(r"\[이미지\s*\d+\][^\[]+", img_text, re.DOTALL):
                n_m = re.search(r"\[이미지\s*(\d+)\]", block)
                p_m = re.search(r"프롬프트:\s*(.+)", block)
                f_m = re.search(r"파일명:\s*(.+)", block)
                a_m = re.search(r"alt:\s*(.+)", block)
                if n_m and p_m:
                    images.append({
                        "index": int(n_m.group(1)),
                        "prompt": p_m.group(1).strip(),
                        "filename": f_m.group(1).strip() if f_m else f"image-{n_m.group(1)}.jpg",
                        "alt": a_m.group(1).strip() if a_m else "",
                    })

    # ===이미지=== 섹션이 없고 body 내 [이미지N] 블록에서 추출한 경우 fallback 사용
    if not images and _body_images:
        images = _body_images
        log(f"[파싱] body 내 이미지 블록 {len(images)}개 추출 (===이미지=== 섹션 없음)")

    plain = re.sub(r"##.*|{{.*?}}|\[애드센스\]|\|.*", "", body)
    char_count = len(re.sub(r"\s+", "", plain))

    # 파싱 결과 검증 로그
    meta_desc = meta_m.group(1).strip().split('\n')[0].strip() if meta_m else ""

    log(f"[파싱] 제목: \"{title}\" ({len(title)}자)")
    log(f"[파싱] 본문: {char_count}자")
    log(f"[파싱] 태그: {tags} ({len(tags)}개)")
    log(f"[파싱] 이미지: {len(images)}개")
    if meta_desc:
        log(f"[파싱] 메타: \"{meta_desc[:60]}\" ({len(meta_desc)}자)")
    if len(title) == 0 or title.strip() == keyword.strip():
        log(f"[파싱] ⚠ 제목이 키워드와 동일 — 재생성 1회 시도")
        _raw2 = generate_text("", blog_id=blog_id, keyword=keyword_final, on_log=log,
                              extra_context=_api_ctx if _api_ctx else None)
        if _raw2 and "추출 실패" not in _raw2:
            _tm2 = re.search(r"===제목===\s*\n(.*?)\n*===제목끝===", _raw2, re.DOTALL)
            if _tm2:
                _t2 = _truncate_title(_tm2.group(1).strip().split('\n')[0].strip(), max_len=55)
                if _t2 and _t2.strip() != keyword.strip():
                    title = _t2
                    log(f"[파싱] 제목 재생성 성공: '{title}'")
                else:
                    log(f"[파싱] ❌ 제목 재생성도 실패 — 발행 중단")
                    return False, keyword
            else:
                log(f"[파싱] ❌ 제목 재생성 파싱 실패 — 발행 중단")
                return False, keyword
        else:
            log(f"[파싱] ❌ 제목 재생성 실패 — 발행 중단")
            return False, keyword
    if char_count < 100:
        log(f"[파싱] ⚠ 본문이 너무 짧음 ({char_count}자)")
    log(f"[파싱] 본문 미리보기: {body[:80]}...")

    MIN_IMAGES = 3

    # 3. 글 품질 검수 (이미지 생성 전에 먼저 — Gemini 쿼터 낭비 방지)
    MIN_BODY_CHARS_HARD = 2000  # 절대 최소 (이 미만이면 발행 중단)
    MIN_BODY_CHARS_SOFT = 3000  # 권고 최소 (이 미만이면 재생성 1회 시도)

    # 2000자 미만이면 재생성 1회 시도
    if char_count < MIN_BODY_CHARS_SOFT:
        log(f"[검수] ⚠ 본문 짧음 ({char_count}자 < {MIN_BODY_CHARS_SOFT}자) — 재생성 1회 시도")
        raw2 = generate_text("", blog_id=blog_id, keyword=keyword_with_mrt, on_log=log)
        if raw2 and "추출 실패" not in raw2:
            body_m2 = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===", raw2, re.DOTALL)
            if body_m2:
                body2 = body_m2.group(1).strip()
                plain2 = re.sub(r"##.*|{{.*?}}|\[애드센스\]|\|.*", "", body2)
                char_count2 = len(re.sub(r"\s+", "", plain2))
                if char_count2 > char_count:
                    log(f"[검수] 재생성 결과 더 길어짐: {char_count}자 → {char_count2}자 — 교체")
                    raw = raw2
                    # 파싱 다시
                    title_m = re.search(r"===제목===\s*\n(.*?)\n*===제목끝===", raw, re.DOTALL)
                    body_m = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===", raw, re.DOTALL)
                    tag_m = re.search(r"===태그===\s*\n(.*?)\n*===태그끝===", raw, re.DOTALL)
                    img_m = re.search(r"===이미지===\s*\n(.*?)\n*===이미지끝===", raw, re.DOTALL)
                    if not img_m:
                        img_m = re.search(r"===이미지===\s*(.*?)\s*===이미지끝===", raw, re.DOTALL)
                    if title_m:
                        title = _truncate_title(title_m.group(1).strip().split('\n')[0].strip(), max_len=40)
                    body = body_m.group(1).strip() if body_m else body  # body2 미정의 방지
                    if tag_m:
                        tag_line = tag_m.group(1).strip().split('\n')[0].strip()
                        tags = [t.strip() for t in tag_line.split(",") if t.strip()]
                    # 이미지 목록도 재생성 결과에서 업데이트 (핵심 버그 수정: 텍스트와 이미지 불일치 방지)
                    if img_m:
                        new_images = []
                        img_text2 = img_m.group(1)
                        for m2 in re.finditer(
                            r"\[이미지\s*(\d+)\][^\n]*\n.*?(?:Gemini\s*)?프롬프트:\s*(.+?)\n.*?파일명:\s*(.+?)\n.*?alt:\s*(.+?)(?=\[이미지|\Z)",
                            img_text2, re.DOTALL,
                        ):
                            new_images.append({
                                "index": int(m2.group(1)),
                                "prompt": m2.group(2).strip(),
                                "filename": m2.group(3).strip(),
                                "alt": m2.group(4).strip(),
                            })
                        if not new_images:
                            for block in re.findall(r"\[이미지\s*\d+\][^\[]+", img_text2, re.DOTALL):
                                n_m2 = re.search(r"\[이미지\s*(\d+)\]", block)
                                p_m2 = re.search(r"프롬프트:\s*(.+)", block)
                                f_m2 = re.search(r"파일명:\s*(.+)", block)
                                a_m2 = re.search(r"alt:\s*(.+)", block)
                                if n_m2 and p_m2:
                                    new_images.append({
                                        "index": int(n_m2.group(1)),
                                        "prompt": p_m2.group(1).strip(),
                                        "filename": f_m2.group(1).strip() if f_m2 else f"image-{n_m2.group(1)}.jpg",
                                        "alt": a_m2.group(1).strip() if a_m2 else "",
                                    })
                        if new_images:
                            log(f"[검수] 재생성 이미지 목록 업데이트: {len(images)}개 → {len(new_images)}개")
                            images = new_images
                        else:
                            log(f"[검수] ⚠ 재생성 이미지 파싱 실패 — 원본 이미지 목록 유지 (불일치 위험)")
                    body = re.sub(r'\n*항목기준충족.*$', '', body, flags=re.DOTALL).strip()
                    body = re.sub(r'\n*===검수===.*?(?:===검수끝===|$)', '', body, flags=re.DOTALL).strip()
                    body = re.sub(r'\n[✅❌☑️].{0,60}(?:\n[✅❌☑️].{0,60}){2,}', '', body).strip()
                    body = re.sub(r'\[검증\s*필요\]|\[출처\s*필요\]|\[사실\s*확인\]|\[확인\s*필요\]', '', body).strip()
                    body = re.sub(r'</?(?:div|section|article|aside|header|footer|nav|main|figure|figcaption)(\s[^>]*)?>',
                                  '', body, flags=re.IGNORECASE).strip()
                    body = re.sub(r'<br\s*/?>', '\n', body, flags=re.IGNORECASE)
                    body = re.sub(r'(?m)^\s*[-*_]{3,}\s*$', '', body).strip()
                    plain = re.sub(r"##.*|{{.*?}}|\[애드센스\]|\|.*", "", body)
                    char_count = len(re.sub(r"\s+", "", plain))
                else:
                    log(f"[검수] 재생성 결과 더 짧음 — 원본 유지")

    if char_count < MIN_BODY_CHARS_HARD:
        log(f"[검수] ⚠ 본문 짧음 ({char_count}자 < {MIN_BODY_CHARS_HARD}자) — 임시저장 후 클로드코드 보완 예정")
    elif char_count < MIN_BODY_CHARS_SOFT:
        log(f"[검수] ⚠ 본문 권고치 미달 ({char_count}자 < {MIN_BODY_CHARS_SOFT}자) — 임시저장 진행 (목표: 3000자)")
    if not tags:
        log(f"[검수] ⚠ 태그 없음 — 기본 태그로 대체")
        tags = [keyword]  # 최소 키워드라도 태그로 사용
    log(f"[검수] 글 품질 기록 — 본문 {char_count}자, 태그 {len(tags)}개 → 임시저장 진행")

    # 텍스트 체크포인트 저장 — 이미지/Playwright 실패 시 다음 라운드에서 재사용
    _save_text_buffer(blog_id, keyword, title, body, tags, images)

    ok = _run_image_and_post(blog_id, keyword, title, body, tags, images)
    return (ok, title) if ok else (False, title)


def _run_image_and_post(blog_id, keyword, title, body, tags, images):
    """이미지 생성 → 내부링크 → 임시저장 (텍스트 생성 이후 단계만)"""
    from image_router import generate_images_for_blog, generate_thumbnail, IMAGES_DIR
    from poster import post_single
    import shutil

    # 이미지 폴더 초기화 — 이전 글 이미지가 섞이는 것 방지
    blog_img_dir = IMAGES_DIR / blog_id
    if blog_img_dir.exists():
        shutil.rmtree(blog_img_dir)
        log(f"[파이프라인] 이미지 폴더 초기화: {blog_img_dir}")
    blog_img_dir.mkdir(parents=True, exist_ok=True)

    # H2 소제목 개수 = 본문 이미지 수 (최소 1)
    h2_count = len(re.findall(r'^##\s+', body, re.MULTILINE))
    MIN_IMAGES = max(h2_count, 1)
    log(f"[파이프라인] H2 소제목 {h2_count}개 → 본문 이미지 {MIN_IMAGES}개 목표")

    # 본문 이미지 생성 (오버레이 없음)
    image_paths = {}
    if images:
        is_naver = blog_id in ("salim1su", "me1091")
        log(f"[파이프라인] 이미지 생성 시작 (blog={blog_id}, skip_webp={is_naver})")
        image_paths = generate_images_for_blog(
            blog_id=blog_id,
            image_infos=images,
            skip_webp=is_naver,
            on_log=log,
        )
        log(f"[파이프라인] 본문 이미지 {len(image_paths)}개 생성 완료")

    # Pollinations 폴백 제거 — 엉뚱한 이미지 반환으로 품질 저하 원인
    # 이미지 부족 시 Claude Code에서 수동 보완

    if len(image_paths) < MIN_IMAGES:
        log(f"[검수] ⚠ 이미지 부족 ({len(image_paths)}개 < {MIN_IMAGES}개) — 임시저장 후 클로드코드 보완 예정")
    else:
        log(f"[검수] ✅ 본문 이미지 {len(image_paths)}개 확인")

    # 썸네일 별도 생성 (오버레이 적용)
    log(f"[파이프라인] 썸네일 생성 중...")
    thumb_path = generate_thumbnail(blog_id, keyword, title, on_log=log)
    if thumb_path:
        image_paths[0] = thumb_path
        log(f"[파이프라인] 썸네일 준비 완료: {thumb_path}")

    # 네이버 블로그 첫 500자 내 키워드 확인 (제목+본문 초반에 포함 여부만 체크, 강제삽입 없음)
    if blog_id in ("salim1su", "me1091"):
        first_500 = (title + " " + body)[:500]
        if keyword and keyword in first_500:
            log(f"[SEO] 제목/본문 초반에 키워드 '{keyword}' 확인됨")
        else:
            log(f"[SEO] 제목/본문 초반에 키워드 '{keyword}' 미확인 — 본문에 자연스럽게 포함 예정")

    # 내부링크 삽입
    body = _inject_internal_links(body, blog_id, log)

    # 임시저장 (Playwright) — 실패 시 최대 2회 재시도
    log(f"[파이프라인] 포스팅 시작: {blog_id}")
    ok = False
    for _attempt in range(3):
        ok = post_single(
            blog_id=blog_id,
            title=title,
            content=body,
            tags=tags,
            image_paths=image_paths,
            image_infos=images,
            thumbnail_path=thumb_path,
            on_log=log,
        )
        if ok:
            break
        if _attempt < 2:
            log(f"[파이프라인] 포스팅 실패 (시도 {_attempt+1}/3) — 30초 후 재시도")
            time.sleep(30)

    if ok:
        log(f"[파이프라인] {blog_id} / '{keyword}' 임시저장완료 ✅")
        _clear_text_buffer(blog_id)  # 성공 시 버퍼 정리
    else:
        log(f"[파이프라인] {blog_id} / '{keyword}' 포스팅 실패 ⚠ (텍스트 버퍼 보존 — 다음 라운드 재시도)")
    return ok


# ─── 블로그 1편 포스팅 ───
MIN_POST_GAP_HOURS = 3  # 같은 블로그 포스팅 최소 간격


def _hours_since_last_post(blog_id: str) -> float:
    """마지막 발행 이후 경과 시간(시간). 발행 이력 없으면 999 반환.

    publish_drafts.py가 logs/blog_publish_times.json에 기록한 실제 발행 시각을
    우선 참조하고, 없으면 SQLite draft_saved 시각으로 fallback.
    """
    import json as _j
    from datetime import datetime as _dt

    # 1순위: publish_drafts.py가 기록한 실제 발행 시각 (Unix timestamp)
    _times_file = LOG_DIR / "blog_publish_times.json"
    if _times_file.exists():
        try:
            times = _j.loads(_times_file.read_text())
            ts = times.get(blog_id)
            if ts:
                return (_dt.now().timestamp() - float(ts)) / 3600
        except Exception:
            pass

    # 2순위: me1091은 별도 SQLite 테이블 (me1091_published) 사용
    if blog_id == "me1091":
        import sqlite3 as _sq
        _db_path = Path(__file__).parent / "keyword_engine" / "engine.db"
        try:
            with _sq.connect(_db_path) as db:
                row = db.execute(
                    "SELECT published_at FROM me1091_published ORDER BY published_at DESC LIMIT 1"
                ).fetchone()
            if row:
                last_time = _dt.fromisoformat(row[0])
                return (_dt.now() - last_time).total_seconds() / 3600
        except Exception:
            pass
        return 999.0

    # 3순위: SQLite draft_saved 시각
    from keyword_engine.db_handler import _conn
    with _conn() as db:
        row = db.execute(
            """SELECT updated_at FROM keyword_blog_status
               WHERE blog_id = ? AND status IN ('published', 'draft_saved')
               ORDER BY updated_at DESC LIMIT 1""",
            (blog_id,),
        ).fetchone()
    if not row:
        return 999.0
    try:
        last_time = _dt.fromisoformat(row[0])
        return (_dt.now() - last_time).total_seconds() / 3600
    except Exception:
        return 999.0


def post_one_blog(blog_id):
    """한 블로그에 키워드 1개 선택 → 포스팅 (SQLite 키워드 엔진만 사용)"""
    import fcntl as _fcntl

    # 블로그별 락 파일 — 동일 블로그에 동시 2개 프로세스 방지 (이미지/텍스트 버퍼 충돌 방지)
    _lock_path = LOG_DIR / f"{blog_id}.lock"
    try:
        _lock_fh = open(_lock_path, "w")
        _fcntl.flock(_lock_fh, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
    except OSError:
        log(f"[{blog_id}] ⚠ 다른 프로세스가 이미 실행 중 (락 파일 있음) — 스킵")
        return False

    try:
        return _post_one_blog_inner(blog_id)
    except Exception as _e:
        import traceback as _tb
        log(f"[{blog_id}] ❌ 예외 발생: {_e}")
        log(f"[{blog_id}] traceback:\n{_tb.format_exc()}")
        return False
    finally:
        _fcntl.flock(_lock_fh, _fcntl.LOCK_UN)
        _lock_fh.close()
        try:
            _lock_path.unlink(missing_ok=True)
        except Exception:
            pass


def _md_to_html(md: str) -> str:
    """마크다운 본문 → Blogger용 HTML 변환 (간단한 규칙 기반)"""
    import html as _html
    lines = md.split('\n')
    result = []
    in_table = False
    in_blockquote = False

    for line in lines:
        # 표
        if line.strip().startswith('|'):
            if not in_table:
                result.append('<table style="width:100%;border-collapse:collapse;margin:16px 0;">')
                in_table = True
            if re.match(r'^\s*\|[-| :]+\|\s*$', line):
                continue  # 구분선 행 스킵
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            row_html = ''.join(f'<td style="border:1px solid #ddd;padding:8px;">{c}</td>' for c in cells)
            result.append(f'<tr>{row_html}</tr>')
            continue
        else:
            if in_table:
                result.append('</table>')
                in_table = False

        # 인용 (꿀팁 박스)
        if line.strip().startswith('> '):
            tip = line.strip()[2:]
            result.append(
                f'<blockquote style="background:#f0f7ff;border-left:4px solid #1a73e8;'
                f'padding:12px 16px;margin:16px 0;border-radius:4px;">'
                f'{_apply_inline(tip)}</blockquote>'
            )
            continue

        # H2
        h2 = re.match(r'^## (.+)$', line)
        if h2:
            result.append(f'<h2 style="margin-top:32px;">{_apply_inline(h2.group(1))}</h2>')
            continue
        # H3
        h3 = re.match(r'^### (.+)$', line)
        if h3:
            result.append(f'<h3 style="margin-top:20px;">{_apply_inline(h3.group(1))}</h3>')
            continue

        # 불릿 리스트
        li = re.match(r'^[-*] (.+)$', line)
        if li:
            result.append(f'<li style="margin:4px 0;">{_apply_inline(li.group(1))}</li>')
            continue

        # 이미지 플레이스홀더 — [이미지N] 또는 {{이미지N}} 형식 모두 처리
        img_m = re.match(r'^\[이미지(\d+)\]$', line.strip()) or re.match(r'^\{\{이미지(\d+)\}\}$', line.strip())
        if img_m:
            result.append(f'{{{{이미지{img_m.group(1)}}}}}')
            continue

        # 빈 줄
        if not line.strip():
            result.append('')
            continue

        # 이미 HTML 블록 태그로 시작하는 줄은 그대로 출력
        if re.match(r'^\s*<(h[1-6]|div|table|ul|ol|li|blockquote|pre|figure)', line, re.IGNORECASE):
            result.append(line)
            continue

        # 일반 단락
        result.append(f'<p>{_apply_inline(line)}</p>')

    if in_table:
        result.append('</table>')

    # <li> 태그를 <ul>로 래핑
    html = '\n'.join(result)
    html = re.sub(r'(<li[^>]*>.*?</li>\n?)+', lambda m: f'<ul style="padding-left:20px;margin:8px 0;">{m.group(0)}</ul>\n', html, flags=re.DOTALL)
    return html


def _apply_inline(text: str) -> str:
    """굵게, 이탤릭, 인라인코드 등 인라인 마크다운 변환"""
    # **볼드**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # *이탤릭*
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # `코드`
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    # [텍스트](URL)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', r'<a href="\2" target="_blank">\1</a>', text)
    return text


# Blogger 블로그별 blog_id 매핑 (.env에서 읽음)
_BLOGGER_BLOG_IDS = {}  # {"blogspot_daily": "12345...", ...}

def _get_blogger_blog_id(blog_id: str) -> str:
    """blog_id에 해당하는 Blogger blog ID 반환"""
    global _BLOGGER_BLOG_IDS
    if blog_id in _BLOGGER_BLOG_IDS:
        return _BLOGGER_BLOG_IDS[blog_id]
    # .env에서 읽기
    env = {}
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    # blogspot_daily → BLOGSPOT_DAILY_BLOG_ID
    # blogspot_travel → BLOGSPOT_TRAVEL_BLOG_ID
    env_key = blog_id.upper().replace("-", "_") + "_BLOG_ID"
    result = env.get(env_key, env.get("BLOGGER_BLOG_ID", ""))
    _BLOGGER_BLOG_IDS[blog_id] = result
    return result


def _post_one_blogger_blog(blog_id: str) -> bool:
    """Blogger 블로그에 키워드 1개 선택 → 글 생성 → Blogger API로 즉시 발행"""
    try:
        from claude_direct import generate_text
    except ImportError:
        from claude_playwright import generate_text
    from keyword_engine.db_handler import fetch_next_pending, set_keyword_status as _db_set
    from image_router import generate_images_for_blog
    from blogger_api import publish_post as _blogger_publish

    # 키워드 선택
    kw = None
    for _ in range(5):
        candidate = fetch_next_pending(blog_id)
        if not candidate:
            break
        if _naver_competition_check(candidate, on_log=log):
            kw = candidate
            break
        log(f"[{blog_id}] ⚠ 경쟁 높음 '{candidate}' → 스킵")
        _db_set(candidate, "failed", blog_id=blog_id)
    if not kw:
        log(f"[{blog_id}] 대기 키워드 없음 — 스킵")
        return False

    log(f"[{blog_id}] 키워드: {kw}")
    _db_set(kw, "in_progress", blog_id=blog_id)

    try:
        # 텍스트 버퍼 확인 — 이미지/API 실패 시 텍스트 재생성 없이 재시도
        buf = _load_text_buffer(blog_id)
        if buf and buf.get("keyword") == kw:
            log(f"[{blog_id}] 텍스트 버퍼 발견 '{kw}' — 이미지/발행만 재시도")
            title  = buf["title"]
            body   = buf["body"]
            tags   = buf["tags"]
            images = buf["images"]
            raw = None  # 글 생성 스킵 플래그
        else:
            buf = None
            raw = "__generate__"  # 글 생성 필요

        # 1. 글 생성 — 링크 피라미드: WP crosslink 주입
        kw_with_backlink = kw
        _wp_tier = "triplog" if blog_id == "blogspot_travel" else None
        if _wp_tier:
            _wp_link = _get_crosslink_url(kw, tier=_wp_tier)
            if _wp_link:
                kw_with_backlink += (
                    f"\n\n[백링크 삽입 지침]\n"
                    f"본문 중간(소제목 아래 또는 마지막 단락 전)에 아래 버튼형 링크를 1회 삽입해.\n"
                    f"링크 URL: {_wp_link}\n"
                    f"삽입 형식:\n"
                    f"<a href=\"{_wp_link}\" target=\"_blank\" "
                    f"style=\"display:inline-block;background:#FF6B35;color:#fff;"
                    f"padding:11px 22px;border-radius:6px;text-decoration:none;"
                    f"font-weight:bold;font-size:15px;\">"
                    f"→ {kw} 상세 정보 보기</a>\n"
                    f"앵커텍스트는 '{kw}' 핵심어를 살려서 자연스럽게 작성."
                )
                log(f"[{blog_id}] WP 백링크 주입 ({_wp_tier}): {_wp_link}")

        if raw == "__generate__":
            log(f"[{blog_id}] 글 생성 시작: '{kw}'")
            raw = generate_text("", blog_id=blog_id, keyword=kw_with_backlink, on_log=log)
            if not raw or "추출 실패" in raw:
                log(f"[{blog_id}] 글 생성 실패")
                _db_set(kw, "failed", blog_id=blog_id)
                return False

            # 백틱 마커 정규화
            raw = re.sub(r'`\s*(===(?:제목|본문|태그|메타)(?:끝)?===)\s*`', r'\1', raw)

            # 2. 파싱
            title_m = re.search(r"===제목===\s*\n(.*?)\n*===제목끝===", raw, re.DOTALL)
            body_m  = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===", raw, re.DOTALL)
            tag_m   = re.search(r"===태그===\s*\n(.*?)\n*===태그끝===", raw, re.DOTALL)
            img_m   = re.search(r"===이미지===\s*\n(.*?)\n*===이미지끝===", raw, re.DOTALL)

            raw_title = title_m.group(1).strip().split('\n')[0] if title_m else kw
            title = _truncate_title(raw_title, max_len=60)
            body  = body_m.group(1).strip() if body_m else raw

            # 내부 마커 제거
            body = re.sub(r'\[검증\s*필요\]|\[출처\s*필요\]|\[사실\s*확인\]|\[확인\s*필요\]', '', body)
            body = re.sub(r'(?m)^\s*[-*_]{3,}\s*$', '', body)

            if tag_m:
                tag_line = tag_m.group(1).strip().split('\n')[0]
                tags = [t.strip() for t in tag_line.split(',') if t.strip()]
            else:
                tags = [kw]

            # 이미지 정보 파싱
            images = []
            if img_m:
                img_text = img_m.group(1)
                for block in re.findall(r"\[이미지\s*\d+\][^\[]+", img_text, re.DOTALL):
                    n_m = re.search(r"\[이미지\s*(\d+)\]", block)
                    p_m = re.search(r"프롬프트:\s*(.+)", block)
                    f_m = re.search(r"파일명:\s*(.+)", block)
                    a_m = re.search(r"alt:\s*(.+)", block)
                    if n_m and p_m:
                        images.append({
                            "index": int(n_m.group(1)),
                            "prompt": p_m.group(1).strip(),
                            "filename": f_m.group(1).strip() if f_m else f"img-{n_m.group(1)}.jpg",
                            "alt": a_m.group(1).strip() if a_m else kw,
                        })

            # H2 개수로 최소 이미지 수 결정
            h2_count = len(re.findall(r'^##\s+|<h2', body, re.MULTILINE))
            if not images:
                for i in range(1, max(h2_count, 3) + 1):
                    images.append({"index": i, "prompt": f"{kw} infographic illustration {i}", "filename": f"img{i}.jpg", "alt": kw})

            # 텍스트 버퍼 저장 (이미지/API 실패 시 재사용)
            _save_text_buffer(blog_id, kw, title, body, tags, images)

        # 3. 이미지 생성 (Gemini / Pollinations)
        log(f"[{blog_id}] 이미지 {len(images)}개 생성 시작")
        image_paths = generate_images_for_blog(
            blog_id=blog_id,
            image_infos=images,
            skip_webp=False,
            on_log=log,
        )
        log(f"[{blog_id}] 이미지 {len(image_paths)}개 생성 완료")

        # Pollinations 폴백 제거 — 이미지 부족 시 그대로 진행 (Claude Code 수동 보완)

        # 4. 마크다운 → HTML 변환
        html_body = _md_to_html(body)

        # 5. {{이미지N}} 플레이스홀더를 <img> 태그로 교체
        # Blogger API는 이미지를 base64 data URI 또는 외부 URL로 받음
        # 로컬 파일을 base64로 인코딩하여 삽입
        import base64 as _b64
        def _img_tag(path: str, alt: str) -> str:
            try:
                with open(path, "rb") as f:
                    data = _b64.b64encode(f.read()).decode()
                ext = Path(path).suffix.lower().lstrip('.')
                mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
                return (f'<div style="text-align:center;margin:20px 0;">'
                        f'<img src="data:image/{mime};base64,{data}" '
                        f'alt="{alt}" style="max-width:100%;height:auto;border-radius:8px;" />'
                        f'</div>')
            except Exception as e:
                log(f"[{blog_id}] 이미지 삽입 실패 ({path}): {e}")
                return ""

        for img in images:
            idx = img["index"]
            placeholder = f"{{{{이미지{idx}}}}}"
            if idx in image_paths:
                tag = _img_tag(image_paths[idx], img.get("alt", kw))
            else:
                tag = ""
            html_body = html_body.replace(placeholder, tag)

        # 남은 플레이스홀더 제거
        html_body = re.sub(r'\{\{이미지\d+\}\}', '', html_body)

        # 6. Blogger API로 발행
        blogger_id = _get_blogger_blog_id(blog_id)
        if not blogger_id:
            log(f"[{blog_id}] ⚠ Blogger blog ID 없음 — .env에 BLOGSPOT_DAILY_BLOG_ID 설정 필요")
            _db_set(kw, "failed", blog_id=blog_id)
            return False

        log(f"[{blog_id}] Blogger API 임시저장 중: '{title}' (HTML {len(html_body)}자, 라벨 {len(tags[:12])}개, blog_id={blogger_id})")
        result = _blogger_publish(title=title, content=html_body, labels=tags[:12],
                                  status="DRAFT", blog_id=blogger_id)
        if not result.get("ok"):
            log(f"[{blog_id}] Blogger 발행 실패: {result.get('reason')}")
            log(f"[{blog_id}] 디버그: 라벨={tags[:12]}, HTML앞100={html_body[:100]!r}")
            _db_set(kw, "failed", blog_id=blog_id)
            return False

        post_url = result.get("url", "")
        post_id  = result.get("id", "")
        log(f"[{blog_id}] ✅ 임시저장 완료: {post_url}")
        _db_set(kw, "draft_saved", blog_id=blog_id, title=title)

        # Playwright로 이미지 삽입
        if image_paths and post_id and blogger_id:
            log(f"[{blog_id}] Playwright 이미지 삽입 시작")
            _blogger_insert_images_pw(blogger_id, post_id, image_paths, on_log=log)
        _clear_text_buffer(blog_id)

        # 링크 피라미드: blogspot_travel / blogspot_it 발행 URL 저장 (Tistory 봇이 백링크 삽입)
        if blog_id in ("blogspot_travel", "blogspot_it") and post_url:
            _store_crosslink_url(kw, post_url, tier=blog_id)
            log(f"[{blog_id}] 크로스링크 저장: {post_url}")

        # 발행 시각 기록
        _times_file = LOG_DIR / "blog_publish_times.json"
        try:
            times = json.loads(_times_file.read_text()) if _times_file.exists() else {}
            times[blog_id] = datetime.now().timestamp()
            _times_file.write_text(json.dumps(times))
        except Exception:
            pass

        # 텔레그램 보고
        _tg_msg = (
            f"✅ 발행 완료\n"
            f"블로그: {blog_id}\n"
            f"제목: {title}\n"
            f"발행시각: {datetime.now().strftime('%H:%M')}\n"
            f"URL: {post_url}\n\n"
            f"🔧 검수 중 수정사항:\n- 이상 없음"
        )
        try:
            import subprocess as _sp
            _sp.run([sys.executable, str(BASE_DIR / "tg_send.py"), _tg_msg], timeout=15)
        except Exception:
            pass

        return True

    except Exception as e:
        log(f"[{blog_id}] 오류: {e}")
        _db_set(kw, "failed", blog_id=blog_id)
        return False


def _upload_image_to_host(img_data: bytes, filename: str) -> str:
    """무료 이미지 호스팅에 업로드 (imgbb 우선, litterbox 백업).
    imgbb 영구, litterbox 72시간 임시.
    """
    import urllib.request as _ur

    # 1. imgbb (영구, .env에 IMGBB_API_KEY 있을 때)
    env = {}
    try:
        env_path = BASE_DIR / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    except Exception:
        pass

    imgbb_key = env.get("IMGBB_API_KEY", "")
    if imgbb_key:
        try:
            import base64 as _b64
            b64 = _b64.b64encode(img_data).decode()
            body = f"key={imgbb_key}&image={_ur.parse.quote(b64)}&name={_ur.parse.quote(filename)}".encode()
            req = _ur.Request("https://api.imgbb.com/1/upload", data=body,
                              headers={"Content-Type": "application/x-www-form-urlencoded"})
            with _ur.urlopen(req, timeout=30) as resp:
                import json as _json
                d = _json.loads(resp.read())
                if d.get("success"):
                    return d["data"]["url"]
        except Exception:
            pass

    # 2. litterbox.catbox.moe (임시 72시간)
    try:
        boundary = "----Boundary7MA5"
        parts = [
            f'--{boundary}\r\nContent-Disposition: form-data; name="reqtype"\r\n\r\nfileupload'.encode(),
            f'--{boundary}\r\nContent-Disposition: form-data; name="time"\r\n\r\n72h'.encode(),
            (f'--{boundary}\r\nContent-Disposition: form-data; name="fileToUpload"; filename="{filename}"\r\n'
             f'Content-Type: image/jpeg\r\n\r\n').encode() + img_data,
            f'--{boundary}--'.encode(),
        ]
        body = b'\r\n'.join(parts)
        req = _ur.Request(
            "https://litterbox.catbox.moe/resources/internals/api.php",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                     "User-Agent": "Mozilla/5.0"},
            method="POST"
        )
        with _ur.urlopen(req, timeout=30) as resp:
            result = resp.read().decode("utf-8").strip()
            if result.startswith("https://"):
                return result
    except Exception:
        pass

    return ""


def _blogger_insert_images_pw(blogger_blog_id: str, post_id: str, image_paths: dict, on_log=None) -> bool:
    """Blogger 포스트에 이미지 삽입 (Playwright + Google Picker 로컬 업로드 방식).
    image_paths: {1: '/path/img1.webp', 2: '/path/img2.webp', ...}
    Chrome CDP(9222)로 에디터 열어 이미지 삽입 후 저장.
    """
    import time as _time

    def log(msg):
        if on_log: on_log(msg)

    if not image_paths:
        log("[Blogger이미지] 삽입할 이미지 없음")
        return False

    # JS: 드롭다운에서 '컴퓨터에서 업로드' 요소 좌표 반환
    JS_FIND_UPLOAD = """() => {
        function traverse(node) {
            if (!node) return null;
            if (node.shadowRoot) {
                let r = traverse(node.shadowRoot);
                if (r) return r;
            }
            let text = (node.textContent || '').trim();
            if (text === '컴퓨터에서 업로드' && node.tagName === 'DIV') {
                let rect = node.getBoundingClientRect();
                if (rect.width > 10 && rect.height > 10 && rect.width < 300) {
                    return {x: Math.round(rect.left + rect.width/2),
                            y: Math.round(rect.top + rect.height/2)};
                }
            }
            for (let c of (node.children || [])) {
                let r = traverse(c);
                if (r) return r;
            }
            return null;
        }
        return traverse(document.body);
    }"""

    def _find_file_input(page, timeout=12):
        start = _time.time()
        while _time.time() - start < timeout:
            for f in page.frames:
                try:
                    if f.locator('input[type="file"]').count() > 0:
                        return f
                except: pass
            _time.sleep(0.5)
        return None

    def _wait_picker_closed(page, timeout=40):
        start = _time.time()
        while _time.time() - start < timeout:
            try:
                has_input = any(
                    f.locator('input[type="file"]').count() > 0
                    for f in page.frames
                )
            except:
                has_input = False
            if not has_input:
                return True
            _time.sleep(0.5)
        return False

    try:
        from playwright.sync_api import sync_playwright as _pw
    except ImportError:
        log("[Blogger이미지] playwright 미설치")
        return False

    edit_url = f"https://www.blogger.com/blog/post/edit/{blogger_blog_id}/{post_id}"
    sorted_imgs = sorted(image_paths.items())
    success_count = 0

    try:
        with _pw() as pw:
            browser = pw.chromium.connect_over_cdp("http://localhost:9222")
            ctx = browser.contexts[0]

            # 기존 에디터 탭 재사용 또는 새 탭
            page = None
            for p in ctx.pages:
                if f"post/edit/{blogger_blog_id}/{post_id}" in p.url:
                    page = p
                    break
            if page is None:
                page = ctx.new_page()
                page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
                _time.sleep(5)
            else:
                page.bring_to_front()
                _time.sleep(1)

            page.keyboard.press("Escape")
            _time.sleep(1)

            for img_num, img_path in sorted_imgs:
                p_path = Path(img_path)
                if not p_path.exists():
                    log(f"[Blogger이미지] 파일 없음: {img_path}")
                    continue

                log(f"[Blogger이미지] 삽입 중 ({img_num}/{len(sorted_imgs)}): {p_path.name}")

                page.evaluate("window.scrollTo(0, 0)")
                _time.sleep(0.3)

                # 이미지 삽입 버튼 → 드롭다운
                img_btn = page.locator("div[role='button'][aria-label='이미지 삽입']").first
                img_btn.click(force=True)
                _time.sleep(1.5)

                # '컴퓨터에서 업로드' 좌표 동적 탐색
                coords = page.evaluate(JS_FIND_UPLOAD)
                if not coords:
                    log(f"[Blogger이미지] '컴퓨터에서 업로드' 요소 없음, 스킵")
                    page.keyboard.press("Escape")
                    continue

                page.mouse.click(coords['x'], coords['y'])

                # Google Picker 파일 입력 대기
                picker_frame = _find_file_input(page, timeout=12)
                if not picker_frame:
                    log(f"[Blogger이미지] Picker 없음, 스킵")
                    page.keyboard.press("Escape")
                    continue

                _time.sleep(2)  # Picker JS 초기화 대기

                try:
                    file_input = picker_frame.locator('input[type="file"]').first
                    file_input.set_input_files(str(img_path))
                except Exception as e:
                    log(f"[Blogger이미지] set_input_files 오류: {e}")
                    page.keyboard.press("Escape")
                    continue

                # 업로드 완료 대기 (picker 자동 닫힘)
                _wait_picker_closed(page, timeout=40)
                _time.sleep(2)
                success_count += 1
                log(f"[Blogger이미지] ✅ 이미지 {img_num} 삽입 완료")

            if success_count == 0:
                log("[Blogger이미지] 삽입된 이미지 없음")
                page.close()
                return False

            # 업데이트 저장
            try:
                update_btn = page.locator("div[role='button'][aria-label='업데이트']").first
                if update_btn.get_attribute("aria-disabled") != "true":
                    update_btn.click(force=True)
                    _time.sleep(5)
                    log(f"[Blogger이미지] ✅ 저장 완료 ({success_count}/{len(sorted_imgs)}장)")
                else:
                    log("[Blogger이미지] 변경사항 없음 (저장 불필요)")
            except Exception as e:
                log(f"[Blogger이미지] 저장 오류: {e}")

            page.close()
            return success_count > 0

    except Exception as e:
        log(f"[Blogger이미지] Playwright 오류: {e}")
        return False


def _post_one_blog_inner(blog_id):
    """post_one_blog 실제 로직 (락 획득 후 호출)"""
    # me1091: Notion 상품 기반 Coupang 리뷰 파이프라인 (키워드 DB 사용 안 함)
    if blog_id == "me1091":
        elapsed = _hours_since_last_post("me1091")
        if elapsed < MIN_POST_GAP_HOURS:
            log(f"[me1091] 마지막 포스팅 {elapsed:.1f}시간 전 — 최소 {MIN_POST_GAP_HOURS}시간 필요, 스킵")
            return False
        try:
            from me1091_bot import run_one_product
            return run_one_product(on_log=log)
        except Exception as e:
            log(f"[me1091] 오류: {e}")
            return False

    # Blogspot 블로그: Blogger API로 직접 발행 (Playwright 불필요)
    _BLOGGER_BLOGS = {"blogspot_daily", "blogspot_travel", "blogspot_it"}
    if blog_id in _BLOGGER_BLOGS:
        elapsed = _hours_since_last_post(blog_id)
        if elapsed < MIN_POST_GAP_HOURS:
            log(f"[{blog_id}] 마지막 포스팅 {elapsed:.1f}시간 전 — 최소 {MIN_POST_GAP_HOURS}시간 필요, 스킵")
            return False
        return _post_one_blogger_blog(blog_id)

    from keyword_engine.db_handler import fetch_next_pending, set_keyword_status as _db_set

    # 최소 포스팅 간격 체크 (같은 블로그 3시간 이상 텀)
    # nolja100/triplog: 각자 타이머 사용 + 상대방이 4시간 이내 발행했으면 대기
    TRAVEL_GROUP = {"nolja100", "triplog"}
    elapsed = _hours_since_last_post(blog_id)
    if blog_id in TRAVEL_GROUP:
        other_elapsed = min(
            (_hours_since_last_post(b) for b in TRAVEL_GROUP if b != blog_id),
            default=999
        )
        if other_elapsed < 4:
            # 상대 여행 블로그가 4시간 이내 발행 → 두 블로그 모두 포화 방지
            effective_elapsed = min(elapsed, other_elapsed)
            if effective_elapsed < MIN_POST_GAP_HOURS:
                log(f"[{blog_id}] 여행그룹 쿨다운 (상대 {other_elapsed:.1f}h 전 발행) — 스킵")
                return False
    if elapsed < MIN_POST_GAP_HOURS:
        log(f"[{blog_id}] 마지막 포스팅 {elapsed:.1f}시간 전 — 최소 {MIN_POST_GAP_HOURS}시간 필요, 스킵")
        return False

    # 이전 텍스트 버퍼 확인 — 이미지/Playwright만 실패했다면 텍스트 재생성 없이 재시도
    buf = _load_text_buffer(blog_id)
    if buf:
        log(f"[{blog_id}] 텍스트 버퍼 발견 ('{buf['keyword']}') — 이미지/포스팅만 재시도")
        try:
            ok, saved_title = run_posting_pipeline(blog_id, buf["keyword"], _resume=buf)
            if ok:
                _db_set(buf["keyword"], "draft_saved", blog_id=blog_id, title=saved_title)
                return True
        except Exception as e:
            log(f"[{blog_id}] 버퍼 재시도 실패: {e}")
        log(f"[{blog_id}] 버퍼 재시도도 실패 — 버퍼 제거 후 새로 생성")
        _clear_text_buffer(blog_id)

    # 테마 부적합 키워드는 스킵하고 다음 키워드 재시도 (최대 5회)
    kw = None
    for _ in range(5):
        candidate = fetch_next_pending(blog_id)
        if not candidate:
            break
        if is_keyword_suitable(blog_id, candidate) and _naver_competition_check(candidate, on_log=log):
            kw = candidate
            break
        log(f"[{blog_id}] ⚠ 테마 부적합 또는 경쟁 높음 '{candidate}' → 스킵")
        _db_set(candidate, "failed", blog_id=blog_id)
    if not kw:
        log(f"[{blog_id}] 대기 키워드 없음 — 스킵")
        return False
    log(f"[{blog_id}] 키워드: {kw}")
    _db_set(kw, "in_progress", blog_id=blog_id)
    _PLAYWRIGHT_ERRORS = ("Connection closed", "BrokenPipe", "Broken pipe",
                          "Target closed", "browser has been closed",
                          "WebSocket", "playwright")
    for attempt in range(1, 3):  # 최대 2회 시도
        try:
            ok, saved_title = run_posting_pipeline(blog_id, kw)
            if ok:
                # 모든 블로그 임시저장 → draft_saved (Claude Code가 검수 후 발행)
                _db_set(kw, "draft_saved", blog_id=blog_id, title=saved_title)
                # 자동 발행 비활성화 — 임시저장까지만 (triplog/baremi542 포함 전체)
                pass
                return True
            else:
                _db_set(kw, "failed", blog_id=blog_id)
                return False
        except Exception as e:
            err_str = str(e)
            is_playwright_crash = any(p.lower() in err_str.lower() for p in _PLAYWRIGHT_ERRORS)
            if is_playwright_crash and attempt == 1:
                log(f"[{blog_id}] Playwright 오류 — 60초 후 재시도 ({err_str[:80]})")
                _db_set(kw, "pending", blog_id=blog_id)  # 재시도 가능하도록 pending 복원
                time.sleep(60)
                continue
            log(f"[{blog_id}] 오류: {e}")
            _db_set(kw, "failed", blog_id=blog_id)
            return False


def run_one_round(round_num):
    """모든 블로그에 1편씩 포스팅 (1라운드) — 순서 랜덤. 실패 블로그는 1회 재시도."""
    import time as _time
    import random as _rand
    # triplog는 nolja100보다 항상 먼저 — 같은 여행 카테고리에서 triplog 우선 배정
    _non_travel = ["salim1su", "baremi542", "goodisak", "woll100", "phn0502", "me1091",
                   "blogspot_daily", "blogspot_travel", "blogspot_it"]
    _rand.shuffle(_non_travel)
    BLOGS = ["triplog", "nolja100"] + _non_travel
    log(f"\n{'='*60}")
    log(f"[라운드 {round_num}] 시작 ({datetime.now().strftime('%H:%M')})")
    log(f"{'='*60}")
    results = {}
    errors = {}
    for blog_id in BLOGS:
        try:
            ok = post_one_blog(blog_id)
            results[blog_id] = "✅" if ok else "⚠"
        except Exception as _e:
            import traceback as _tb
            err_detail = _tb.format_exc()
            log(f"[라운드{round_num}] ❌ {blog_id} 예외: {_e}")
            log(f"[라운드{round_num}] {blog_id} traceback:\n{err_detail}")
            results[blog_id] = "❌"
            errors[blog_id] = str(_e)
        # 블로그 간 1-3분 랜덤 대기 (사람처럼)
        _time.sleep(_rand.uniform(60, 180))
    log(f"[라운드 {round_num}] 완료: " + " / ".join(f"{k}:{v}" for k, v in results.items()))
    if errors:
        log(f"[라운드 {round_num}] 오류 목록: " + " | ".join(f"{k}={v[:60]}" for k, v in errors.items()))
    save_log()

    # ── 실패 블로그 즉시 재시도 (1회) ──
    failed = [b for b, s in results.items() if s == "⚠"]
    if failed:
        log(f"[라운드 {round_num}] 실패 블로그 재시도: {failed}")
        _time.sleep(_rand.uniform(60, 120))  # 1-2분 후 재시도
        for blog_id in failed:
            try:
                ok = post_one_blog(blog_id)
            except Exception as _e:
                import traceback as _tb
                log(f"[재시도] ❌ {blog_id} 예외: {_e}\n{_tb.format_exc()}")
                ok = False
            results[blog_id] = "✅" if ok else "⚠"
            _time.sleep(_rand.uniform(30, 90))
        log(f"[라운드 {round_num}] 재시도 결과: " + " / ".join(f"{b}:{results[b]}" for b in failed))
        save_log()

    # 리프레시 대상 확인 (30~60일 된 글)
    try:
        from refresh_posts import run_refresh
        run_refresh()
    except Exception as e:
        log(f"[리프레시] 스킵: {e}")

    # MRT 파트너 블로그 딜 모니터링 (triplog용 프로모션 글 자동 생성)
    try:
        from mrt_deals import run_deal_check
        run_deal_check()
    except Exception as e:
        log(f"[딜모니터] 스킵: {e}")

    # ── 자동 발행 비활성화 (임시저장까지만) ──────────────────────────
    # publish_drafts.py 자동 실행 OFF — 수동 발행 시 별도 실행
    pass


# ─── 메인 실행 ───
# 사용법: python3 overnight_run.py [blog_id]
#   blog_id 지정 시: 해당 블로그 1편만 생성+임시저장
#   blog_id 없을 시: 전체 블로그 1라운드 실행
if __name__ == "__main__":
    import sys as _sys

    log("=" * 60)
    log(f"자동 실행 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    log("=" * 60)

    # ── 시작 시: stale in_progress 키워드 → pending 초기화 (이전 세션 crash 대비) ──
    try:
        from keyword_engine.db_handler import _conn as _kw_conn
        with _kw_conn() as _db:
            _stale = _db.execute(
                "SELECT keyword, blog_id FROM keyword_blog_status WHERE status = 'in_progress'"
            ).fetchall()
            if _stale:
                for _s_kw, _s_blog in _stale:
                    _db.execute(
                        "UPDATE keyword_blog_status SET status = 'pending' WHERE keyword = ? AND blog_id = ?",
                        (_s_kw, _s_blog),
                    )
                log(f"[시작] stale in_progress {len(_stale)}개 → pending 초기화: {[r[0] for r in _stale]}")
    except Exception as _e:
        log(f"[시작] in_progress 초기화 실패 (무시): {_e}")

    # ── 일 1회 작업: 키워드 크롤링 + 롱테일 확장 + 경쟁모니터 (상태파일로 중복 방지) ──
    _STATE_FILE = LOG_DIR / "overnight_state.json"
    _today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        _state = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        if _state.get("run_date") != _today_str:
            _state = None
    except Exception:
        _state = None
    if not _state:
        _state = {"run_date": _today_str, "crawling_done": False}
        try:
            _STATE_FILE.write_text(json.dumps(_state, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    _crawled_keywords = {}
    if not _state.get("crawling_done"):
        log("[크롤링] salim1su, baremi542 키워드 수집")
        from keyword_crawler import crawl_keywords
        for bid in ["salim1su", "baremi542"]:
            try:
                result = crawl_keywords(blog_id=bid, on_log=log)
                cnt = result.get(bid, 0)
                log(f"[크롤링] {bid}: {cnt}개 저장")
                if cnt > 0:
                    _crawled_keywords[bid] = result.get("keywords", [])
            except Exception as e:
                log(f"[크롤링] {bid} 오류: {e}")
        _state["crawling_done"] = True
        try:
            _STATE_FILE.write_text(json.dumps(_state, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        save_log()

        log("[롱테일] 키워드 확장 시작")
        _BLOG_LONGTAIL = {
            "nolja100":  "여행",
            "triplog":   "여행",
            "salim1su":  "살림",
            "goodisak":  "IT",
            "baremi542": "정부지원금",
            "woll100":   "교통",
            "phn0502":   "영화",
            "me1091":    "리뷰",
        }
        try:
            from keyword_engine.longtail_expander import expand_longtail
            from keyword_engine.db_handler import get_top_keywords
            _CAT_BLOG = {"여행": ["nolja100", "triplog"], "살림": ["salim1su"],
                         "IT": ["goodisak"], "정부지원금": ["baremi542"],
                         "교통": ["woll100"], "영화": ["phn0502"]}
            for bid, cat in _BLOG_LONGTAIL.items():
                if cat == "여행" and bid == "triplog":
                    continue
                crawled_seeds = []
                for _bid in _CAT_BLOG.get(cat, []):
                    crawled_seeds.extend(_crawled_keywords.get(_bid, []))
                db_seeds = [r["keyword"] for r in get_top_keywords(n=20, min_score=0)
                            if r.get("category", "") == cat and len(r["keyword"].split()) <= 4]
                seen_seeds = set()
                seeds = []
                for kw in crawled_seeds + db_seeds:
                    if kw not in seen_seeds:
                        seen_seeds.add(kw)
                        seeds.append(kw)
                if not seeds:
                    continue
                added = expand_longtail(base_keywords=seeds, category=cat, blog_id=bid,
                                        top_n=8, on_log=log)
                log(f"[롱테일] {bid}({cat}): +{added}개 롱테일 추가")
        except Exception as e:
            log(f"[롱테일] 오류: {e}")

        _today_wd = datetime.now().weekday()
        if _today_wd in (0, 2, 4):
            log("[경쟁모니터] 경쟁 사이트 신규 포스트 감지 시작")
            try:
                from keyword_engine.competitor_monitor import monitor_competitors
                _added = monitor_competitors(on_log=log)
                log(f"[경쟁모니터] 신규 키워드 {_added}개 추가 완료")
            except Exception as _e:
                log(f"[경쟁모니터] 오류: {_e}")
        save_log()
    else:
        log("[크롤링] 오늘 이미 완료 — 스킵")

    # ── 포스팅 실행 ──
    _target_blog = _sys.argv[1] if len(_sys.argv) > 1 else None
    if _target_blog:
        log(f"[실행] 블로그 지정: {_target_blog}")
        ok = post_one_blog(_target_blog)
        log(f"[완료] {_target_blog}: {'✅' if ok else '⚠'}")
    else:
        log("[실행] 전체 블로그 1라운드")
        run_one_round(1)

    log("\n" + "=" * 60)
    log("완료")
    log("=" * 60)
    save_log()
