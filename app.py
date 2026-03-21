import sys
import os
import subprocess
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QLineEdit, QTextEdit, QPushButton, QFrame,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QRect, QPoint, QSize
from PyQt5.QtGui import QFont, QPainter, QColor, QPen, QBrush, QMovie
from pathlib import Path

# 같은 디렉토리의 모듈 import를 위해 경로 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import ACCOUNTS, ACCOUNT_MAP
from claude_playwright import generate_text
from login_playwright import login_blog, login_naver
from poster import post_single, post_all


# ─── GIF 기반 픽셀 캐릭터 위젯 ───

ASSETS_DIR = Path(__file__).parent / "assets"

AGENT_NAMES = {
    "keyword": "키워드",
    "writer": "작성",
    "review": "검수",
    "final_review": "최종",
    "poster": "포스팅",
}


class PixelCharacterWidget(QWidget):
    """GIF 애니메이션 기반 에이전트 캐릭터 위젯"""

    def __init__(self, agent_id, parent=None):
        super().__init__(parent)
        self.agent_id = agent_id
        self.agent_name = AGENT_NAMES.get(agent_id, agent_id)
        self.state = "idle"
        self.task_text = "대기"

        self.setFixedSize(210, 280)

        # GIF 로드
        self.movies = {}
        for state in ("idle", "working", "done", "failed"):
            gif_path = ASSETS_DIR / f"{agent_id}_{state}.gif"
            if gif_path.exists():
                movie = QMovie(str(gif_path))
                movie.setScaledSize(QSize(192, 192))
                self.movies[state] = movie

        # 메인 레이아웃
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(6)

        # GIF 표시 라벨
        self.gif_label = QLabel()
        self.gif_label.setFixedSize(192, 192)
        self.gif_label.setAlignment(Qt.AlignCenter)
        self.gif_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.gif_label, alignment=Qt.AlignCenter)

        # 이름 라벨
        self.name_label = QLabel(self.agent_name)
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setStyleSheet(
            "color: #ffffff; font-size: 16px; font-weight: bold; letter-spacing: 1px; "
            "background: #333; border-radius: 5px; padding: 3px 10px; border: none;")
        layout.addWidget(self.name_label)

        # 상태 라벨
        self.status_label = QLabel(self.task_text)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(
            "color: #aaa; font-size: 13px; font-weight: bold; "
            "background: transparent; border: none; padding: 2px 0;")
        layout.addWidget(self.status_label)

        # 초기 GIF 시작
        self._play_state("idle")

    def set_state(self, state):
        self.state = state
        labels = {"idle": "대기", "working": "작업 중...",
                  "done": "완료!", "failed": "실패"}
        self.task_text = labels.get(state, state)
        self._play_state(state)

    def _play_state(self, state):
        # 기존 GIF 중지
        for movie in self.movies.values():
            movie.stop()

        # 상태별 색상 설정
        state_colors = {
            "idle": "#888888",
            "working": "#4ade80",
            "done": "#22c55e",
            "failed": "#f87171",
        }
        state_bg = {
            "idle": "#1e1e2e",
            "working": "#0b2a1a",
            "done": "#0a250a",
            "failed": "#2a0b0b",
        }
        state_border = {
            "idle": "#444455",
            "working": "#4ade80",
            "done": "#22c55e",
            "failed": "#ef4444",
        }
        state_name_bg = {
            "idle": "#333344",
            "working": "#14532d",
            "done": "#166534",
            "failed": "#7f1d1d",
        }

        # 위젯 전체 배경 + 테두리 (상태별 색깔 구분)
        self.setStyleSheet(
            f"background: {state_bg.get(state, '#1e1e2e')}; "
            f"border: 3px solid {state_border.get(state, '#444455')}; "
            "border-radius: 12px;"
        )

        # 이름 라벨 배경색
        self.name_label.setStyleSheet(
            f"color: #ffffff; font-size: 16px; font-weight: bold; letter-spacing: 1px; "
            f"background: {state_name_bg.get(state, '#333344')}; "
            "border-radius: 5px; padding: 3px 10px; border: none;"
        )

        # 상태 텍스트 + 색상
        self.status_label.setText(self.task_text)
        self.status_label.setStyleSheet(
            f"color: {state_colors.get(state, '#888')}; font-size: 13px; font-weight: bold; "
            "background: transparent; border: none; padding: 2px 0;"
        )

        # 새 GIF 재생
        movie = self.movies.get(state)
        if movie:
            self.gif_label.setMovie(movie)
            movie.start()
        else:
            self.gif_label.setText("?")
            self.gif_label.setStyleSheet(
                "color: #888; font-size: 48px; background: #1a1a2e; "
                "border: 1px solid #333; border-radius: 4px;"
            )


class OrchestratorWorker(QThread):
    """orchestrator.run_all()을 실행하는 워커"""
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str, str)  # (agent_name, state)
    finished = pyqtSignal(str)

    def __init__(self, blog_ids=None):
        super().__init__()
        self.blog_ids = blog_ids

    def run(self):
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agents"))
            from agents import orchestrator
            results = orchestrator.run_all(
                blog_ids=self.blog_ids,
                on_log=self._emit_log,
                on_status=self._emit_status,
            )
            success = sum(1 for r in results if r["success"])
            total = len(results)
            self.finished.emit(f"[에이전트] 완료: {success}/{total} 성공")
        except Exception as e:
            self.finished.emit(f"[에이전트 오류] {e}")

    def _emit_log(self, msg):
        self.log_signal.emit(msg)

    def _emit_status(self, agent, state):
        self.status_signal.emit(agent, state)


class SingleAgentWorker(QThread):
    """orchestrator.run_single()을 실행하는 워커"""
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str, str)
    finished = pyqtSignal(str)

    def __init__(self, blog_id, keyword=None):
        super().__init__()
        self.blog_id = blog_id
        self.keyword = keyword

    def run(self):
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agents"))
            from agents import orchestrator
            result = orchestrator.run_single(
                self.blog_id,
                keyword=self.keyword,
                on_log=self._emit_log,
                on_status=self._emit_status,
            )
            if result["success"]:
                self.finished.emit(f"[에이전트] 발행 완료: {result['title']}")
            else:
                self.finished.emit(f"[에이전트] 실패: {result['reason']}")
        except Exception as e:
            self.finished.emit(f"[에이전트 오류] {e}")

    def _emit_log(self, msg):
        self.log_signal.emit(msg)

    def _emit_status(self, agent, state):
        self.status_signal.emit(agent, state)


class SchedulerWorker(QThread):
    """스케줄러를 GUI 내에서 실행하는 워커"""
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str, str)
    finished = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True

    def run(self):
        import random
        from datetime import datetime, timedelta
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agents"))
        from agents import orchestrator

        START_HOUR, END_HOUR = 7, 23
        MIN_INTERVAL, MAX_INTERVAL = 60, 180
        BLOG_ORDER = ["goodisak", "nolja100", "salim1su"]

        self._emit_log("[스케줄러] 시작 (7:00~23:00, 60~180분 간격)")

        while not self._stop_flag:
            hour = datetime.now().hour
            if hour < START_HOUR or hour >= END_HOUR:
                # 비활동 시간 — 다음 7시까지 대기
                now = datetime.now()
                if hour >= END_HOUR:
                    target = (now + timedelta(days=1)).replace(
                        hour=START_HOUR, minute=0, second=0)
                else:
                    target = now.replace(hour=START_HOUR, minute=0, second=0)
                wait = (target - now).total_seconds()
                self._emit_log(
                    f"[스케줄러] 비활동 시간 — {target.strftime('%H:%M')}까지 대기")
                self._sleep(wait)
                continue

            # 사이클 실행
            for blog_id in BLOG_ORDER:
                if self._stop_flag:
                    break
                if not (START_HOUR <= datetime.now().hour < END_HOUR):
                    break

                self._emit_log(f"[스케줄러] {blog_id} 파이프라인 시작")
                try:
                    result = orchestrator.run_single(
                        blog_id,
                        on_log=self._emit_log,
                        on_status=self._emit_status,
                    )
                    if result["success"]:
                        self._emit_log(
                            f"[스케줄러] {blog_id} 발행 완료: {result['title']}")
                    else:
                        self._emit_log(
                            f"[스케줄러] {blog_id} 실패: {result['reason']}")
                except Exception as e:
                    self._emit_log(f"[스케줄러] {blog_id} 오류: {e}")

                # 블로그 간 쿨다운
                if blog_id != BLOG_ORDER[-1] and not self._stop_flag:
                    cd = random.randint(5, 15) * 60
                    self._emit_log(
                        f"[스케줄러] 다음 블로그까지 {cd // 60}분 대기")
                    self._sleep(cd)

            if self._stop_flag:
                break

            # 다음 사이클까지 랜덤 대기
            interval = random.randint(MIN_INTERVAL, MAX_INTERVAL) * 60
            next_time = datetime.now() + timedelta(seconds=interval)
            self._emit_log(
                f"[스케줄러] 다음 사이클: {next_time.strftime('%H:%M')} "
                f"({interval // 60}분 후)")
            self._sleep(interval)

        self.finished.emit("[스케줄러] 종료됨")

    def _sleep(self, seconds):
        import time as _time
        end = _time.time() + seconds
        while _time.time() < end and not self._stop_flag:
            _time.sleep(min(5, end - _time.time()))

    def _emit_log(self, msg):
        self.log_signal.emit(msg)

    def _emit_status(self, agent, state):
        self.status_signal.emit(agent, state)


DARK_STYLE = """
QMainWindow { background: #1e1e1e; }
QLabel { color: #e0e0e0; font-size: 14px; }
QComboBox, QLineEdit {
    background: #2d2d2d; color: #e0e0e0; border: 1px solid #555;
    border-radius: 6px; padding: 6px 10px; font-size: 14px;
}
QTextEdit {
    background: #111; color: #d4d4d4; border: 1px solid #333;
    border-radius: 8px; padding: 8px; font-size: 13px;
}
QPushButton {
    padding: 10px 20px; border: none; border-radius: 6px;
    font-size: 14px; color: #fff;
}
#runBtn { background: #2563eb; }
#runBtn:disabled { background: #555; }
#loginBtn { background: #16a34a; }
#loginBtn:disabled { background: #555; }
#naverBtn { background: #03c75a; }
#naverBtn:disabled { background: #555; }
#postBtn { background: #dc2626; }
#postBtn:disabled { background: #555; }
#postAllBtn { background: #9333ea; }
#postAllBtn:disabled { background: #555; }
#clearBtn { background: #444; }
#agentBtn { background: #f59e0b; }
#agentBtn:disabled { background: #555; }
#agentAllBtn { background: #9333ea; }
#agentAllBtn:disabled { background: #555; }
#agentPanel {
    background: #181818; border: 1px solid #333;
    border-radius: 8px;
}
#schedBtn { background: #059669; }
#schedBtn:disabled { background: #555; }
#schedStopBtn { background: #dc2626; }
"""


class CliWorker(QThread):
    finished = pyqtSignal(str)

    def __init__(self, keyword):
        super().__init__()
        self.keyword = keyword

    def run(self):
        prompt = f"{self.keyword} 블로그 글 3줄만 써줘"
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        try:
            result = subprocess.run(
                ["claude", "-p", prompt, "--print"],
                capture_output=True, text=True, timeout=60, env=env,
            )
            output = result.stdout.strip() if result.stdout else result.stderr.strip()
            self.finished.emit(f"[응답]\n{output}")
        except subprocess.TimeoutExpired:
            self.finished.emit("[오류] 60초 타임아웃 초과")
        except FileNotFoundError:
            self.finished.emit("[오류] claude CLI를 찾을 수 없습니다. PATH를 확인하세요.")
        except Exception as e:
            self.finished.emit(f"[오류] {e}")


class PlaywrightWorker(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, keyword, blog_id=None):
        super().__init__()
        self.keyword = keyword
        self.blog_id = blog_id

    def run(self):
        try:
            result = generate_text(
                prompt=f"{self.keyword} 블로그 글 써줘",
                blog_id=self.blog_id,
                keyword=self.keyword,
                on_log=self._emit_log,
            )
            self.finished.emit(f"[Playwright 결과]\n{result}")
        except Exception as e:
            self.finished.emit(f"[Playwright 오류] {e}")

    def _emit_log(self, msg):
        self.log_signal.emit(msg)


class LoginWorker(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, blog_id):
        super().__init__()
        self.blog_id = blog_id

    def run(self):
        try:
            ok = login_blog(self.blog_id, on_log=self._emit_log)
            status = "성공" if ok else "수동 확인 필요"
            self.finished.emit(f"[로그인 {status}]")
        except Exception as e:
            self.finished.emit(f"[로그인 오류] {e}")

    def _emit_log(self, msg):
        self.log_signal.emit(msg)


class PostSingleWorker(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, blog_id, keyword):
        super().__init__()
        self.blog_id = blog_id
        self.keyword = keyword

    def run(self):
        try:
            # 테스트용 콘텐츠
            title = f"{self.keyword} — 블로그 자동 포스팅 테스트"
            content = (
                f"{self.keyword}에 대한 자동 생성 테스트 글입니다.\n"
                f"이 글은 blog-automation-v2로 자동 작성되었습니다.\n"
                f"테스트가 완료되면 삭제해 주세요."
            )
            tags = [self.keyword, "자동포스팅", "테스트"]
            ok = post_single(self.blog_id, title, content, tags,
                             on_log=self._emit_log)
            status = "성공" if ok else "실패"
            self.finished.emit(f"[포스팅 {status}]")
        except Exception as e:
            self.finished.emit(f"[포스팅 오류] {e}")

    def _emit_log(self, msg):
        self.log_signal.emit(msg)


class PostAllWorker(QThread):
    log_signal = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, keyword):
        super().__init__()
        self.keyword = keyword

    def run(self):
        try:
            # 모든 계정용 테스트 콘텐츠 생성
            contents = {}
            for a in ACCOUNTS:
                blog_id = a["blog"]
                contents[blog_id] = {
                    "title": f"{self.keyword} — {blog_id} 자동 포스팅",
                    "content": (
                        f"{self.keyword}에 대한 자동 생성 글입니다.\n"
                        f"블로그: {blog_id} ({a['platform']})\n"
                        f"테스트 완료 후 삭제해 주세요."
                    ),
                }
            tags_map = {a["blog"]: [self.keyword, "자동포스팅"] for a in ACCOUNTS}
            results = post_all(self.keyword, contents, tags_map,
                               on_log=self._emit_log)
            self.finished.emit("[순환 포스팅 완료]")
        except Exception as e:
            self.finished.emit(f"[순환 포스팅 오류] {e}")

    def _emit_log(self, msg):
        self.log_signal.emit(msg)


class BlogAutomationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Blog Automation v2")
        self.resize(1350, 980)
        self.worker = None
        self.char_widgets = {}
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        # --- 상단: 블로그 선택 + 키워드 ---
        top = QHBoxLayout()
        top.addWidget(QLabel("블로그 선택"))
        self.blog_combo = QComboBox()
        self.blog_combo.addItems([a["blog"] for a in ACCOUNTS])
        self.blog_combo.setFixedWidth(160)
        top.addWidget(self.blog_combo)

        top.addWidget(QLabel("키워드"))
        self.keyword_input = QLineEdit("도쿄 여행")
        top.addWidget(self.keyword_input)
        layout.addLayout(top)

        # --- 에이전트 캐릭터 패널 ---
        agent_panel = QFrame()
        agent_panel.setObjectName("agentPanel")
        agent_layout = QHBoxLayout(agent_panel)
        agent_layout.setContentsMargins(16, 14, 16, 14)
        agent_layout.setSpacing(6)
        agent_layout.addStretch()
        for agent_id in ["keyword", "writer", "review", "final_review", "poster"]:
            cw = PixelCharacterWidget(agent_id)
            self.char_widgets[agent_id] = cw
            agent_layout.addWidget(cw)
            # 에이전트 사이 화살표
            if agent_id != "poster":
                arrow = QLabel("▶")
                arrow.setStyleSheet(
                    "color: #4a4a66; font-size: 22px; font-weight: bold;")
                arrow.setAlignment(Qt.AlignCenter)
                arrow.setFixedWidth(32)
                agent_layout.addWidget(arrow)
        agent_layout.addStretch()
        layout.addWidget(agent_panel)

        # --- 로그인 + 포스팅 + 에이전트 버튼 행 ---
        action_row = QHBoxLayout()

        self.login_btn = QPushButton("로그인")
        self.login_btn.setObjectName("loginBtn")
        self.login_btn.clicked.connect(self._run_login)
        action_row.addWidget(self.login_btn)

        self.agent_btn = QPushButton("에이전트 실행")
        self.agent_btn.setObjectName("agentBtn")
        self.agent_btn.clicked.connect(self._run_agent_single)
        action_row.addWidget(self.agent_btn)

        self.agent_all_btn = QPushButton("전체 에이전트")
        self.agent_all_btn.setObjectName("agentAllBtn")
        self.agent_all_btn.clicked.connect(self._run_agent_all)
        action_row.addWidget(self.agent_all_btn)

        self.post_btn = QPushButton("단일 포스팅")
        self.post_btn.setObjectName("postBtn")
        self.post_btn.clicked.connect(self._run_post_single)
        action_row.addWidget(self.post_btn)

        self.post_all_btn = QPushButton("전체 순환 포스팅")
        self.post_all_btn.setObjectName("postAllBtn")
        self.post_all_btn.clicked.connect(self._run_post_all)
        action_row.addWidget(self.post_all_btn)

        self.sched_btn = QPushButton("스케줄러 시작")
        self.sched_btn.setObjectName("schedBtn")
        self.sched_btn.clicked.connect(self._run_scheduler)
        action_row.addWidget(self.sched_btn)

        self.sched_stop_btn = QPushButton("중지")
        self.sched_stop_btn.setObjectName("schedStopBtn")
        self.sched_stop_btn.clicked.connect(self._stop_scheduler)
        self.sched_stop_btn.setEnabled(False)
        self.sched_stop_btn.setFixedWidth(60)
        action_row.addWidget(self.sched_stop_btn)

        action_row.addStretch()
        layout.addLayout(action_row)

        # --- 중앙: 로그 ---
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("Menlo", 12))
        layout.addWidget(self.log_box)

        # --- 하단: 버튼 ---
        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("Claude CLI 테스트")
        self.run_btn.setObjectName("runBtn")
        self.run_btn.clicked.connect(self._run_test)
        btn_row.addWidget(self.run_btn)

        self.pw_btn = QPushButton("Playwright 글 생성")
        self.pw_btn.setObjectName("runBtn")
        self.pw_btn.clicked.connect(self._run_playwright)
        btn_row.addWidget(self.pw_btn)

        btn_row.addStretch()

        clear_btn = QPushButton("로그 지우기")
        clear_btn.setObjectName("clearBtn")
        clear_btn.clicked.connect(self.log_box.clear)
        btn_row.addWidget(clear_btn)
        layout.addLayout(btn_row)

    def _run_test(self):
        self.run_btn.setEnabled(False)
        self.run_btn.setText("실행 중...")
        self.log_box.append(">>> Claude CLI 호출 시작...")

        keyword = self.keyword_input.text().strip() or "도쿄 여행"
        self.worker = CliWorker(keyword)
        self.worker.finished.connect(self._on_result)
        self.worker.start()

    def _on_result(self, text):
        self.log_box.append(text)
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Claude CLI 테스트")

    # --- Playwright 글 생성 ---
    def _run_playwright(self):
        self.pw_btn.setEnabled(False)
        self.pw_btn.setText("생성 중...")
        self.log_box.append(">>> Playwright claude.ai 글 생성 시작...")

        keyword = self.keyword_input.text().strip() or "도쿄 여행"
        blog_id = self.blog_combo.currentText()
        self.pw_worker = PlaywrightWorker(keyword, blog_id=blog_id)
        self.pw_worker.log_signal.connect(self.log_box.append)
        self.pw_worker.finished.connect(self._on_pw_result)
        self.pw_worker.start()

    def _on_pw_result(self, text):
        self.log_box.append(text)
        self.pw_btn.setEnabled(True)
        self.pw_btn.setText("Playwright 글 생성")

    # --- 로그인 (선택된 블로그) ---
    def _run_login(self):
        self.login_btn.setEnabled(False)
        self.login_btn.setText("로그인 중...")
        blog_id = self.blog_combo.currentText()
        self.login_worker = LoginWorker(blog_id)
        self.login_worker.log_signal.connect(self.log_box.append)
        self.login_worker.finished.connect(self._on_login_done)
        self.login_worker.start()

    def _on_login_done(self, text):
        self.log_box.append(text)
        self.login_btn.setEnabled(True)
        self.login_btn.setText("로그인")

    # --- 단일 포스팅 (선택된 블로그) ---
    def _run_post_single(self):
        self.post_btn.setEnabled(False)
        self.post_btn.setText("포스팅 중...")
        blog_id = self.blog_combo.currentText()
        keyword = self.keyword_input.text().strip() or "도쿄 여행"
        self.post_worker = PostSingleWorker(blog_id, keyword)
        self.post_worker.log_signal.connect(self.log_box.append)
        self.post_worker.finished.connect(self._on_post_done)
        self.post_worker.start()

    def _on_post_done(self, text):
        self.log_box.append(text)
        self.post_btn.setEnabled(True)
        self.post_btn.setText("단일 포스팅")

    # --- 전체 순환 포스팅 ---
    def _run_post_all(self):
        self.post_all_btn.setEnabled(False)
        self.post_all_btn.setText("순환 중...")
        keyword = self.keyword_input.text().strip() or "도쿄 여행"
        self.post_all_worker = PostAllWorker(keyword)
        self.post_all_worker.log_signal.connect(self.log_box.append)
        self.post_all_worker.finished.connect(self._on_post_all_done)
        self.post_all_worker.start()

    def _on_post_all_done(self, text):
        self.log_box.append(text)
        self.post_all_btn.setEnabled(True)
        self.post_all_btn.setText("전체 순환 포스팅")

    # --- 에이전트 실행 (단일 블로그) ---
    def _run_agent_single(self):
        self.agent_btn.setEnabled(False)
        self.agent_btn.setText("실행 중...")
        self._reset_characters()
        blog_id = self.blog_combo.currentText()
        keyword = self.keyword_input.text().strip() or None
        self.agent_worker = SingleAgentWorker(blog_id, keyword)
        self.agent_worker.log_signal.connect(self.log_box.append)
        self.agent_worker.status_signal.connect(self._update_character)
        self.agent_worker.finished.connect(self._on_agent_done)
        self.agent_worker.start()

    # --- 에이전트 실행 (전체 블로그) ---
    def _run_agent_all(self):
        self.agent_all_btn.setEnabled(False)
        self.agent_all_btn.setText("실행 중...")
        self._reset_characters()
        self.agent_all_worker = OrchestratorWorker()
        self.agent_all_worker.log_signal.connect(self.log_box.append)
        self.agent_all_worker.status_signal.connect(self._update_character)
        self.agent_all_worker.finished.connect(self._on_agent_all_done)
        self.agent_all_worker.start()

    def _on_agent_done(self, text):
        self.log_box.append(text)
        self.agent_btn.setEnabled(True)
        self.agent_btn.setText("에이전트 실행")

    def _on_agent_all_done(self, text):
        self.log_box.append(text)
        self.agent_all_btn.setEnabled(True)
        self.agent_all_btn.setText("전체 에이전트")

    def _update_character(self, agent_name, state):
        """on_status 콜백 → 픽셀 캐릭터 상태 업데이트"""
        cw = self.char_widgets.get(agent_name)
        if cw:
            cw.set_state(state)

    def _reset_characters(self):
        for cw in self.char_widgets.values():
            cw.set_state("idle")

    # --- 스케줄러 ---
    def _run_scheduler(self):
        self.sched_btn.setEnabled(False)
        self.sched_btn.setText("실행 중...")
        self.sched_stop_btn.setEnabled(True)
        self._reset_characters()
        self.sched_worker = SchedulerWorker()
        self.sched_worker.log_signal.connect(self.log_box.append)
        self.sched_worker.status_signal.connect(self._update_character)
        self.sched_worker.finished.connect(self._on_scheduler_done)
        self.sched_worker.start()

    def _stop_scheduler(self):
        if hasattr(self, 'sched_worker') and self.sched_worker.isRunning():
            self.sched_worker.stop()
            self.log_box.append("[스케줄러] 중지 요청...")

    def _on_scheduler_done(self, text):
        self.log_box.append(text)
        self.sched_btn.setEnabled(True)
        self.sched_btn.setText("스케줄러 시작")
        self.sched_stop_btn.setEnabled(False)
        self._reset_characters()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLE)
    window = BlogAutomationApp()
    window.show()
    sys.exit(app.exec_())
