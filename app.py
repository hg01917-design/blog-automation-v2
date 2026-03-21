import sys
import os
import subprocess
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QLineEdit, QTextEdit, QPushButton, QFrame,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QRect, QPoint
from PyQt5.QtGui import QFont, QPainter, QColor, QPen, QBrush

# 같은 디렉토리의 모듈 import를 위해 경로 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import ACCOUNTS, ACCOUNT_MAP
from claude_playwright import generate_text
from login_playwright import login_blog, login_naver
from poster import post_single, post_all


# ─── 픽셀 캐릭터 위젯 ───

AGENT_COLORS = {
    "keyword":      {"shirt": "#3b82f6", "pants": "#1e40af", "name": "키워드"},
    "writer":       {"shirt": "#22c55e", "pants": "#15803d", "name": "작성"},
    "review":       {"shirt": "#eab308", "pants": "#a16207", "name": "검수"},
    "final_review": {"shirt": "#a855f7", "pants": "#7e22ce", "name": "최종"},
    "poster":       {"shirt": "#ef4444", "pants": "#b91c1c", "name": "포스팅"},
}


class PixelCharacterWidget(QWidget):
    """80x80 QPainter 기반 픽셀 캐릭터 — 에이전트 상태 표시"""

    def __init__(self, agent_id, parent=None):
        super().__init__(parent)
        self.agent_id = agent_id
        info = AGENT_COLORS.get(agent_id, {"shirt": "#888", "pants": "#555", "name": agent_id})
        self.shirt_color = QColor(info["shirt"])
        self.pants_color = QColor(info["pants"])
        self.agent_name = info["name"]
        self.state = "idle"       # idle, working, done, failed
        self.frame = 0
        self.task_text = "대기"

        self.setFixedSize(90, 120)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(400)

    def set_state(self, state):
        self.state = state
        labels = {"idle": "대기", "working": "작업 중...",
                  "done": "완료!", "failed": "실패"}
        self.task_text = labels.get(state, state)
        self.frame = 0
        self.update()

    def _tick(self):
        self.frame += 1
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        # 캐릭터를 중앙에 그리기 (80x80 영역, 아래 텍스트 공간 남김)
        ox, oy = 5, 0  # offset
        s = 4  # pixel scale (20x20 grid → 80x80)

        skin = QColor("#fcd5b0")
        hair = QColor("#4a3728")
        eye = QColor("#222")
        desk = QColor("#8B7355")
        monitor = QColor("#333")
        screen = QColor("#1a1a2e")

        f = self.frame % 4  # 4-frame animation cycle

        # ── 모니터 (고정) ──
        p.fillRect(QRect(ox + 6*s, oy + 2*s, 8*s, 6*s), QBrush(monitor))
        p.fillRect(QRect(ox + 7*s, oy + 3*s, 6*s, 4*s), QBrush(screen))
        # 모니터 받침
        p.fillRect(QRect(ox + 9*s, oy + 8*s, 2*s, s), QBrush(monitor))

        # 화면 내용 (상태별)
        if self.state == "working":
            # 깜빡이는 텍스트 줄
            line_c = QColor("#4ade80")
            for row in range(3):
                w = (3 + ((f + row) % 3)) * s
                if not (f % 2 == 0 and row == 2):
                    p.fillRect(QRect(ox + 8*s, oy + (3 + row)*s + 2, w, 2), QBrush(line_c))
        elif self.state == "done":
            p.setPen(QPen(QColor("#4ade80")))
            p.setFont(QFont("Arial", 7, QFont.Bold))
            p.drawText(QRect(ox + 7*s, oy + 3*s, 6*s, 4*s), Qt.AlignCenter, "OK")
        elif self.state == "failed":
            p.setPen(QPen(QColor("#ef4444")))
            p.setFont(QFont("Arial", 7, QFont.Bold))
            p.drawText(QRect(ox + 7*s, oy + 3*s, 6*s, 4*s), Qt.AlignCenter, "ERR")
        else:
            # idle — 빈 화면 또는 스크린세이버
            if f % 4 < 2:
                p.fillRect(QRect(ox + 8*s + f*s, oy + 5*s, s, s), QBrush(QColor("#334155")))

        # ── 책상 ──
        p.fillRect(QRect(ox + 2*s, oy + 9*s, 16*s, s), QBrush(desk))

        # ── 머리 ──
        head_bob = 0
        if self.state == "idle":
            head_bob = s // 2 if f % 4 < 2 else 0  # 꾸벅꾸벅
        elif self.state == "done":
            head_bob = -(s // 2) if f % 2 == 0 else 0  # 들썩

        # 머리카락
        p.fillRect(QRect(ox + 2*s, oy + 6*s + head_bob, 4*s, s), QBrush(hair))
        # 얼굴
        p.fillRect(QRect(ox + 2*s, oy + 7*s + head_bob, 4*s, 3*s), QBrush(skin))
        # 눈
        if self.state == "idle" and f % 4 >= 2:
            # 졸고 있음 — 눈 감음
            p.fillRect(QRect(ox + 3*s, oy + 8*s + head_bob, s, 1), QBrush(eye))
            p.fillRect(QRect(ox + 5*s, oy + 8*s + head_bob, s, 1), QBrush(eye))
        else:
            p.fillRect(QRect(ox + 3*s, oy + 8*s + head_bob, s, s), QBrush(eye))
            p.fillRect(QRect(ox + 5*s, oy + 8*s + head_bob, s, s), QBrush(eye))

        # 실패 시 땀방울
        if self.state == "failed" and f % 2 == 0:
            p.fillRect(QRect(ox + 7*s, oy + 7*s + head_bob, s//2, s), QBrush(QColor("#60a5fa")))

        # ── 몸통 (셔츠) ──
        p.fillRect(QRect(ox + 1*s, oy + 10*s, 6*s, 4*s), QBrush(self.shirt_color))

        # ── 팔 ──
        if self.state == "working":
            # 타이핑 — 팔 움직임
            arm_dx = s if f % 2 == 0 else 0
            p.fillRect(QRect(ox + 7*s + arm_dx, oy + 11*s, 2*s, s), QBrush(skin))
            p.fillRect(QRect(ox + 7*s - arm_dx + s, oy + 12*s, 2*s, s), QBrush(skin))
        elif self.state == "done":
            # 만세!
            if f % 2 == 0:
                p.fillRect(QRect(ox + 0*s, oy + 8*s, s, 2*s), QBrush(skin))
                p.fillRect(QRect(ox + 7*s, oy + 8*s, s, 2*s), QBrush(skin))
            else:
                p.fillRect(QRect(ox + 0*s, oy + 9*s, s, 2*s), QBrush(skin))
                p.fillRect(QRect(ox + 7*s, oy + 9*s, s, 2*s), QBrush(skin))
        elif self.state == "failed":
            # 머리 긁적
            scratch_y = oy + 7*s if f % 2 == 0 else oy + 6*s + head_bob
            p.fillRect(QRect(ox + 6*s, scratch_y, s, 2*s), QBrush(skin))
            # 다른 팔은 내림
            p.fillRect(QRect(ox + 0*s, oy + 12*s, s, 2*s), QBrush(skin))
        else:
            # idle — 책상 위에 팔
            p.fillRect(QRect(ox + 7*s, oy + 11*s, 2*s, s), QBrush(skin))

        # ── 바지 ──
        p.fillRect(QRect(ox + 1*s, oy + 14*s, 3*s, 2*s), QBrush(self.pants_color))
        p.fillRect(QRect(ox + 4*s, oy + 14*s, 3*s, 2*s), QBrush(self.pants_color))

        # ── 의자 ──
        chair = QColor("#555")
        p.fillRect(QRect(ox + 0*s, oy + 16*s, 8*s, s), QBrush(chair))
        p.fillRect(QRect(ox + 1*s, oy + 17*s, s, 2*s), QBrush(chair))
        p.fillRect(QRect(ox + 6*s, oy + 17*s, s, 2*s), QBrush(chair))

        # ── 이름 + 상태 텍스트 ──
        p.setPen(QPen(QColor("#e0e0e0")))
        p.setFont(QFont("Arial", 9, QFont.Bold))
        text_rect = QRect(0, 82, 90, 16)
        p.drawText(text_rect, Qt.AlignCenter, self.agent_name)

        p.setFont(QFont("Arial", 8))
        state_colors = {
            "idle": "#888", "working": "#4ade80",
            "done": "#22c55e", "failed": "#ef4444",
        }
        p.setPen(QPen(QColor(state_colors.get(self.state, "#888"))))
        p.drawText(QRect(0, 98, 90, 16), Qt.AlignCenter, self.task_text)

        p.end()


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
        self.resize(800, 750)
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
        agent_layout.setContentsMargins(10, 10, 10, 10)
        agent_layout.setSpacing(6)
        agent_layout.addStretch()
        for agent_id in ["keyword", "writer", "review", "final_review", "poster"]:
            cw = PixelCharacterWidget(agent_id)
            self.char_widgets[agent_id] = cw
            agent_layout.addWidget(cw)
            # 에이전트 사이 화살표
            if agent_id != "poster":
                arrow = QLabel(">")
                arrow.setStyleSheet("color: #555; font-size: 18px; font-weight: bold;")
                arrow.setAlignment(Qt.AlignCenter)
                arrow.setFixedWidth(16)
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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLE)
    window = BlogAutomationApp()
    window.show()
    sys.exit(app.exec_())
