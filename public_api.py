"""공공데이터포털 API 연동 모듈

블로그 글 생성 전 실제 데이터를 extra_context로 주입해 할루시네이션 방지.

지원 API:
- 한국관광공사 축제/행사정보  → nolja100, triplog
- 정부24 공공서비스 정보      → baremi542, goodisak, salim1su
"""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# .env 로드
_env = Path(__file__).parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, _, v = _line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

_RAW_KEY = os.environ.get("PUBLIC_DATA_API_KEY", "")
# URL 인코딩된 키를 디코딩
SERVICE_KEY = urllib.parse.unquote(_RAW_KEY)

# 한국관광공사 API
_FESTIVAL_URL = "https://apis.data.go.kr/B551011/KorService2/searchFestival2"
# 정부24 공공서비스 API
_GOV_SERVICE_URL = "https://api.odcloud.kr/api/gov24/v3/serviceList"


def _get(url: str, params: dict) -> dict:
    params["serviceKey"] = SERVICE_KEY
    params["_type"] = "json"
    full_url = url + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(full_url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def _extract_region(keyword: str) -> str:
    """키워드에서 지역명 추출 (단순 포함 검색)."""
    regions = [
        "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
        "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
        "수원", "고양", "용인", "성남", "부천", "안산", "화성", "남양주",
        "전주", "청주", "천안", "안양", "창원", "포항", "김해", "진주",
        "속초", "강릉", "춘천", "양양", "평창", "여수", "순천", "목포",
        "경주", "안동", "통영", "거제", "남해",
    ]
    for r in regions:
        if r in keyword:
            return r
    return ""


def fetch_festival_context(keyword: str, on_log=None) -> str:
    """키워드 지역의 현재~3개월 내 축제 정보를 문자열로 반환.

    Returns: extra_context 문자열 (없으면 빈 문자열)
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if not SERVICE_KEY:
        log("[PublicAPI] API 키 없음 — 축제 데이터 스킵")
        return ""

    region = _extract_region(keyword)
    today = datetime.now()
    start_date = today.strftime("%Y%m%d")
    # 3개월 후
    end_month = today.month + 3
    end_year = today.year + (end_month - 1) // 12
    end_month = ((end_month - 1) % 12) + 1
    end_date = f"{end_year}{end_month:02d}28"

    params = {
        "numOfRows": "10",
        "pageNo": "1",
        "MobileOS": "ETC",
        "MobileApp": "blog-auto",
        "eventStartDate": start_date,
        "eventEndDate": end_date,
        "arrange": "A",  # 제목순
    }
    if region:
        # areaCode 매핑 (한국관광공사 지역코드)
        area_map = {
            "서울": "1", "인천": "2", "대전": "3", "대구": "4", "광주": "5",
            "부산": "6", "울산": "7", "세종": "8", "경기": "31", "강원": "32",
            "충북": "33", "충남": "34", "경북": "35", "경남": "36", "전북": "37",
            "전남": "38", "제주": "39",
        }
        area_code = area_map.get(region, "")
        if area_code:
            params["areaCode"] = area_code
            log(f"[PublicAPI] 축제 검색: {region} (areaCode={area_code}), {start_date}~{end_date}")
        else:
            log(f"[PublicAPI] 축제 검색: 전국, {start_date}~{end_date}")
    else:
        log(f"[PublicAPI] 축제 검색: 전국 (지역 미추출), {start_date}~{end_date}")

    data = _get(_FESTIVAL_URL, params)

    if "error" in data:
        log(f"[PublicAPI] 축제 API 오류: {data['error']}")
        return ""

    try:
        items = data["response"]["body"]["items"]
        if not items:
            log("[PublicAPI] 축제 검색 결과 없음")
            return ""
        item_list = items.get("item", [])
        if isinstance(item_list, dict):
            item_list = [item_list]
        if not item_list:
            log("[PublicAPI] 축제 항목 없음")
            return ""

        lines = [f"[현재 {region or '전국'} 축제/행사 정보 (공공데이터포털)]"]
        for item in item_list[:5]:
            name = item.get("title", "")
            addr = item.get("addr1", "") + item.get("addr2", "")
            start = item.get("eventstartdate", "")
            end = item.get("eventenddate", "")
            tel = item.get("tel", "")
            if name:
                lines.append(f"- 행사명: {name}")
                if addr:
                    lines.append(f"  주소: {addr}")
                if start:
                    lines.append(f"  기간: {start} ~ {end}")
                if tel:
                    lines.append(f"  전화: {tel}")
        ctx = "\n".join(lines)
        log(f"[PublicAPI] 축제 데이터 {len(item_list)}건 수집 완료")
        return ctx
    except Exception as e:
        log(f"[PublicAPI] 축제 데이터 파싱 실패: {e}")
        return ""


def fetch_gov_service_context(keyword: str, on_log=None) -> str:
    """키워드 관련 정부24 공공서비스 정보를 문자열로 반환.

    Returns: extra_context 문자열 (없으면 빈 문자열)
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if not SERVICE_KEY:
        log("[PublicAPI] API 키 없음 — 공공서비스 데이터 스킵")
        return ""

    # 키워드에서 검색어 추출 (앞 2단어)
    words = keyword.replace(",", " ").split()
    search_kw = " ".join(words[:2]) if words else keyword[:10]

    params = {
        "page": "1",
        "perPage": "5",
        "cond[서비스명::LIKE]": search_kw,
    }
    log(f"[PublicAPI] 공공서비스 검색: '{search_kw}'")

    data = _get(_GOV_SERVICE_URL, params)

    if "error" in data:
        log(f"[PublicAPI] 공공서비스 API 오류: {data['error']}")
        return ""

    try:
        items = data.get("data", [])
        if not items:
            log("[PublicAPI] 공공서비스 검색 결과 없음")
            return ""

        lines = [f"[정부24 공공서비스 정보 ('{search_kw}' 검색 결과)]"]
        for item in items[:3]:
            name = item.get("서비스명", "")
            summary = item.get("서비스목적요약", "") or item.get("서비스목적", "")
            dept = item.get("소관기관명", "")
            target = item.get("지원대상", "")
            amount = item.get("지원내용", "")
            url = item.get("상세조회URL", "")
            if name:
                lines.append(f"\n[서비스] {name}")
                if dept:
                    lines.append(f"  소관기관: {dept}")
                if target:
                    lines.append(f"  지원대상: {target[:100]}")
                if amount:
                    lines.append(f"  지원내용: {amount[:150]}")
                if summary:
                    lines.append(f"  요약: {summary[:100]}")
                if url:
                    lines.append(f"  상세: {url}")
        ctx = "\n".join(lines)
        log(f"[PublicAPI] 공공서비스 데이터 {len(items)}건 수집 완료")
        return ctx
    except Exception as e:
        log(f"[PublicAPI] 공공서비스 데이터 파싱 실패: {e}")
        return ""


def fetch_context_for_blog(blog_id: str, keyword: str, on_log=None) -> str:
    """blog_id에 따라 적합한 공공API 데이터를 가져와 extra_context로 반환.

    overnight_run.py → generate_text(..., extra_context=...) 에 주입용.
    """
    if blog_id in {"nolja100", "triplog"}:
        # 여행 블로그: 축제/행사 정보
        return fetch_festival_context(keyword, on_log=on_log)
    elif blog_id in {"baremi542", "goodisak", "salim1su"}:
        # 정보성 블로그: 정부24 공공서비스
        # 복지/지원금/혜택 키워드일 때만 (IT나 살림 키워드엔 무관)
        welfare_hints = ["지원", "혜택", "신청", "급여", "보조", "복지", "정책", "수당", "바우처"]
        if any(h in keyword for h in welfare_hints):
            return fetch_gov_service_context(keyword, on_log=on_log)
    return ""
