"""Agoda 제휴마케팅 API — 여행 블로그 호텔 링크 자동 삽입"""
# .env에 AGODA_API_KEY, AGODA_SITE_ID 필요
# nolja100 전용

import os
import json
import urllib.parse
import urllib.request
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("AGODA_API_KEY", "")
SITE_ID = os.getenv("AGODA_SITE_ID", "")

CONTENT_API_URL = "https://affiliateapi7.agoda.com/affiliateservice/lt_v1"

DUMMY_HOTELS = [
    {"name": "추천 호텔 1 (4성급)", "url": "https://www.agoda.com/partners/partnersearch.aspx?hid=dummy1"},
    {"name": "추천 호텔 2 (5성급)", "url": "https://www.agoda.com/partners/partnersearch.aspx?hid=dummy2"},
    {"name": "추천 호텔 3 (가성비)", "url": "https://www.agoda.com/partners/partnersearch.aspx?hid=dummy3"},
]


def search_hotels(destination: str, limit: int = 3) -> list:
    """Agoda Content API로 호텔을 검색한다.

    API 키가 없거나 호출 실패 시 빈 리스트를 반환한다.

    Returns:
        list[dict]: [{"name": str, "url": str}, ...]
    """
    if not API_KEY or not SITE_ID or "여기에_키_입력" in API_KEY:
        return []

    try:
        headers = {
            "Authorization": f"site-id={SITE_ID};api-key={API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = json.dumps({
            "criteria": {
                "additional": {
                    "currency": "KRW",
                    "language": "ko-kr",
                    "occupancy": {"numberOfAdult": 2, "numberOfChildren": 0},
                },
                "checkIn": "",
                "checkOut": "",
                "cityId": 0,
                "countryCode": "",
                "searchText": destination,
            },
            "paging": {"pageNo": 1, "pageSize": limit},
        }).encode("utf-8")

        req = urllib.request.Request(
            CONTENT_API_URL,
            data=payload,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        hotels = []
        for item in data.get("results", [])[:limit]:
            hotel_id = item.get("hotelId", "")
            name = item.get("hotelName", destination)
            url = (
                f"https://www.agoda.com/partners/partnersearch.aspx"
                f"?site_id={SITE_ID}&hid={hotel_id}"
            )
            hotels.append({"name": name, "url": url})
        return hotels

    except Exception:
        return []


def get_hotel_block(keyword: str) -> str:
    """여행지 키워드로 호텔 3개를 검색하고 마크다운 링크 블록을 반환한다.

    API 키가 없거나 오류 발생 시 빈 문자열을 반환한다 (글 발행 중단 없음).
    """
    if not API_KEY or not SITE_ID or "여기에_키_입력" in API_KEY:
        return ""

    try:
        hotels = search_hotels(keyword, limit=3)

        if not hotels:
            return ""

        lines = ["\n\n---\n\n### 추천 숙소\n"]
        for h in hotels:
            lines.append(f"- [{h['name']}]({h['url']})")
        lines.append(
            "\n*본 포스팅에는 Agoda 제휴 링크가 포함되어 있으며, "
            "예약 시 소정의 수수료를 받을 수 있습니다.*\n"
        )
        return "\n".join(lines)

    except Exception:
        return ""
