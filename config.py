"""계정 및 블로그 설정"""
import sys
import os


def _find_chrome() -> str:
    """OS별 Chrome 실행 파일 경로 자동 탐지"""
    if sys.platform == "darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    elif sys.platform == "win32":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return candidates[0]  # 기본값
    else:
        return "google-chrome"


# Chrome CDP 설정 — 블로그 전용 프로필
CHROME_CONFIG = {
    "executable": _find_chrome(),
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
    {
        "blog": "baremi542",
        "platform": "wordpress",
        "editor_url": "https://baremi542.com/wp-admin/post-new.php",
        "category": "정부지원금",
    },
    {
        "blog": "triplog",
        "platform": "wordpress",
        "editor_url": "https://app.baremi542.com/wp-admin/post-new.php",
        "category": "여행",
        "wp_user_env": "TRIPLOG_WP_USER",
        "wp_pass_env": "TRIPLOG_WP_APP_PASSWORD",
    },
    {
        "blog": "woll100",
        "platform": "tistory",
        "kakao_id": "wolbaeg100",
        "editor_url": "https://woll100.tistory.com/manage/newpost",
        "category": "교통정보",
    },
    {
        "blog": "phn0502",
        "platform": "tistory",
        "kakao_id": "baremi542",
        "editor_url": "https://phn0502.tistory.com/manage/newpost",
        "category": "영화",
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
