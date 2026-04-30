"""키워드 크롤러 — 네이버 데이터랩 + 자동완성 + 검색광고 API → Notion 저장"""
import os
import time
import json
import hashlib
import hmac
import base64
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta

from blog_stats import get_blog_level
import blog_visitor

# .env 로드 (번들 실행 시 PROJECT_ROOT 우선)
_env_path = Path(os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(Path(__file__).parent))) / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

# API 키
DATALAB_CLIENT_ID = os.environ.get("NAVER_DATALAB_CLIENT_ID", "")
DATALAB_CLIENT_SECRET = os.environ.get("NAVER_DATALAB_CLIENT_SECRET", "")
SEARCH_CLIENT_ID = os.environ.get("NAVER_SEARCH_CLIENT_ID", "") or DATALAB_CLIENT_ID
SEARCH_CLIENT_SECRET = os.environ.get("NAVER_SEARCH_CLIENT_SECRET", "") or DATALAB_CLIENT_SECRET
AD_API_KEY = os.environ.get("NAVER_API_KEY", "")
AD_SECRET_KEY = os.environ.get("NAVER_SECRET_KEY", "")
AD_CUSTOMER_ID = os.environ.get("NAVER_CUSTOMER_ID", "")

# Notion
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
KEYWORD_DB_ID = "d6bb5b753f1b4963891de02427411276"

# 블로그별 카테고리 키워드 (세분화 씨드 포함)
BLOG_CATEGORIES = {
    "goodisak": [
        # IT 실사용 후기 중심
        "갤럭시 추천", "아이폰 추천", "노트북 추천", "태블릿 추천", "이어폰 추천",
        "스마트워치 추천", "앱 추천", "유틸리티 앱", "무료 앱 추천",
        "유튜브 광고 차단", "윈도우 단축키", "맥북 설정", "아이패드 활용",
    ],
    "nolja100": [
        # 국내 여행 실용 정보 중심
        "국내여행 추천", "당일치기 여행", "주말 여행", "가족여행 추천",
        "입장료 할인", "펜션 추천", "글램핑 추천", "캠핑 추천",
        "지역 축제", "봄 여행지", "여름 여행지", "가을 여행지",
    ],
    "salim1su": [
        # ── 절약: 고정지출 (전기/가스/수도) ──
        "전기요금", "전기요금 절약", "전기세 폭탄", "에어컨 전기요금",
        "가스비", "가스비 절약", "도시가스 요금", "보일러 가스비",
        "수도세 절약", "수도 요금 줄이기",
        # ── 절약: 통신/인터넷 ──
        "통신비 절약", "알뜰폰 추천", "인터넷 요금 절약", "알뜰폰 바꾸는법",
        "가족결합 할인", "데이터 절약 방법", "통신 번호이동 절약",
        "인터넷 해지 위약금 면제",
        # ── 절약: 관리비 ──
        "아파트 관리비 절약", "관리비 줄이는법", "공동전기료 줄이기",
        # ── 절약: 구독서비스 ──
        "OTT 구독 절약", "구독서비스 정리 방법", "넷플릭스 요금제 비교",
        "유튜브 프리미엄 절약", "가족 공유 요금제",
        # ── 절약: 쇼핑/생활비 ──
        "마트 장보기 절약", "생활비 절약 루틴", "포인트 적립 방법",
        "온라인 장보기 꿀팁", "쿠폰 활용법", "코스트코 활용법",
        "다이소 주방 추천", "다이소 욕실 추천", "다이소 수납 추천",
        "다이소 청소 추천",
        # ── 절약: 명의변경/이사 ──
        "전기요금 명의변경", "도시가스 명의변경", "이사비용 줄이기",
        # ── 세금/연말정산 ──
        "연말정산 환급", "직장인 연말정산 공제", "교육비 세금공제",
        "의료비 세금공제", "카드 소득공제 방법", "자동차세 연납 할인",
        "재산세 분납 방법", "월세 세액공제 방법",
        # ── 건강보험 ──
        "건강보험료 줄이기", "건강보험 피부양자 등록 조건",
        "건강보험 환급금 찾기", "건강보험 환급 신청",
        "건강보험 지역가입자 절약",
        # ── 워킹맘/육아 지원 ──
        "아동수당 신청 방법", "부모급여 신청",
        "국민행복카드 혜택", "다자녀 할인 혜택",
        "워킹맘 세금공제", "육아기 근로시간 단축 방법",
        "어린이집 바우처 사용법",
        # ── 정리/수납 — 장소별 ──
        "옷장 정리법", "옷장 계절 교체 방법", "아이 옷 보관법",
        "신발장 정리법", "신발 보관법",
        "욕실 정리법", "세면대 주변 정리",
        "냉동실 정리법", "냉동식품 보관법",
        "싱크대 서랍 정리", "주방 양념 보관법",
        "이불 보관법", "계절 이불 정리",
        "베란다 정리법", "다용도실 정리",
        "아이방 장난감 정리법",
        # ── 정리/수납 — 아이템별 ──
        "밀폐용기 정리법", "텀블러 보관법",
        "비닐봉지 정리법", "쇼핑백 정리 방법",
        # ── 세탁/의류 관리 ──
        "이불 빨래 방법", "이불 세탁 주기",
        "흰옷 관리법", "흰옷 누렇게 됐을 때",
        "운동화 세탁 방법", "가죽 신발 관리",
        "니트 세탁 방법", "울 소재 세탁",
        "드라이클리닝 대신 집에서 세탁",
        "의류 장기 보관 방법",
        # ── 식품 보관 ──
        "채소 오래 보관하는 법", "과일 신선하게 보관",
        "두부 보관법", "된장 보관법", "김치 보관법",
        "밥 보관법", "식빵 보관법",
        # ── 청소/위생 (DIY만) ──
        "욕실 물때 제거법", "변기 청소 방법",
        "전자레인지 청소법", "세탁조 청소 방법",
        "싱크대 배수구 청소", "행주 삶는 방법",
        "베이킹소다 활용법", "구연산 활용법",
        # ── 루틴/계획 ──
        "주간 청소 루틴", "월별 대청소 계획",
        "워킹맘 아침 루틴", "냉장고 정리 주기",
        "한 달 생활비 관리법", "가계부 쓰는 법",
        "생활비 예산 세우는법",
    ],
    "baremi542": [
        # 장려금/지원금
        "근로장려금", "근로장려금 신청", "근로장려금 조건", "근로장려금 지급일",
        "자녀장려금", "자녀장려금 신청", "장려금 신청방법",
        # 청년 지원
        "청년지원", "청년지원금 종류", "청년 월세지원", "청년 전세자금",
        "청년도약계좌", "청년희망적금",
        # 실업급여
        "실업급여", "실업급여 조건", "실업급여 신청방법", "실업급여 계산",
        # 육아휴직
        "육아휴직", "육아휴직 급여", "육아휴직 기간", "육아휴직 신청",
        # 복지 신청
        "복지신청", "복지로 신청", "긴급복지 지원", "긴급복지지원 신청",
        # 정부지원
        "정부지원", "정부지원 대출", "정부지원금 신청", "소상공인 지원금",
        # 세금 환급/신고
        "종합소득세 환급", "종합소득세 신고방법",
        # 복지 수당
        "에너지바우처 신청", "주거급여 신청", "건강보험 환급금",
        "국민연금 납부유예",
    ],
}


# ─────────────────────────────────────────────
# 계절/시즌 키워드 필터링
# ─────────────────────────────────────────────
SEASON_KEYWORDS = {
    # 키워드 패턴 → 해당 월 (이 월에만 유효)
    "연말정산": [1, 2, 11, 12],          # 11~2월만 유효
    "연말": [11, 12],
    "크리스마스": [11, 12],
    "송년회": [11, 12],
    "신년": [1, 2],
    "새해": [1, 2],
    "설날": [1, 2],
    "설 선물": [1, 2],
    "추석": [8, 9, 10],
    "추석 선물": [8, 9, 10],
    "어버이날": [4, 5],
    "어린이날": [4, 5],
    "발렌타인": [1, 2],
    "화이트데이": [2, 3],
    "빼빼로": [10, 11],
    "여름휴가": [5, 6, 7, 8],
    "해수욕장": [6, 7, 8],
    "겨울여행": [11, 12, 1, 2],
    "벚꽃": [3, 4],
    "단풍": [9, 10, 11],
    "장마": [6, 7],
    "난방비": [10, 11, 12, 1, 2, 3],
    "보일러": [9, 10, 11, 12, 1, 2, 3],
    "에어컨": [5, 6, 7, 8, 9],
    "냉방비": [6, 7, 8, 9],
    "선풍기": [5, 6, 7, 8],
}


def _is_season_valid(keyword: str, month: int = None) -> bool:
    """현재 월 기준으로 키워드가 시즌에 맞는지 확인"""
    if month is None:
        month = datetime.now().month
    for pattern, valid_months in SEASON_KEYWORDS.items():
        if pattern in keyword:
            return month in valid_months
    return True  # 시즌 패턴에 없으면 항상 유효


def _filter_season_keywords(keywords: list, on_log=None) -> list:
    """시즌 맞지 않는 키워드 제외"""
    month = datetime.now().month
    valid = []
    for kw in keywords:
        if _is_season_valid(kw, month):
            valid.append(kw)
        else:
            _log(f"[시즌필터] 제외: {kw} (현재 {month}월)", on_log)
    return valid


def _mark_offseason_in_notion(blog_id: str, on_log=None):
    """Notion 키워드 큐에서 시즌 지난 '대기' 키워드를 '실패' 상태로 변경"""
    month = datetime.now().month
    body = {
        "filter": {
            "and": [
                {"property": "블로그", "select": {"equals": blog_id}},
                {"property": "상태", "select": {"equals": "대기"}},
            ]
        },
        "page_size": 100,
    }
    req = urllib.request.Request(
        f"{NOTION_API}/databases/{KEYWORD_DB_ID}/query",
        data=json.dumps(body).encode("utf-8"),
        headers=_notion_headers(),
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        for page in data.get("results", []):
            props = page.get("properties", {})
            kw_text = ""
            for prop_name in ["키워드", "Name", "name", "제목"]:
                prop = props.get(prop_name, {})
                if prop.get("type") == "title":
                    texts = prop.get("title", [])
                    if texts:
                        kw_text = texts[0].get("plain_text", "")
                    break
            if kw_text and not _is_season_valid(kw_text, month):
                page_id = page["id"]
                _update_page_status(page_id, "실패")
                _log(f"[시즌필터] Notion 실패 처리: {kw_text}", on_log)
    except Exception as e:
        _log(f"[시즌필터] Notion 조회 오류: {e}", on_log)


def _update_page_status(page_id: str, status: str):
    """Notion 페이지 상태 업데이트"""
    body = {"properties": {"상태": {"select": {"name": status}}}}
    req = urllib.request.Request(
        f"{NOTION_API}/pages/{page_id}",
        data=json.dumps(body).encode("utf-8"),
        headers=_notion_headers(),
        method="PATCH",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


# ─────────────────────────────────────────────
# 블로그별 금지 키워드 필터링
# ─────────────────────────────────────────────
BANNED_WORDS = {
    "goodisak": [
        # 주식/투자 (IT 블로그와 무관)
        "주가", "주식", "코인", "ETF", "펀드", "투자", "증권",
        "부동산", "청약", "대출", "금리", "환율",
        "장려금", "지원금", "실업급여", "육아휴직",
    ],
    "nolja100": [
        # 주식/투자/금융 (여행 블로그와 무관)
        "주가", "주식", "코인", "ETF", "투자", "증권",
        "대출", "금리", "부동산", "청약",
        "장려금", "지원금", "실업급여",
    ],
    "salim1su": [
        # 에어컨 청소/설치/수리 관련 차단 (전기요금은 허용)
        "에어컨청소", "에어컨 청소", "에어컨 필터", "에어컨 셀프",
        "에어컨 분해", "에어컨설치", "에어컨이전", "에어컨배관",
        "에어컨실외기청소", "시스템에어컨청소", "천장형에어컨청소",
        "에어컨분해청소", "벽걸이에어컨셀프청소",
        # 세탁기/보일러 서비스
        "세탁기청소", "세탁기 청소", "보일러청소", "보일러 청소",
        "청소업체", "청소비용", "청소가격", "출장청소", "가사도우미",
        # 금융/투자 (baremi542도 아님, 완전 금지)
        "카드", "신용카드", "체크카드", "실비", "실비보험", "종신보험", "암보험",
        "대출", "주택담보대출", "신용대출", "전세자금대출", "대출이자",
        "투자", "주식", "펀드", "ETF", "코인", "증권",
        "부동산", "아파트매매", "청약",
        "저축", "적금", "예금", "금리", "환율",
        # 정부지원금/장려금 → baremi542로 보내야 함
        "장려금", "근로장려금", "자녀장려금",
        "실업급여", "육아휴직급여",
        "지원금", "정부지원", "복지급여", "복지신청",
        "주거급여", "에너지바우처",
        "긴급복지", "긴급지원",
        "종합소득세 환급", "종합소득세 신고",
        "국민연금 납부유예",
        "청년지원", "청년수당", "청년월세",
        "소상공인 지원",
        # 이미지 필수 주제 (글로만 커버 불가) → 금지
        "레시피", "만드는법", "요리법", "요리하는법",
        "만들기", "끓이는법", "볶는법", "굽는법",
        "반찬 만드는", "국 끓이는", "찌개 끓이는",
    ],
}
# "보험" 단독은 금지하지 않음 (건강보험은 허용, 실비보험/종신보험/암보험은 금지)

# 블로그별 허용 키워드 (이 단어 중 하나라도 포함돼야 해당 블로그에서 사용 가능)
BLOG_CATEGORY_KEYWORDS = {
    "goodisak": [
        "삼성", "갤럭시", "아이폰", "아이패드", "애플", "맥북", "아이맥",
        "LG", "노트북", "태블릿", "패드", "2in1",
        "에어팟", "버즈", "이어폰", "헤드폰", "스피커",
        "스마트폰", "핸드폰", "안드로이드",
        "모니터", "TV", "공기청정기", "로봇청소기",
        "CPU", "GPU", "SSD", "RAM", "PC", "컴퓨터", "미니PC", "게이밍",
        "RTX", "RX", "인텔", "AMD", "엔비디아",
        "OTT", "넷플릭스", "티빙", "유튜브",
        "블루투스", "와이파이", "WiFi", "5G", "충전기",
        "카메라", "DSLR", "드론", "AI", "ChatGPT",
        "토스", "카카오페이", "네이버페이", "페이코", "앱",
        "윈도우", "맥OS", "맥 미니", "맥스튜디오",
        "NAS", "시놀로지", "큐냅", "서버",
        "구글", "크롬", "안드로이드", "iOS",
        "노션", "옵시디언", "슬랙", "디스코드",
        "SEO", "블로그 운영", "유튜브 운영",
    ],
    "nolja100": [
        # 여행 행위/장소 명사 (지역명 단독은 제외 — 오분류 방지)
        "여행", "맛집", "카페", "숙소", "호텔", "펜션", "리조트", "게스트하우스",
        "제주도", "제주 여행", "부산 여행", "강릉 여행", "속초 여행",
        "경주 여행", "전주 여행", "여수 여행", "통영 여행", "남해 여행",
        "서울 여행", "강원도 여행", "경기도 여행",
        "해외여행", "일본 여행", "오사카", "도쿄", "방콕", "베트남 여행", "유럽 여행",
        "캠핑", "글램핑", "드라이브 코스", "당일치기",
        "관광지", "명소", "축제", "국립공원", "등산 코스",
    ],
    "salim1su": [
        # 청소는 DIY/방법 형태만 허용 (지역+업체 서비스 키워드 차단)
        "청소 방법", "청소 꿀팁", "청소 소다", "청소 식초", "청소 락스",
        "셀프 청소", "청소하는 법", "청소하기", "직접 청소", "청소 주기",
        "청소 도구", "청소 용품", "청소기", "물때", "찌든 때", "기름때",
        "정리", "수납", "보관", "인테리어", "DIY",
        "냉장고", "냉동실", "세탁", "빨래", "다림질",
        "살림", "주방", "욕실", "싱크대", "베란다",
        "절약", "생활비", "전기요금", "가스비", "관리비",
        "통신비", "알뜰폰", "연말정산", "건강보험",
        "육아", "이유식", "초등", "아동수당", "부모급여",
        "다이소", "코스트코", "장보기", "쇼핑",
        "루틴", "계획", "가계부", "생활비 관리",
        "청소", "물때", "베이킹소다", "구연산",
        "의류", "옷", "이불",
        "보건증", "발급방법", "준비물",
        "아기방", "원룸",
    ],
    "baremi542": [
        "지원금", "지원사업", "수당", "급여", "장려금", "보조금",
        "복지", "혜택", "바우처", "누리카드",
        "신청방법", "신청자격",
        "청년지원", "청년통장", "청년저축", "청년수당", "청년월세",
        "노인복지", "장애인지원", "차상위", "기초생활수급",
        "실업급여", "육아휴직급여", "출산급여",
        "국민취업지원", "취업지원제도",
        "저축계좌", "청년도약", "청년희망적금",
        "에너지바우처", "문화누리",
        "주거급여", "의료급여", "교육급여",
        "긴급복지", "소상공인지원", "노동자 통장",
    ],
}


def _is_allowed(keyword: str, blog_id: str) -> bool:
    """키워드가 해당 블로그 카테고리에 맞는지 확인 (양성 필터).
    설정이 없는 blog_id는 모두 허용."""
    allow_words = BLOG_CATEGORY_KEYWORDS.get(blog_id, [])
    if not allow_words:
        return True
    for word in allow_words:
        if word in keyword:
            return True
    return False


_SALIM_ACBLOCK_ALLOW = {"에어컨 전기요금", "에어컨 전기세", "에어컨 전기"}  # 허용 예외

def _is_banned(keyword: str, blog_id: str) -> bool:
    """키워드가 해당 블로그의 금지 단어를 포함하는지 확인"""
    # salim1su: 에어컨+청소/설치/이전/분해/관리 조합을 정규식으로 차단
    if blog_id == "salim1su":
        kw_no_space = keyword.replace(" ", "")
        if "에어컨" in keyword and keyword not in _SALIM_ACBLOCK_ALLOW:
            import re as _re
            if _re.search(r'에어컨.{0,15}(청소|설치|이전|분해|관리|냄새|필터|셀프)', keyword):
                return True
            if kw_no_space.startswith("에어컨") and len(kw_no_space) > 4:
                # 에어컨+단순설명(전기요금 제외) 차단
                if not any(exc in keyword for exc in _SALIM_ACBLOCK_ALLOW):
                    if _re.search(r'에어컨.{0,10}(청소|설치|분해|냄새|필터|수리|이전|배관)', kw_no_space):
                        return True

    banned = BANNED_WORDS.get(blog_id, [])
    for word in banned:
        if word in keyword:
            return True
    return False


def _filter_banned_keywords(keywords: list, blog_id: str, on_log=None) -> list:
    """금지 단어 포함 키워드 제외"""
    valid = []
    for kw in keywords:
        if _is_banned(kw, blog_id):
            _log(f"[금지필터] 제외: {kw}", on_log)
        else:
            valid.append(kw)
    return valid


def filter_by_level(keywords: list, blog_id: str, on_log=None) -> list:
    """블로그 레벨에 따라 키워드를 필터링한다 (선택적 호출).

    - 초급: 롱테일 키워드 우선 — 공백 포함 3어절 이상 또는 음절 수 6자 이상
    - 중급/고급: 필터 없이 전체 반환 (추후 검색량 기준 필터 추가 예정)

    TODO: 월 검색량 데이터가 있을 경우 LEVEL_RANGES 기준으로 검색량 필터 추가
          초급 100~500, 중급 500~3000, 고급 3000+ 범위 적용

    Args:
        keywords: 키워드 문자열 리스트
        blog_id: 블로그 ID

    Returns:
        list: 레벨 기준에 맞는 키워드 리스트
    """
    info = get_blog_level(blog_id)
    level = info["level"]

    if level == "초급":
        # 롱테일 우선: 공백으로 구분된 단어가 3개 이상이거나, 연속 글자 수 6자 이상
        filtered = []
        excluded = []
        for kw in keywords:
            words = kw.split()
            char_count = len(kw.replace(" ", ""))
            if len(words) >= 3 or char_count >= 6:
                filtered.append(kw)
            else:
                excluded.append(kw)
        if excluded:
            _log(f"[레벨필터] {blog_id}({level}): {len(excluded)}개 단어 제외 (롱테일 기준 미달)", on_log)
        _log(f"[레벨필터] {blog_id}({level}): {len(filtered)}/{len(keywords)}개 통과", on_log)
        return filtered

    # 중급/고급: 현재는 전체 통과 (추후 검색량 범위 필터 추가)
    _log(f"[레벨필터] {blog_id}({level}): 전체 {len(keywords)}개 통과 (필터 미적용)", on_log)
    return keywords


def _mark_banned_in_notion(blog_id: str, on_log=None):
    """Notion 키워드 큐에서 금지 키워드 포함된 '대기' 항목을 '실패'로 변경"""
    banned = BANNED_WORDS.get(blog_id, [])
    if not banned:
        return

    body = {
        "filter": {
            "and": [
                {"property": "블로그", "select": {"equals": blog_id}},
                {"property": "상태", "select": {"equals": "대기"}},
            ]
        },
        "page_size": 100,
    }
    req = urllib.request.Request(
        f"{NOTION_API}/databases/{KEYWORD_DB_ID}/query",
        data=json.dumps(body).encode("utf-8"),
        headers=_notion_headers(),
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        count = 0
        for page in data.get("results", []):
            props = page.get("properties", {})
            kw_text = ""
            for prop_name in ["키워드", "Name", "name", "제목"]:
                prop = props.get(prop_name, {})
                if prop.get("type") == "title":
                    texts = prop.get("title", [])
                    if texts:
                        kw_text = texts[0].get("plain_text", "")
                    break
            if kw_text and _is_banned(kw_text, blog_id):
                page_id = page["id"]
                # 상태 + 메모 업데이트
                update_body = {
                    "properties": {
                        "상태": {"select": {"name": "실패"}},
                        "메모": {"rich_text": [{"text": {"content": "금지카테고리"}}]},
                    }
                }
                update_req = urllib.request.Request(
                    f"{NOTION_API}/pages/{page_id}",
                    data=json.dumps(update_body).encode("utf-8"),
                    headers=_notion_headers(),
                    method="PATCH",
                )
                try:
                    urllib.request.urlopen(update_req, timeout=10)
                    count += 1
                    _log(f"[금지필터] Notion 실패 처리: {kw_text}", on_log)
                except Exception:
                    pass
                time.sleep(0.3)
        _log(f"[금지필터] {blog_id}: {count}개 금지 키워드 실패 처리", on_log)
    except Exception as e:
        _log(f"[금지필터] Notion 조회 오류: {e}", on_log)


def _log(msg, on_log=None):
    print(msg, flush=True)
    if on_log:
        on_log(msg)


# ─────────────────────────────────────────────
# 1단계: 네이버 데이터랩 트렌드 조회
# ─────────────────────────────────────────────
def fetch_datalab_trends(blog_id: str, on_log=None) -> list:
    """블로그 카테고리별 7일 트렌드 조회 → 증가 추세 키워드 반환"""
    keywords = BLOG_CATEGORIES.get(blog_id, [])
    if not keywords:
        return []

    today = datetime.now()
    start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")

    # 키워드 그룹 구성 (최대 5개)
    keyword_groups = []
    for kw in keywords:
        keyword_groups.append({"groupName": kw, "keywords": [kw]})

    body = json.dumps({
        "startDate": start,
        "endDate": end,
        "timeUnit": "date",
        "keywordGroups": keyword_groups,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://openapi.naver.com/v1/datalab/search",
        data=body,
        headers={
            "X-Naver-Client-Id": DATALAB_CLIENT_ID,
            "X-Naver-Client-Secret": DATALAB_CLIENT_SECRET,
            "Content-Type": "application/json",
        },
    )

    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
    except Exception as e:
        _log(f"[데이터랩] API 오류: {e}", on_log)
        return keywords  # 실패 시 전체 키워드 반환

    # 트렌드 분석: 후반 3일 평균 > 전반 4일 평균이면 증가 추세
    trending = []
    for result in data.get("results", []):
        name = result["title"]
        ratios = [d["ratio"] for d in result.get("data", [])]
        if len(ratios) < 7:
            trending.append(name)
            continue
        first_half = sum(ratios[:4]) / 4
        second_half = sum(ratios[4:]) / 3
        if second_half >= first_half:  # 증가 또는 유지
            trending.append(name)
            _log(f"[데이터랩] ↑ {name} (전반 {first_half:.1f} → 후반 {second_half:.1f})", on_log)
        else:
            _log(f"[데이터랩] ↓ {name} (전반 {first_half:.1f} → 후반 {second_half:.1f})", on_log)

    _log(f"[데이터랩] {blog_id}: {len(trending)}/{len(keywords)}개 트렌딩", on_log)
    return trending


# ─────────────────────────────────────────────
# 2단계: 네이버 자동완성으로 세부 키워드 파생
# ─────────────────────────────────────────────
def fetch_autocomplete(keyword: str, on_log=None) -> list:
    """네이버 자동완성에서 연관 키워드 최대 5개 수집"""
    encoded = urllib.parse.quote(keyword)
    url = f"https://mac.search.naver.com/mobile/ac?q={encoded}&st=100&frm=mobile_nv&r_format=json"

    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    })

    try:
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        items = data.get("items", [[]])[0] if data.get("items") else []
        suggestions = []
        for item in items:
            if isinstance(item, list) and len(item) > 0:
                suggestions.append(item[0])
            elif isinstance(item, str):
                suggestions.append(item)
        # 원본 키워드와 동일한 것 제외
        suggestions = [s for s in suggestions if s != keyword]
        return suggestions[:5]
    except Exception as e:
        _log(f"[자동완성] {keyword} 오류: {e}", on_log)
        return []


# ─────────────────────────────────────────────
# 3단계: 네이버 검색광고 API로 검색량 확인
# ─────────────────────────────────────────────
def _generate_signature(timestamp, method, uri):
    """네이버 검색광고 API HMAC 서명 생성"""
    message = f"{timestamp}.{method}.{uri}"
    sign = hmac.new(
        AD_SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(sign).decode("utf-8")


def _resolve_ad_keys():
    """검색광고 API 키 해석 (숫자=Customer ID, 긴 문자열=API Key)"""
    api_key = AD_API_KEY
    customer_id = AD_CUSTOMER_ID
    # 숫자만으로 구성된 쪽이 Customer ID
    if AD_API_KEY.isdigit() and not AD_CUSTOMER_ID.isdigit():
        customer_id = AD_API_KEY
        api_key = AD_CUSTOMER_ID
    return api_key, customer_id


def fetch_search_volume(keywords: list, on_log=None) -> dict:
    """키워드 리스트의 월간 검색량 조회 → {keyword: volume} 반환"""
    if not AD_API_KEY or not AD_SECRET_KEY or not AD_CUSTOMER_ID:
        _log("[검색광고] API 키 미설정 — 검색량 확인 스킵", on_log)
        return {kw: 999 for kw in keywords}  # 기본값으로 통과

    api_key, customer_id = _resolve_ad_keys()
    results = {}

    # 키워드 1개씩 개별 요청
    for kw in keywords:
        timestamp = str(int(time.time() * 1000))
        uri = "/keywordstool"
        method = "GET"
        signature = _generate_signature(timestamp, method, uri)

        # 검색광고 API는 hintKeywords에 공백 불허 → 공백 제거
        hint_kw = kw.replace(" ", "")
        params = urllib.parse.urlencode({
            "hintKeywords": hint_kw,
            "showDetail": "1",
        })
        url = f"https://api.searchad.naver.com{uri}?{params}"

        req = urllib.request.Request(url, headers={
            "X-Timestamp": timestamp,
            "X-API-KEY": api_key,
            "X-Customer": customer_id,
            "X-Signature": signature,
        })

        try:
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            found = False
            for item in data.get("keywordList", []):
                rel_kw = item.get("relKeyword", "")
                pc = item.get("monthlyPcQcCnt", 0)
                mobile = item.get("monthlyMobileQcCnt", 0)
                pc = int(pc) if isinstance(pc, (int, float)) else 0
                mobile = int(mobile) if isinstance(mobile, (int, float)) else 0
                vol = pc + mobile
                # 공백 제거 후 비교 (API가 공백 없이 반환)
                if rel_kw.replace(" ", "") == hint_kw:
                    results[kw] = vol
                    found = True
                    break
            if not found:
                # 첫 번째 결과라도 사용 (가장 유사한 키워드)
                first = data.get("keywordList", [{}])[0] if data.get("keywordList") else {}
                if first:
                    pc = first.get("monthlyPcQcCnt", 0)
                    mobile = first.get("monthlyMobileQcCnt", 0)
                    pc = int(pc) if isinstance(pc, (int, float)) else 0
                    mobile = int(mobile) if isinstance(mobile, (int, float)) else 0
                    results[kw] = pc + mobile
                else:
                    results[kw] = 0
        except urllib.error.HTTPError as e:
            err_body = e.read().decode()[:200]
            if e.code == 403:
                _log("[검색광고] API 키 인증 실패 — 기본값(999)으로 통과", on_log)
                return {k: 999 for k in keywords}
            _log(f"[검색광고] {kw} 오류 ({e.code}): {err_body}", on_log)
            results[kw] = 0
        except Exception as e:
            _log(f"[검색광고] {kw} 오류: {e}", on_log)
            results[kw] = 0

        time.sleep(0.3)  # rate limit

    return results


def classify_keywords(keywords_with_volume: dict, on_log=None,
                      min_vol: int = 300, max_vol: int = 100_000) -> list:
    """검색량 기준으로 키워드 분류.

    Args:
        keywords_with_volume: {keyword: volume} 딕셔너리
        min_vol: 최소 검색량 (기본 300 — blog_visitor로 동적 결정 가능)
        max_vol: 최대 검색량 (기본 무제한)
    """
    result = []
    for kw, vol in keywords_with_volume.items():
        if vol < min_vol:
            _log(f"[분류] 제외(검색량 부족): {kw} ({vol:,} < {min_vol:,})", on_log)
            continue
        if vol > max_vol:
            _log(f"[분류] 제외(검색량 초과): {kw} ({vol:,} > {max_vol:,})", on_log)
            continue
        ktype = "트렌딩" if vol >= 5000 else "에버그린"
        result.append({"keyword": kw, "volume": vol, "type": ktype})
        _log(f"[분류] {kw}: {vol:,}회/월 ({ktype})", on_log)
    return result


# ─────────────────────────────────────────────
# 4단계: Notion 키워드 큐 DB 저장
# ─────────────────────────────────────────────
def _notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _fetch_existing_keywords() -> set:
    """Notion DB에서 기존 키워드 목록 조회"""
    existing = set()
    url = f"{NOTION_API}/databases/{KEYWORD_DB_ID}/query"
    has_more = True
    start_cursor = None

    while has_more:
        body = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=_notion_headers(),
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            for page in data.get("results", []):
                props = page.get("properties", {})
                # "키워드" 또는 "Name" 프로퍼티에서 제목 추출
                for prop_name in ["키워드", "Name", "name", "제목"]:
                    prop = props.get(prop_name, {})
                    if prop.get("type") == "title":
                        texts = prop.get("title", [])
                        if texts:
                            existing.add(texts[0].get("plain_text", ""))
                        break
            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")
        except Exception as e:
            _log(f"[Notion] 기존 키워드 조회 오류: {e}")
            break

    return existing


def save_to_notion(keywords: list, blog_id: str, on_log=None) -> int:
    """키워드 리스트를 Notion DB에 저장 (중복 제외)"""
    existing = _fetch_existing_keywords()
    _log(f"[Notion] 기존 키워드 {len(existing)}개 확인", on_log)

    saved = 0
    for item in keywords:
        kw = item["keyword"]
        if kw in existing:
            _log(f"[Notion] 중복 스킵: {kw}", on_log)
            continue

        body = {
            "parent": {"database_id": KEYWORD_DB_ID},
            "properties": {
                "키워드": {
                    "title": [{"text": {"content": kw}}]
                },
                "블로그": {
                    "select": {"name": blog_id}
                },
                "상태": {
                    "select": {"name": "대기"}
                },
                "검색량": {
                    "number": item["volume"]
                },
                "유형": {
                    "select": {"name": item["type"]}
                },
                "수집일": {
                    "date": {"start": datetime.now().strftime("%Y-%m-%d")}
                },
            },
        }

        req = urllib.request.Request(
            f"{NOTION_API}/pages",
            data=json.dumps(body).encode("utf-8"),
            headers=_notion_headers(),
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            if resp.status == 200:
                saved += 1
                _log(f"[Notion] 저장: {kw} ({item['volume']:,}회, {item['type']})", on_log)
        except Exception as e:
            _log(f"[Notion] 저장 실패 ({kw}): {e}", on_log)

        time.sleep(0.3)  # rate limit

    return saved


# ─────────────────────────────────────────────
# 전체 수집 파이프라인
# ─────────────────────────────────────────────
def crawl_keywords(blog_id: str = None, on_log=None) -> dict:
    """전체 키워드 수집 파이프라인 실행"""
    targets = [blog_id] if blog_id else list(BLOG_CATEGORIES.keys())
    total_results = {}

    for bid in targets:
        _log(f"\n{'='*50}", on_log)
        _log(f"[수집] {bid} 키워드 수집 시작", on_log)
        _log(f"{'='*50}", on_log)

        # 0단계: Notion에서 시즌 지난/금지 키워드 실패 처리
        _log(f"\n[0단계] 시즌/금지 키워드 필터링...", on_log)
        _mark_offseason_in_notion(bid, on_log)
        _mark_banned_in_notion(bid, on_log)

        # 1단계: 데이터랩 트렌드
        _log(f"\n[1단계] 데이터랩 트렌드 조회...", on_log)
        trending = fetch_datalab_trends(bid, on_log)

        if not trending:
            _log(f"[수집] {bid}: 트렌딩 키워드 없음 — 스킵", on_log)
            total_results[bid] = 0
            continue

        # 2단계: 자동완성 2단계 파생 (씨드 → 1차 파생 → 2차 파생)
        _log(f"\n[2단계] 자동완성 키워드 파생 (2단계)...", on_log)
        first_gen = []
        for kw in trending:
            suggestions = fetch_autocomplete(kw, on_log)
            if suggestions:
                _log(f"[1차] {kw} → {suggestions}", on_log)
                first_gen.extend(suggestions)
            time.sleep(0.2)

        # 2차 파생: 1차 결과를 다시 자동완성
        second_gen = []
        for kw in first_gen:
            suggestions = fetch_autocomplete(kw, on_log)
            if suggestions:
                _log(f"[2차] {kw} → {suggestions}", on_log)
                second_gen.extend(suggestions)
            time.sleep(0.2)

        # 전체 블로그: 2차 파생 키워드만 저장 (씨드/1차는 중간 재료로만 사용)
        _log(f"[{bid}] 2차 파생 키워드만 저장 모드: {len(second_gen)}개", on_log)
        all_keywords = list(dict.fromkeys(second_gen))

        # 중복 제거 후 최종 후보
        all_keywords = list(dict.fromkeys(all_keywords))
        _log(f"[수집] 총 {len(all_keywords)}개 후보 키워드", on_log)

        # 시즌 필터링
        before_count = len(all_keywords)
        all_keywords = _filter_season_keywords(all_keywords, on_log)
        if len(all_keywords) < before_count:
            _log(f"[수집] 시즌 필터 후 {len(all_keywords)}개 ({before_count - len(all_keywords)}개 제외)", on_log)

        # 금지 키워드 필터링
        before_count = len(all_keywords)
        all_keywords = _filter_banned_keywords(all_keywords, bid, on_log)
        if len(all_keywords) < before_count:
            _log(f"[수집] 금지 필터 후 {len(all_keywords)}개 ({before_count - len(all_keywords)}개 제외)", on_log)

        # 3단계: 검색량 확인
        _log(f"\n[3단계] 검색량 확인...", on_log)
        volumes = fetch_search_volume(all_keywords, on_log)

        # 방문자 수 기반 동적 검색량 범위
        try:
            vrange = blog_visitor.get_volume_range_for_blog(bid, on_log)
            min_vol = vrange["min"]
            max_vol = vrange["max"]
        except Exception as e:
            _log(f"[방문자] 범위 조회 실패: {e} — 기본값(300~100000) 사용", on_log)
            min_vol, max_vol = 300, 100_000

        qualified = classify_keywords(volumes, on_log, min_vol=min_vol, max_vol=max_vol)
        _log(
            f"[수집] {len(qualified)}개 키워드 통과 "
            f"(검색량 {min_vol:,}~{max_vol:,})", on_log
        )

        # 4단계: Notion 저장
        _log(f"\n[4단계] Notion 저장...", on_log)
        saved = save_to_notion(qualified, bid, on_log)
        total_results[bid] = saved
        _log(f"[수집] {bid}: {saved}개 새 키워드 저장 완료", on_log)

    return total_results


# ─────────────────────────────────────────────
# 5단계: APScheduler 자동 실행
# ─────────────────────────────────────────────
_scheduler = None


def start_scheduler(on_log=None):
    """4시간마다 키워드 수집 + 방문자 수 갱신 스케줄러 시작"""
    global _scheduler
    from apscheduler.schedulers.background import BackgroundScheduler
    from datetime import datetime

    if _scheduler and _scheduler.running:
        _log("[스케줄러] 이미 실행 중", on_log)
        return _scheduler

    _scheduler = BackgroundScheduler()

    # 키워드 수집 (4시간 간격, 즉시 실행 안 함)
    _scheduler.add_job(
        crawl_keywords,
        "interval",
        hours=4,
        kwargs={"on_log": on_log},
        id="keyword_crawl",
        next_run_time=None,
    )

    # 방문자 수 갱신 (4시간 간격, 시작 즉시 1회 실행)
    _scheduler.add_job(
        blog_visitor.refresh_all,
        "interval",
        hours=4,
        kwargs={"on_log": on_log},
        id="visitor_refresh",
        next_run_time=datetime.now(),
    )

    _scheduler.start()
    _log("[스케줄러] 4시간 간격 키워드 수집 + 방문자 수 갱신 스케줄러 시작", on_log)
    return _scheduler


def stop_scheduler(on_log=None):
    """스케줄러 중지"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _log("[스케줄러] 스케줄러 중지", on_log)
    _scheduler = None


# ─────────────────────────────────────────────
# 단독 실행
# ─────────────────────────────────────────────
if __name__ == "__main__":
    results = crawl_keywords()
    print(f"\n{'='*50}")
    print("[최종 결과]")
    for bid, count in results.items():
        print(f"  {bid}: {count}개 저장")
    print(f"{'='*50}")
