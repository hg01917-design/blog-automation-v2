"""계정 및 블로그 설정"""

# Chrome CDP 설정 — 블로그 전용 프로필
CHROME_CONFIG = {
    "executable": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "profile": "Profile 1",
    "port": 9222,
    "debug_url": "http://localhost:9222",
}

ACCOUNTS = [
    {
        "blog": "goodisak",
        "platform": "tistory",
        "kakao_id": "isag27511",
        "editor_url": "https://goodisak.tistory.com/manage/newpost",
        "category": "IT",
    },
    {
        "blog": "nolja100",
        "platform": "tistory",
        "kakao_id": "baremi542",
        "editor_url": "https://nolja100.tistory.com/manage/newpost",
        "category": "여행",
    },
    {
        "blog": "salim1su",
        "platform": "naver",
        "naver_id": "daonna525",
        "editor_url": "https://blog.naver.com/salim1su/postwrite",
        "category": "살림",
    },
]

# 계정별 빠른 조회용
ACCOUNT_MAP = {a["blog"]: a for a in ACCOUNTS}

# 블로그별 Notion 프롬프트 페이지 ID
PROMPT_PAGES = {
    "goodisak": "3296d296d9c1811cabe8d3dec2de4274",
    "nolja100": "3296d296d9c181a390c8c54b8dbb1401",
    "salim1su": "3296d296d9c18164a390e019bad2999a",
    "baremi542": "3296d296d9c181648d01f433963557c6",
}
