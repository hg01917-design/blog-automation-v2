import sys
import os
from pathlib import Path as _Path

# ── GUI 앱에서 stdout/stderr Broken pipe 방지 ──────────────────────────────
if getattr(sys, "frozen", False):
    import io, os
    _devnull = open(os.devnull, "w")
    try:
        os.dup2(_devnull.fileno(), 1)  # fd 1 = stdout → /dev/null
        os.dup2(_devnull.fileno(), 2)  # fd 2 = stderr → /dev/null
    except Exception:
        pass
    sys.stdout = _devnull
    sys.stderr = _devnull

# ── 프로젝트 루트 경로 설정 (.app 번들 / 일반 실행 모두 대응) ──────────────
# 사용자 데이터(DB, .env)는 앱 위치와 무관하게 고정 경로에 저장
_USER_DATA_DIR = _Path.home() / "Library" / "Application Support" / "BlogAutomation"
_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

if getattr(sys, "frozen", False):
    # .app/Contents/MacOS/실행파일 → 5단계 위가 프로젝트 루트
    _PROJECT_ROOT = _Path(sys.executable).parent.parent.parent.parent.parent
else:
    _PROJECT_ROOT = _Path(__file__).parent

os.environ["BLOG_AUTO_PROJECT_ROOT"] = str(_PROJECT_ROOT)

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QFrame, QSizePolicy,
    QDialog, QLineEdit, QFormLayout, QDialogButtonBox, QMessageBox,
    QCheckBox, QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSplitter,
    QComboBox, QTabWidget, QStackedWidget, QListWidget, QListWidgetItem,
    QInputDialog,
)
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QPoint, QSize,
)
from PyQt5.QtGui import QFont, QPainter, QColor, QPen, QBrush, QMovie, QFontMetrics
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import ACCOUNTS, ACCOUNT_MAP

try:
    _base = Path(sys._MEIPASS)
except AttributeError:
    _base = Path(__file__).parent
ASSETS_DIR = _base / "assets"

BLOG_CATEGORIES = {
    "goodisak":        "IT",
    "nolja100":        "여행",
    "salim1su":        "살림",
    "baremi542":       "정부지원금",
    "woll100":         "교통",
    "phn0502":         "영화",
    "triplog":         "여행",
    "me1091":          "리뷰",
    "blogspot_travel": "여행",
    "blogspot_it":     "IT",
    "blogspot_daily":  "일상",
}

# 플랫폼 뱃지 정보: blog_id → (플랫폼명, bg, text, border)
_PLATFORM_INFO = {
    "baremi542":       ("WordPress", "#0073aa22", "#4f8ef7", "#0073aa44"),
    "triplog":         ("WordPress", "#0073aa22", "#4f8ef7", "#0073aa44"),
    "goodisak":        ("Tistory",   "#ff590022", "#ff8c60", "#ff590044"),
    "nolja100":        ("Tistory",   "#ff590022", "#ff8c60", "#ff590044"),
    "woll100":         ("Tistory",   "#ff590022", "#ff8c60", "#ff590044"),
    "phn0502":         ("Tistory",   "#ff590022", "#ff8c60", "#ff590044"),
    "salim1su":        ("Naver",     "#03c75a22", "#22c55e", "#03c75a44"),
    "me1091":          ("Naver",     "#03c75a22", "#22c55e", "#03c75a44"),
    "blogspot_travel": ("Blogspot",  "#ea433522", "#ea4335", "#ea433544"),
    "blogspot_it":     ("Blogspot",  "#ea433522", "#ea4335", "#ea433544"),
    "blogspot_daily":  ("Blogspot",  "#ea433522", "#ea4335", "#ea433544"),
}


# ─── 단일 블로그 즉시 실행 워커 ──────────────────────────────────────────

class SingleRunWorker(QThread):
    """단일 블로그 즉시 실행 워커"""
    log_signal    = pyqtSignal(str)
    status_signal = pyqtSignal(str, str)
    blog_signal   = pyqtSignal(str)
    finished      = pyqtSignal(str)

    def __init__(self, blog_id: str, keyword: str = None, forced_title: str = None):
        super().__init__()
        self.blog_id = blog_id
        self.keyword = keyword
        self.forced_title = forced_title

    def run(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agents"))
        from agents import orchestrator
        self.blog_signal.emit(self.blog_id)
        try:
            result = orchestrator.run_single(
                self.blog_id,
                keyword=self.keyword or None,
                on_log=self._log,
                on_status=self._status,
                forced_title=self.forced_title or None,
            )
            if result["success"]:
                self.finished.emit(f"[완료] {self.blog_id}: {result['title']}")
            else:
                self.finished.emit(f"[실패] {self.blog_id}: {result['reason']}")
        except Exception as e:
            self.finished.emit(f"[오류] {self.blog_id}: {e}")
        finally:
            self.blog_signal.emit("")

    def _log(self, msg):
        self.log_signal.emit(msg)

    def _status(self, agent, state):
        self.status_signal.emit(agent, state)


# ─── 스케줄러 워커 ────────────────────────────────────────────────────────

class SchedulerWorker(QThread):
    log_signal    = pyqtSignal(str)
    status_signal = pyqtSignal(str, str)
    blog_signal   = pyqtSignal(str)
    finished      = pyqtSignal(str)

    def __init__(self, enabled_blogs: list[str]):
        super().__init__()
        self._stop_flag    = False
        self.enabled_blogs = enabled_blogs
        self._proc         = None

    def stop(self):
        self._stop_flag = True
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def run(self):
        import subprocess
        from pathlib import Path

        # overnight_run.py 경로 찾기
        if getattr(sys, "frozen", False):
            base = Path(sys._MEIPASS)
        else:
            base = Path(__file__).parent

        script = base / "overnight_run.py"
        self._log(f"[스케줄러] overnight_run.py 시작: {script}")

        # frozen 앱에서는 프로젝트 소스 디렉토리에서 실행 (MEIPASS 아님)
        project_dir = Path(__file__).parent
        if getattr(sys, "frozen", False):
            # sys.executable = .app/Contents/MacOS/Blog Automation v2
            # parents[4] = blog-automation-v2/ (프로젝트 루트)
            exe_path = Path(sys.executable).resolve()
            for i in range(2, 8):
                candidate = exe_path.parents[i]
                src_script = candidate / "overnight_run.py"
                if src_script.exists():
                    script = src_script
                    project_dir = candidate
                    break
            else:
                # 못 찾으면 MEIPASS 사용
                project_dir = base

        self._log(f"[스케줄러] script={script}")
        self._log(f"[스케줄러] cwd={project_dir}")

        try:
            self._proc = subprocess.Popen(
                [sys.executable if not getattr(sys, "frozen", False) else "python3",
                 str(script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(project_dir),
            )
            for line in self._proc.stdout:
                if self._stop_flag:
                    break
                line = line.rstrip()
                if line:
                    self._log(line)
            self._proc.wait()
        except Exception as e:
            self._log(f"[스케줄러] 오류: {e}")
        finally:
            self._proc = None

        self.finished.emit("[스케줄러] 종료됨")

    def _log(self, msg):
        self.log_signal.emit(msg)

    def _status(self, agent, state):
        self.status_signal.emit(agent, state)


# ─── 메인 앱 ─────────────────────────────────────────────────────────────

DARK_STYLE = """
QMainWindow { background: #13151f; }
QWidget     { background: #13151f; color: #e0e0e0; }
QLabel      { color: #e0e0e0; font-size: 12px; }
QScrollArea { background: transparent; border: none; }
QTextEdit {
    background: #0d0f18; color: #c9d1d9;
    border: 1px solid #1e2233; border-radius: 6px;
    padding: 6px; font-size: 11px;
}
QPushButton {
    padding: 4px 12px; border: none; border-radius: 5px;
    font-size: 12px; color: #fff;
}
QComboBox {
    background: #1a1d2e; color: #e0e0e0;
    border: 1px solid #1e2233; border-radius: 5px;
    padding: 4px 8px; font-size: 12px;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background: #1a1d2e; color: #e0e0e0;
    selection-background-color: #4f8ef7;
}
QListWidget {
    background: #0d0f18; color: #c9d1d9;
    border: none; font-size: 11px;
}
QScrollBar:vertical {
    background: #1a1d2e; width: 6px; border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #4a5568; border-radius: 3px;
}
"""


class SettingsDialog(QDialog):
    """API 키 / 환경변수 설정 다이얼로그 — 저장 시 .env 파일에 반영"""

    _ENV_PATH = _Path(os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(_Path(__file__).parent.parent))) / ".env"

    # 표시할 키 목록: (env_key, 레이블, placeholder, 비밀번호여부)
    _FIELDS = [
        ("WP_USER",                  "WordPress 사용자명",           "admin",                        False),
        ("WP_APP_PASSWORD",          "WordPress 애플리케이션 비밀번호",  "xxxx xxxx xxxx xxxx xxxx xxxx", True),
        ("NOTION_TOKEN",             "Notion API 토큰",              "secret_...",                   True),
        ("GEMINI_API_KEY",           "Gemini API 키",                "AIza...",                      True),
        ("NAVER_SEARCH_CLIENT_ID",   "Naver 검색 Client ID",         "25wb2T...",                    False),
        ("NAVER_SEARCH_CLIENT_SECRET","Naver 검색 Client Secret",    "_bSa7...",                     True),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙ 설정 — API 키 관리")
        self.setMinimumWidth(520)
        self._inputs: dict[str, QLineEdit] = {}

        env_vals = self._load_env()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 안내 문구
        hint = QLabel("저장 버튼을 누르면 .env 파일에 즉시 반영됩니다.")
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(8)
        for key, label, placeholder, is_pw in self._FIELDS:
            edit = QLineEdit()
            edit.setPlaceholderText(placeholder)
            edit.setText(env_vals.get(key, ""))
            edit.setMinimumHeight(30)
            if is_pw:
                edit.setEchoMode(QLineEdit.Password)
            self._inputs[key] = edit
            form.addRow(f"{label}:", edit)
        layout.addLayout(form)

        # 비밀번호 표시 토글
        toggle_btn = QPushButton("🔑  비밀번호 표시 / 숨기기")
        toggle_btn.setFixedHeight(28)
        toggle_btn.clicked.connect(self._toggle_pw_visibility)
        layout.addWidget(toggle_btn)

        # 버튼 박스
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Save).setText("저장")
        btn_box.button(QDialogButtonBox.Cancel).setText("취소")
        btn_box.accepted.connect(self._save)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _toggle_pw_visibility(self):
        for key, _, _, is_pw in self._FIELDS:
            if is_pw:
                edit = self._inputs[key]
                edit.setEchoMode(
                    QLineEdit.Normal if edit.echoMode() == QLineEdit.Password
                    else QLineEdit.Password
                )

    def _load_env(self) -> dict:
        """현재 .env 파일에서 key=value 파싱"""
        vals = {}
        if self._ENV_PATH.exists():
            for line in self._ENV_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    vals[k.strip()] = v.strip()
        return vals

    def _save(self):
        """입력값을 .env 파일에 반영 (기존 다른 키는 유지)"""
        # 현재 .env 전체 줄 읽기
        if self._ENV_PATH.exists():
            lines = self._ENV_PATH.read_text(encoding="utf-8").splitlines()
        else:
            lines = []

        new_vals = {key: self._inputs[key].text().strip() for key in self._inputs}

        # 기존 줄 중 해당 키 업데이트
        updated_keys = set()
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _, _ = stripped.partition("=")
                k = k.strip()
                if k in new_vals:
                    new_lines.append(f"{k}={new_vals[k]}")
                    updated_keys.add(k)
                    continue
            new_lines.append(line)

        # 없던 키는 파일 끝에 추가
        for key, val in new_vals.items():
            if key not in updated_keys:
                new_lines.append(f"{key}={val}")

        self._ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

        # os.environ 즉시 반영
        for key, val in new_vals.items():
            if val:
                os.environ[key] = val

        QMessageBox.information(self, "저장 완료", ".env 파일에 저장되었습니다.\n앱 재시작 없이 즉시 적용됩니다.")
        self.accept()


# ─── 블로그 추가 다이얼로그 ────────────────────────────────────────────────

class AddBlogDialog(QDialog):
    """새 블로그 등록 다이얼로그 — config_custom.json + 에이전트 파일 자동 생성"""

    _BASE_DIR = _Path(os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(_Path(__file__).parent)))
    _CUSTOM_JSON = _BASE_DIR / "config_custom.json"
    _AGENTS_DIR  = _BASE_DIR / "agents"

    _PLATFORMS = ["tistory", "naver", "wordpress", "blogspot"]
    _CATEGORIES = ["여행", "IT", "살림", "정부지원금", "교통정보", "영화", "리뷰", "일상", "기타"]
    _PLATFORM_COLORS = {
        "tistory":  ("#ff590022", "#ff8c60", "#ff590044", "Tistory"),
        "naver":    ("#03c75a22", "#22c55e", "#03c75a44", "Naver"),
        "wordpress":("#0073aa22", "#4f8ef7", "#0073aa44", "WordPress"),
        "blogspot": ("#ea433522", "#ea4335", "#ea433544", "Blogspot"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("➕ 블로그 추가")
        self.setMinimumWidth(440)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        # 블로그 ID
        self._id_edit = QLineEdit()
        self._id_edit.setPlaceholderText("예: mytravel (영문+숫자)")
        self._id_edit.setMinimumHeight(30)
        form.addRow("블로그 ID:", self._id_edit)

        # 플랫폼
        self._platform_combo = QComboBox()
        self._platform_combo.addItems(self._PLATFORMS)
        self._platform_combo.currentTextChanged.connect(self._on_platform_changed)
        form.addRow("플랫폼:", self._platform_combo)

        # 카카오 ID (Tistory)
        self._kakao_edit = QLineEdit()
        self._kakao_edit.setPlaceholderText("카카오 로그인 ID")
        self._kakao_edit.setMinimumHeight(30)
        form.addRow("카카오 ID:", self._kakao_edit)

        # 네이버 ID (Naver)
        self._naver_edit = QLineEdit()
        self._naver_edit.setPlaceholderText("네이버 로그인 ID")
        self._naver_edit.setMinimumHeight(30)
        form.addRow("네이버 ID:", self._naver_edit)

        # 블로그 URL
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("예: https://myblog.tistory.com")
        self._url_edit.setMinimumHeight(30)
        form.addRow("블로그 URL:", self._url_edit)

        # 카테고리
        self._cat_combo = QComboBox()
        self._cat_combo.addItems(self._CATEGORIES)
        form.addRow("카테고리:", self._cat_combo)

        layout.addLayout(form)

        hint = QLabel("※ 입력 후 저장하면 즉시 콤보박스에 추가됩니다.")
        hint.setStyleSheet("color:#888;font-size:11px;")
        layout.addWidget(hint)

        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Save).setText("저장")
        btn_box.button(QDialogButtonBox.Cancel).setText("취소")
        btn_box.accepted.connect(self._save)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self._on_platform_changed("tistory")

    def _on_platform_changed(self, platform: str):
        self._kakao_edit.setVisible(platform == "tistory")
        self._naver_edit.setVisible(platform == "naver")

    def _save(self):
        blog_id  = self._id_edit.text().strip()
        platform = self._platform_combo.currentText()
        url      = self._url_edit.text().strip().rstrip("/")
        category = self._cat_combo.currentText()
        kakao_id = self._kakao_edit.text().strip()
        naver_id = self._naver_edit.text().strip()

        if not blog_id:
            QMessageBox.warning(self, "입력 오류", "블로그 ID를 입력해 주세요.")
            return
        if not url:
            QMessageBox.warning(self, "입력 오류", "블로그 URL을 입력해 주세요.")
            return

        # editor_url 자동 생성
        if platform == "tistory":
            editor_url = f"{url}/manage/newpost"
        elif platform == "naver":
            editor_url = f"https://blog.naver.com/{blog_id}/postwrite"
        elif platform == "wordpress":
            editor_url = f"{url}/wp-admin/post-new.php"
        else:
            editor_url = url

        # config_custom.json 업데이트
        custom = {"accounts": []}
        if self._CUSTOM_JSON.exists():
            import json
            try:
                custom = json.loads(self._CUSTOM_JSON.read_text(encoding="utf-8"))
            except Exception:
                pass

        account = {"blog": blog_id, "platform": platform,
                   "editor_url": editor_url, "category": category}
        if platform == "tistory" and kakao_id:
            account["kakao_id"] = kakao_id
        if platform == "naver" and naver_id:
            account["naver_id"] = naver_id

        # 중복 제거 후 추가
        import json
        custom["accounts"] = [a for a in custom["accounts"] if a.get("blog") != blog_id]
        custom["accounts"].append(account)
        self._CUSTOM_JSON.write_text(json.dumps(custom, ensure_ascii=False, indent=2), encoding="utf-8")

        # 에이전트 파일 자동 생성
        self._create_agent(blog_id, platform, category)

        # orchestrator BLOG_AGENT_MAP 런타임 업데이트
        try:
            from agents import orchestrator as _orc
            _orc.BLOG_AGENT_MAP[blog_id] = f"{blog_id}_agent"
            if blog_id not in _orc.DEFAULT_BLOG_ORDER:
                _orc.DEFAULT_BLOG_ORDER.append(blog_id)
        except Exception:
            pass

        # BLOG_CATEGORIES / _PLATFORM_INFO 런타임 업데이트
        BLOG_CATEGORIES[blog_id] = category
        _bg, _fg, _border, _name = self._PLATFORM_COLORS.get(platform, ("#33333322","#aaa","#33333344","Unknown"))
        _PLATFORM_INFO[blog_id] = (_name, _bg, _fg, _border)

        self._result_blog_id = blog_id
        QMessageBox.information(self, "추가 완료", f"'{blog_id}' 블로그가 추가되었습니다.")
        self.accept()

    def _create_agent(self, blog_id: str, platform: str, category: str):
        """orchestrator의 _generate_agent_template으로 에이전트 파일 자동 생성"""
        agent_path = self._AGENTS_DIR / f"{blog_id}_agent.py"
        if agent_path.exists():
            return
        try:
            from agents import orchestrator as _orc
            module_name = f"{blog_id}_agent"
            _orc._generate_agent_template(blog_id, module_name, category)
        except Exception:
            pass

    @property
    def result_blog_id(self) -> str:
        return getattr(self, "_result_blog_id", "")


# ─── 인라인 설정 패널 (새 콤팩트 GUI용) ──────────────────────────────────

class _SettingsPanel(QWidget):
    """⚙ 버튼 클릭 시 메인 뷰와 교체되는 인라인 설정 패널"""

    saved = pyqtSignal()

    _ENV_PATH = _Path(os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(_Path(__file__).parent))) / ".env"

    _FIELDS = [
        # (env_key, 라벨, placeholder, is_pw)
        ("CLAUDE_API_KEY",      "Claude API Key",          "sk-ant-...",              True),
        ("WP_URL",              "WordPress 사이트 URL",    "https://example.com",     False),
        ("WP_USER",             "WordPress 아이디",         "admin",                   False),
        ("WP_APP_PASSWORD",     "WordPress 앱 비밀번호",    "xxxx xxxx xxxx xxxx",     True),
        ("TISTORY_URL",         "Tistory 블로그 주소",      "https://xxx.tistory.com", False),
        ("TISTORY_ACCESS_TOKEN","Tistory Access Token",    "abc123...",               True),
        ("NAVER_ID",            "Naver 아이디",             "user123",                 False),
        ("NAVER_PW",            "Naver 비밀번호",           "...",                     True),
        ("NOTION_TOKEN",        "Notion Integration Token","secret_...",              True),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._inputs: dict[str, QLineEdit] = {}
        self._build_ui()
        self._load()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        title = QLabel("⚙ 설정")
        title.setStyleSheet("color:#e0e0e0;font-size:14px;font-weight:bold;")
        lay.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background:transparent;border:none;")
        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        form = QFormLayout(inner)
        form.setSpacing(6)
        form.setContentsMargins(0, 0, 4, 0)

        for key, label, ph, is_pw in self._FIELDS:
            lbl = QLabel(f"{label}:")
            lbl.setStyleSheet("color:#9ca3af;font-size:11px;")
            edit = QLineEdit()
            edit.setPlaceholderText(ph)
            edit.setMinimumHeight(26)
            edit.setStyleSheet(
                "background:#1a1d2e;color:#e0e0e0;border:1px solid #1e2233;"
                "border-radius:4px;padding:2px 6px;font-size:11px;"
            )
            if is_pw:
                edit.setEchoMode(QLineEdit.Password)
            self._inputs[key] = edit
            form.addRow(lbl, edit)

        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)

        save_btn = QPushButton("저장")
        save_btn.setStyleSheet(
            "background:#4f8ef7;color:#fff;border:none;border-radius:5px;"
            "font-size:12px;padding:6px 24px;"
        )
        save_btn.clicked.connect(self._save)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(save_btn)
        lay.addLayout(row)

    def _load(self):
        vals = {}
        if self._ENV_PATH.exists():
            for line in self._ENV_PATH.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s and not s.startswith("#") and "=" in s:
                    k, _, v = s.partition("=")
                    vals[k.strip()] = v.strip()
        for key, edit in self._inputs.items():
            edit.setText(vals.get(key, ""))

    def _save(self):
        lines = self._ENV_PATH.read_text(encoding="utf-8").splitlines() \
                if self._ENV_PATH.exists() else []
        new_vals = {k: e.text().strip() for k, e in self._inputs.items()}
        updated, new_lines = set(), []
        for line in lines:
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k = s.partition("=")[0].strip()
                if k in new_vals:
                    new_lines.append(f"{k}={new_vals[k]}")
                    updated.add(k)
                    continue
            new_lines.append(line)
        for k, v in new_vals.items():
            if k not in updated:
                new_lines.append(f"{k}={v}")
        self._ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        for k, v in new_vals.items():
            if v:
                os.environ[k] = v
        QMessageBox.information(self.window(), "저장", ".env에 저장됐습니다.")
        self.saved.emit()


# ─── 키워드 수집 백그라운드 워커 ──────────────────────────────────────────

class KeywordCollectWorker(QThread):
    """7개 카테고리 순차 수집 — 백그라운드 실행"""
    log_signal      = pyqtSignal(str)
    keyword_signal  = pyqtSignal(str, str, float, int, int)  # category, keyword, score, volume, pub_count
    category_signal = pyqtSignal(str)   # 현재 수집 중인 카테고리 ("" = 완료)
    finished        = pyqtSignal(str)

    ALL_CATEGORIES = ["IT", "금융", "여행", "살림", "정부지원금", "교통", "영화"]

    def __init__(self, use_playwright: bool = False):
        super().__init__()
        self.use_playwright = use_playwright
        self._stop_flag     = False

    def stop(self):
        self._stop_flag = True

    def run(self):
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from keyword_engine.category_engine import run_category

            total = 0
            for category in self.ALL_CATEGORIES:
                if self._stop_flag:
                    break
                self.category_signal.emit(category)
                self.log_signal.emit(f"\n{'═'*40}")
                self.log_signal.emit(f"  [{category}] 수집 시작")
                self.log_signal.emit(f"{'═'*40}")

                def on_log(msg, _cat=category):
                    if not self._stop_flag:
                        self.log_signal.emit(msg)

                def on_keyword(item, _cat=category):
                    if not self._stop_flag:
                        self.keyword_signal.emit(
                            _cat, item["keyword"], item["score"],
                            item["volume"], item["pub_count"],
                        )

                results = run_category(
                    category=category,
                    top_n=50,
                    min_score=50_000,
                    min_volume=500,
                    use_playwright=self.use_playwright,
                    on_log=on_log,
                    on_keyword=on_keyword,
                )
                self.log_signal.emit(f"[{category}] ✓ {len(results)}개 완료")
                total += len(results)

            self.category_signal.emit("")
            self.finished.emit(f"[전체 완료] 4개 카테고리 — 총 {total}개 키워드")
        except Exception as e:
            self.finished.emit(f"[오류] {e}")


# ─── 키워드 분석 ────────────────────────────────────────────────────────────

class _KeywordAnalysisWorker(QThread):
    """Naver API로 키워드 경쟁도·연관키워드 분석 + Claude 제목 생성"""
    log_signal      = pyqtSignal(str)
    result_signal   = pyqtSignal(dict)   # 분석 결과
    titles_signal   = pyqtSignal(list)   # 제목 후보
    finished        = pyqtSignal()

    def __init__(self, keyword: str, blog_id: str):
        super().__init__()
        self.keyword = keyword
        self.blog_id = blog_id

    def run(self):
        try:
            from keyword_analyzer import analyze_keyword, filter_by_blog, generate_titles
            result = analyze_keyword(self.keyword, on_log=self.log_signal.emit)
            result["filtered"] = filter_by_blog(result["related"], self.blog_id)
            self.result_signal.emit(result)
            # 제목 생성 (분석 완료 후)
            self.log_signal.emit(f"[분석] SEO 제목 생성 중...")
            titles = generate_titles(self.keyword, self.blog_id, on_log=self.log_signal.emit)
            self.titles_signal.emit(titles)
        except Exception as e:
            self.log_signal.emit(f"[분석] 오류: {e}")
        finally:
            self.finished.emit()


class KeywordAnalysisDialog(QDialog):
    """키워드 분석 결과 다이얼로그 — 키워드·제목 선택 → 블로그 생성으로 연결"""
    keyword_selected = pyqtSignal(str)        # 키워드만 선택 (Claude가 제목 생성)
    title_forced     = pyqtSignal(str, str)   # (keyword, forced_title) — 제목 강제 적용

    _STYLE = """
        QDialog { background: #0d0f18; color: #e0e0e0; }
        QLabel  { color: #e0e0e0; }
        QTableWidget { background: #1a1d2e; color: #e0e0e0; gridline-color: #2a2d3e;
                       border: 1px solid #2a2d3e; font-size: 11px; }
        QTableWidget::item:selected { background: #4f8ef7; color: #fff; }
        QHeaderView::section { background: #1e2233; color: #9ca3af;
                               padding: 4px; border: none; font-size: 11px; }
        QTextEdit { background: #1a1d2e; color: #9ca3af; border: 1px solid #2a2d3e;
                    font-size: 10px; font-family: Menlo; }
        QPushButton { background: #1a1d2e; color: #9ca3af; border: 1px solid #2a2d3e;
                      border-radius: 4px; padding: 5px 12px; font-size: 11px; }
        QPushButton:hover { background: #4f8ef7; color: #fff; }
        QPushButton#use_btn { background: #22c55e; color: #fff; border: none; font-weight: bold; }
        QPushButton#use_btn:hover { background: #16a34a; }
    """

    def __init__(self, keyword: str, blog_id: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"🔍 키워드 분석 — {keyword}")
        self.setMinimumSize(720, 560)
        self.setStyleSheet(self._STYLE)
        self._keyword = keyword
        self._blog_id = blog_id
        self._worker = None
        self._selected_kw = keyword

        self._build_ui()
        # 모든 자식 위젯에 Enter키 차단 이벤트필터 설치
        for child in self.findChildren(QLineEdit):
            child.installEventFilter(self)
        self._run_analysis()

    def eventFilter(self, obj, event):
        from PyQt5.QtCore import QEvent
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            return True  # Enter 완전 차단
        return super().eventFilter(obj, event)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        # ── 상단: 메인 키워드 경쟁도 ──
        top = QHBoxLayout()
        self._main_label = QLabel(f"키워드: <b>{self._keyword}</b>")
        self._main_label.setStyleSheet("font-size:13px; color:#e0e0e0;")
        self._level_label = QLabel("분석 중...")
        self._level_label.setStyleSheet("font-size:12px; color:#f5a623;")
        top.addWidget(self._main_label)
        top.addStretch()
        top.addWidget(self._level_label)
        layout.addLayout(top)

        # ── 연관 키워드 탭 (네이버 / 다음) ──
        layout.addWidget(QLabel("📊 연관 키워드 (초록색 = 블로그 수준 적합)"))
        self._kw_tabs = QTabWidget()
        self._kw_tabs.setStyleSheet(
            "QTabBar::tab{background:#1a1d2e;color:#9ca3af;padding:4px 12px;font-size:11px;border:none;}"
            "QTabBar::tab:selected{background:#4f8ef7;color:#fff;border-radius:3px;}"
            "QTabWidget::pane{border:1px solid #2a2d3e;background:#0d0f18;}")
        self._comp_table   = self._make_kw_table()   # 경쟁도 탭
        self._volume_table = self._make_kw_table()   # 검색량 탭
        self._kw_tabs.addTab(self._comp_table,   "🔵 경쟁도 (발행량↑)")
        self._kw_tabs.addTab(self._volume_table, "🟠 검색량 (DataLab↓)")
        layout.addWidget(self._kw_tabs)

        # ── SEO 제목 후보 ──
        layout.addWidget(QLabel("✍ SEO 제목 후보 (클릭해서 선택)"))
        self._title_list = QListWidget()
        self._title_list.setMaximumHeight(120)
        self._title_list.setStyleSheet(
            "background:#1a1d2e; color:#e0e0e0; border:1px solid #2a2d3e; font-size:12px;")
        self._title_list.itemClicked.connect(self._on_title_clicked)
        layout.addWidget(self._title_list)

        # ── 선택된 키워드/제목 표시 ──
        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("선택:"))
        self._sel_edit = QLineEdit(self._keyword)
        self._sel_edit.setStyleSheet(
            "background:#1a1d2e; color:#e0e0e0; border:1px solid #4f8ef7;"
            "border-radius:4px; padding:4px 8px; font-size:12px;")
        sel_row.addWidget(self._sel_edit)
        layout.addLayout(sel_row)

        # ── 로그 ──
        self._log = QTextEdit()
        self._log.setMaximumHeight(80)
        self._log.setReadOnly(True)
        layout.addWidget(self._log)

        # ── 버튼 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("닫기")
        cancel_btn.setAutoDefault(False)
        cancel_btn.setDefault(False)
        cancel_btn.clicked.connect(self.reject)

        kw_btn = QPushButton("키워드만 사용 (Claude가 제목 생성)")
        kw_btn.setAutoDefault(False)
        kw_btn.setDefault(False)
        kw_btn.setStyleSheet(
            "background:#1e3a5f;color:#4f8ef7;border:1px solid #2a4a7f;"
            "border-radius:4px;padding:5px 12px;font-size:11px;")
        kw_btn.clicked.connect(self._use_keyword_only)

        title_btn = QPushButton("이 제목 그대로 사용")
        title_btn.setObjectName("use_btn")
        title_btn.setAutoDefault(False)
        title_btn.setDefault(False)
        title_btn.clicked.connect(self._use_with_title)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(kw_btn)
        btn_row.addWidget(title_btn)
        layout.addLayout(btn_row)

        # Enter키로 다이얼로그 닫히지 않도록 sel_edit returnPressed 차단
        self._sel_edit.returnPressed.connect(lambda: None)

    def _run_analysis(self):
        self._worker = _KeywordAnalysisWorker(self._keyword, self._blog_id)
        self._worker.log_signal.connect(self._append_log)
        self._worker.result_signal.connect(self._on_result)
        self._worker.titles_signal.connect(self._on_titles)
        self._worker.start()

    def _make_kw_table(self) -> QTableWidget:
        t = QTableWidget(0, 4)
        t.setHorizontalHeaderLabels(["키워드", "발행량", "난이도", "검색량"])
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        t.setColumnWidth(1, 80)
        t.setColumnWidth(2, 90)
        t.setColumnWidth(3, 65)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.itemSelectionChanged.connect(self._on_kw_selected)
        return t

    def _append_log(self, msg: str):
        self._log.append(msg)

    def _fill_table(self, table: QTableWidget, rows: list, filtered_kws: set):
        table.setRowCount(len(rows))
        for i, item in enumerate(rows):
            kw_item    = QTableWidgetItem(item["keyword"])
            total_item = QTableWidgetItem(f"{item['total']:,}" if item.get('total', -1) >= 0 else "-")
            level_item = QTableWidgetItem(item.get("level", "-"))
            score = item.get("score", -1.0)
            score_item = QTableWidgetItem(f"{score:.1f}" if score >= 0 else "-")
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            score_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            green = item["keyword"] in filtered_kws
            for it in (kw_item, total_item, level_item, score_item):
                if green:
                    it.setForeground(QColor("#22c55e"))
            table.setItem(i, 0, kw_item)
            table.setItem(i, 1, total_item)
            table.setItem(i, 2, level_item)
            table.setItem(i, 3, score_item)

    def _on_result(self, result: dict):
        total = result["total"]
        level = result["level"]
        color = "#22c55e" if "낮음" in level else ("#f5a623" if "보통" in level else "#ef4444")
        self._level_label.setText(f"발행량: {total:,}개 | {level}")
        self._level_label.setStyleSheet(f"font-size:12px; color:{color};")

        filtered_kws = {r["keyword"] for r in result.get("filtered", [])}
        self._fill_table(self._comp_table,   result.get("related", []),        filtered_kws)
        self._fill_table(self._volume_table, result.get("volume_sorted", []),  filtered_kws)

    def _on_titles(self, titles: list):
        self._title_list.clear()
        for t in titles:
            self._title_list.addItem(t)

    def _on_kw_selected(self):
        active = self._comp_table if self._kw_tabs.currentIndex() == 0 else self._volume_table
        rows = active.selectedItems()
        if rows:
            self._sel_edit.setText(rows[0].text())

    def _on_title_clicked(self, item):
        self._sel_edit.setText(item.text())

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            return  # Enter가 다이얼로그 닫는 것 방지
        super().keyPressEvent(event)

    def _detach_worker(self):
        """닫기 전 워커 시그널 끊기 — 소멸된 슬롯 호출로 인한 세그폴트 방지."""
        if self._worker:
            try:
                self._worker.log_signal.disconnect()
                self._worker.result_signal.disconnect()
                self._worker.titles_signal.disconnect()
                self._worker.finished.disconnect()
            except Exception:
                pass

    def accept(self):
        self._detach_worker()
        super().accept()

    def reject(self):
        self._detach_worker()
        super().reject()

    def _use_keyword_only(self):
        kw = self._sel_edit.text().strip()
        if kw:
            self.keyword_selected.emit(kw)
            self.accept()

    def _use_with_title(self):
        sel = self._sel_edit.text().strip()
        if not sel:
            return
        self.title_forced.emit(self._keyword, sel)
        self.accept()


# ─── 키워드 엔진 다이얼로그 ────────────────────────────────────────────────

class _KeywordWriteWorker(QThread):
    """키워드 직접 작성 워커 (Notion 큐 없이 바로 실행)"""
    log_signal = pyqtSignal(str)
    finished   = pyqtSignal(bool, str)  # success, title_or_reason

    def __init__(self, blog_id: str, keyword: str):
        super().__init__()
        self.blog_id = blog_id
        self.keyword = keyword

    def run(self):
        try:
            from agents import orchestrator
            result = orchestrator.run_single(
                self.blog_id,
                keyword=self.keyword,
                on_log=self.log_signal.emit,
            )
            self.finished.emit(result["success"], result.get("title") or result.get("reason", ""))
        except Exception as e:
            self.finished.emit(False, str(e))


class KeywordEngineDialog(QDialog):
    """4개 카테고리 전체 수집 + 카테고리 탭별 분류 표시"""

    CATEGORIES = ["IT", "금융", "여행", "살림", "정부지원금", "교통", "영화"]
    CAT_COLORS  = {
        "IT":         "#4da6ff",
        "금융":       "#44ccaa",
        "여행":       "#ff9966",
        "살림":       "#55dd77",
        "정부지원금": "#cc88ff",
        "교통":       "#ffdd55",
        "영화":       "#ff6688",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔑 키워드 엔진 — 전체 카테고리 수집")
        self.resize(1000, 660)
        self._worker = None
        self._selected_category = self.CATEGORIES[0]
        # 카테고리별 키워드 메모리 캐시
        self._cat_keywords: dict = {cat: [] for cat in self.CATEGORIES}
        self._build_ui()
        self._load_all_from_db()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ── 상단: 카테고리 탭 + 수집 버튼 ──
        top_row = QHBoxLayout()

        self._cat_btns = {}
        for cat in self.CATEGORIES:
            color = self.CAT_COLORS[cat]
            btn = QPushButton(cat)
            btn.setFixedHeight(32)
            btn.setCheckable(True)
            btn.setChecked(cat == self._selected_category)
            btn.setStyleSheet(
                f"QPushButton{{background:#1a1a2e;color:#aaa;border:2px solid #333;"
                f"border-radius:6px;font-size:12px;font-weight:bold;padding:0 14px;}}"
                f"QPushButton:checked{{background:{color}22;color:#fff;"
                f"border:2px solid {color};}}"
            )
            btn.clicked.connect(lambda _, c=cat: self._on_cat_clicked(c))
            self._cat_btns[cat] = btn
            top_row.addWidget(btn)

        top_row.addStretch()

        # 현재 수집 중 카테고리 표시
        self._collecting_label = QLabel("")
        self._collecting_label.setStyleSheet("color:#facc15;font-size:11px;font-weight:bold;")
        top_row.addWidget(self._collecting_label)

        self._refresh_btn = QPushButton("🔄 새로고침")
        self._refresh_btn.setFixedHeight(32)
        self._refresh_btn.setStyleSheet(
            "background:#374151;color:#fff;border-radius:6px;"
            "font-size:12px;font-weight:bold;padding:0 12px;border:none;")
        self._refresh_btn.clicked.connect(self._load_all_from_db)
        top_row.addWidget(self._refresh_btn)

        self._collect_btn = QPushButton("⬇  전체 수집 시작")
        self._collect_btn.setFixedHeight(32)
        self._collect_btn.setStyleSheet(
            "background:#16a34a;color:#fff;border-radius:6px;"
            "font-size:12px;font-weight:bold;padding:0 16px;border:none;")
        self._collect_btn.clicked.connect(self._start_collect)
        top_row.addWidget(self._collect_btn)

        self._stop_btn = QPushButton("⏹ 중지")
        self._stop_btn.setFixedHeight(32)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet(
            "background:#dc2626;color:#fff;border-radius:6px;"
            "font-size:12px;padding:0 14px;border:none;")
        self._stop_btn.clicked.connect(self._stop_collect)
        top_row.addWidget(self._stop_btn)

        root.addLayout(top_row)

        # ── 발행량 필터 행 ──
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("검색량 필터:"))
        self._filter_min = QLineEdit()
        self._filter_min.setPlaceholderText("최소 (예: 1000)")
        self._filter_min.setFixedWidth(90)
        self._filter_min.setFixedHeight(26)
        self._filter_min.setStyleSheet(
            "background:#1a1d2e;color:#fff;border:1px solid #333;"
            "border-radius:4px;padding:2px 6px;font-size:11px;")
        filter_row.addWidget(self._filter_min)
        filter_row.addWidget(QLabel("~"))
        self._filter_max = QLineEdit()
        self._filter_max.setPlaceholderText("최대 (예: 3000)")
        self._filter_max.setFixedWidth(90)
        self._filter_max.setFixedHeight(26)
        self._filter_max.setStyleSheet(
            "background:#1a1d2e;color:#fff;border:1px solid #333;"
            "border-radius:4px;padding:2px 6px;font-size:11px;")
        filter_row.addWidget(self._filter_max)
        filter_apply_btn = QPushButton("적용")
        filter_apply_btn.setFixedHeight(26)
        filter_apply_btn.setFixedWidth(50)
        filter_apply_btn.setStyleSheet(
            "background:#2563eb;color:#fff;border:none;"
            "border-radius:4px;font-size:11px;")
        filter_apply_btn.clicked.connect(lambda: self._render_table(self._selected_category))
        filter_row.addWidget(filter_apply_btn)
        filter_row.addStretch()
        root.addLayout(filter_row)

        # ── 중단: 스플리터 (테이블 | 로그) ──
        splitter = QSplitter(Qt.Horizontal)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["키워드", "점수", "검색량", "발행량", "상태"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            "QTableWidget{background:#0e0e1a;color:#e0e0e0;"
            "gridline-color:#222;border:1px solid #333;border-radius:6px;}"
            "QTableWidget::item:selected{background:#2563eb;}"
            "QHeaderView::section{background:#1a1a2e;color:#aaa;"
            "border:none;padding:4px;font-size:11px;}"
            "QTableWidget{alternate-background-color:#12121e;}"
        )
        splitter.addWidget(self._table)

        self._log_box = QTextEdit()
        self._log_box.setReadOnly(True)
        self._log_box.setFont(QFont("Menlo", 10))
        self._log_box.setMaximumWidth(300)
        self._log_box.setStyleSheet(
            "background:#0a0a14;color:#888;border:1px solid #333;"
            "border-radius:6px;padding:6px;font-size:10px;")
        self._log_box.setPlaceholderText("수집 로그...")
        splitter.addWidget(self._log_box)

        splitter.setSizes([680, 280])
        root.addWidget(splitter)

        # ── 상태 표시줄 ──
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color:#888;font-size:11px;")
        root.addWidget(self._status_label)

        # ── 하단 버튼 ──
        btn_row = QHBoxLayout()

        sel_all_btn = QPushButton("전체선택")
        sel_all_btn.setFixedHeight(28)
        sel_all_btn.setStyleSheet("background:#333;color:#fff;border-radius:4px;font-size:11px;border:none;")
        sel_all_btn.clicked.connect(self._table.selectAll)
        btn_row.addWidget(sel_all_btn)

        write_btn = QPushButton("✍  선택 키워드 작성")
        write_btn.setFixedHeight(28)
        write_btn.setStyleSheet(
            "background:#16a34a;color:#fff;border-radius:4px;"
            "font-size:11px;padding:0 12px;border:none;font-weight:bold;")
        write_btn.clicked.connect(self._write_selected)
        btn_row.addWidget(write_btn)

        del_btn = QPushButton("🗑  삭제")
        del_btn.setFixedHeight(28)
        del_btn.setStyleSheet(
            "background:#7f1d1d;color:#fca5a5;border-radius:4px;"
            "font-size:11px;padding:0 10px;border:none;")
        del_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(del_btn)

        btn_row.addStretch()

        close_btn = QPushButton("닫기")
        close_btn.setFixedHeight(28)
        close_btn.setStyleSheet("background:#555;color:#fff;border-radius:4px;font-size:11px;border:none;")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

    # ── DB에서 전체 카테고리 로드 ──
    def _load_all_from_db(self):
        try:
            from keyword_engine.db_handler import get_keywords_by_category
            for cat in self.CATEGORIES:
                rows = get_keywords_by_category(cat, n=30000)
                self._cat_keywords[cat] = rows
                self._update_cat_btn(cat)
            self._render_table(self._selected_category)
        except Exception as e:
            self._status_label.setText(f"DB 로드 오류: {e}")

    # ── 카테고리 탭 클릭 ──
    def _on_cat_clicked(self, category: str):
        self._selected_category = category
        for cat, btn in self._cat_btns.items():
            btn.setChecked(cat == category)
        self._render_table(category)

    # ── 테이블 렌더링 ──
    def _render_table(self, category: str):
        keywords = self._cat_keywords.get(category, [])
        # 발행량 필터 적용
        try:
            min_pub = int(self._filter_min.text()) if self._filter_min.text().strip() else 0
        except ValueError:
            min_pub = 0
        try:
            max_pub = int(self._filter_max.text()) if self._filter_max.text().strip() else 99999999
        except ValueError:
            max_pub = 99999999
        if min_pub > 0 or max_pub < 99999999:
            keywords = [k for k in keywords if min_pub <= k.get("volume", 0) <= max_pub]
        self._table.setRowCount(0)
        for row_idx, item in enumerate(keywords):
            self._table.insertRow(row_idx)
            self._table.setItem(row_idx, 0, QTableWidgetItem(item["keyword"]))
            s = QTableWidgetItem(f"{item['score']:,.0f}")
            s.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row_idx, 1, s)
            v = QTableWidgetItem(f"{item['volume']:,}")
            v.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row_idx, 2, v)
            p = QTableWidgetItem(f"{item.get('pub_count', 0):,}")
            p.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row_idx, 3, p)
            status = item.get("status", "pending")
            st = QTableWidgetItem("✓ 발행됨" if status == "published" else "")
            st.setForeground(QColor("#86efac" if status == "published" else "#888"))
            self._table.setItem(row_idx, 4, st)
        n = len(keywords)
        self._status_label.setText(
            f"[{category}]  {n}개 키워드"
            + ("  — 수집 시작을 눌러주세요" if n == 0 else "")
        )

    # ── 카테고리 버튼 배지 업데이트 ──
    def _update_cat_btn(self, category: str):
        n = len(self._cat_keywords.get(category, []))
        color = self.CAT_COLORS[category]
        label = f"{category}  ({n})" if n > 0 else category
        btn = self._cat_btns[category]
        btn.setText(label)

    # ── 수집 시작 ──
    def _start_collect(self):
        if self._worker and self._worker.isRunning():
            return
        self._collect_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._log_box.clear()
        self._log_box.append("[전체 수집] IT → 여행 → 살림 → 정부지원금 순서로 시작...")

        self._worker = KeywordCollectWorker(use_playwright=False)
        self._worker.log_signal.connect(self._log_box.append)
        self._worker.keyword_signal.connect(self._on_new_keyword)
        self._worker.category_signal.connect(self._on_collecting_category)
        self._worker.finished.connect(self._on_collect_done)
        self._worker.start()

    def _stop_collect(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._log_box.append("[수집] 중지 요청...")
        self._collect_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._collecting_label.setText("")

    def _on_collecting_category(self, category: str):
        if category:
            self._collecting_label.setText(f"● {category} 수집 중...")
        else:
            self._collecting_label.setText("")

    def _on_new_keyword(self, category: str, keyword: str, score: float, volume: int, pub_count: int):
        """수집된 키워드를 해당 카테고리 캐시에 저장 + 현재 탭이면 테이블에도 추가/업데이트"""
        item = {"keyword": keyword, "score": score, "volume": volume, "pub_count": pub_count}

        # 캐시에 이미 있으면 업데이트, 없으면 추가
        cat_list = self._cat_keywords[category]
        existing_idx = next((i for i, k in enumerate(cat_list) if k["keyword"] == keyword), None)
        if existing_idx is not None:
            cat_list[existing_idx] = item
        else:
            cat_list.append(item)

        self._update_cat_btn(category)

        if category == self._selected_category:
            # 테이블에 이미 있는 행이면 업데이트, 없으면 추가
            existing_row = None
            for r in range(self._table.rowCount()):
                if self._table.item(r, 0) and self._table.item(r, 0).text() == keyword:
                    existing_row = r
                    break

            if existing_row is None:
                existing_row = self._table.rowCount()
                self._table.insertRow(existing_row)

            self._table.setItem(existing_row, 0, QTableWidgetItem(keyword))
            s = QTableWidgetItem("—" if score == 0 else f"{score:,.0f}")
            s.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(existing_row, 1, s)
            v = QTableWidgetItem("조회중" if volume == 0 else f"{volume:,}")
            v.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(existing_row, 2, v)
            p = QTableWidgetItem("—" if pub_count == 0 else f"{pub_count:,}")
            p.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(existing_row, 3, p)
            if existing_row == self._table.rowCount() - 1:
                self._table.scrollToBottom()

        n = len(self._cat_keywords[category])
        if category == self._selected_category:
            self._status_label.setText(f"[{category}]  {n}개 키워드 (수집 중...)")

    def _on_collect_done(self, msg: str):
        self._log_box.append(msg)
        self._collect_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._collecting_label.setText("")
        # 완료 후 DB 키워드를 in-memory에 병합 (기존 목록 유지 + 업데이트)
        try:
            from keyword_engine.db_handler import get_keywords_by_category
            for cat in self.CATEGORIES:
                db_rows = get_keywords_by_category(cat, n=1000)
                cat_list = self._cat_keywords[cat]
                kw_index = {k["keyword"]: i for i, k in enumerate(cat_list)}
                for row in db_rows:
                    kw = row["keyword"]
                    if kw in kw_index:
                        # 점수/검색량 업데이트
                        cat_list[kw_index[kw]].update(row)
                    else:
                        # 새 키워드 추가
                        cat_list.append(row)
                        kw_index[kw] = len(cat_list) - 1
                # 점수 내림차순 정렬
                self._cat_keywords[cat] = sorted(cat_list, key=lambda x: x.get("score", 0), reverse=True)
                self._update_cat_btn(cat)
            self._render_table(self._selected_category)
        except Exception as e:
            self._status_label.setText(f"DB 로드 오류: {e}")

    # ── 선택 키워드 작성 시작 ──
    def _write_selected(self):
        selected_rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()))
        if not selected_rows:
            QMessageBox.information(self, "선택 없음", "작성할 키워드 행을 선택해주세요.")
            return

        from keyword_engine.category_engine import CATEGORY_MAP
        blog_id = CATEGORY_MAP.get(self._selected_category)
        if not blog_id:
            QMessageBox.warning(self, "오류", "블로그 ID를 찾을 수 없습니다.")
            return

        # 첫 번째 선택 행의 키워드만 처리 (한 번에 1개씩)
        row = selected_rows[0]
        kw_item = self._table.item(row, 0)
        if not kw_item:
            return
        keyword = kw_item.text()

        reply = QMessageBox.question(
            self, "작성 시작",
            f"[{self._selected_category}] '{keyword}' 키워드로 글을 작성할까요?\n\n블로그: {blog_id}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # 상태 표시
        status_item = QTableWidgetItem("작성중...")
        status_item.setForeground(QColor("#facc15"))
        self._table.setItem(row, 4, status_item)
        self._log_box.append(f"\n[작성] '{keyword}' 시작 → {blog_id}")

        # 워커 실행
        self._write_worker = _KeywordWriteWorker(blog_id, keyword)
        self._write_worker.log_signal.connect(self._log_box.append)
        self._write_worker.finished.connect(lambda ok, title, kw=keyword, r=row: self._on_write_done(ok, title, kw, r))
        self._write_worker.start()

    def _on_write_done(self, success: bool, title: str, keyword: str, row: int):
        if success:
            self._log_box.append(f"[완료] '{keyword}' → {title}")
            # DB 상태 업데이트
            from keyword_engine.db_handler import set_keyword_status
            set_keyword_status(keyword, "published")
            # in-memory 업데이트
            cat_list = self._cat_keywords[self._selected_category]
            for item in cat_list:
                if item["keyword"] == keyword:
                    item["status"] = "published"
                    break
            # 테이블 행 상태 표시
            if row < self._table.rowCount():
                status_item = QTableWidgetItem("✓ 발행됨")
                status_item.setForeground(QColor("#86efac"))
                self._table.setItem(row, 4, status_item)
        else:
            self._log_box.append(f"[실패] '{keyword}' → {title}")
            if row < self._table.rowCount():
                status_item = QTableWidgetItem("✗ 실패")
                status_item.setForeground(QColor("#fca5a5"))
                self._table.setItem(row, 4, status_item)

    # ── 선택 키워드 삭제 ──
    def _delete_selected(self):
        selected_rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()), reverse=True)
        if not selected_rows:
            QMessageBox.information(self, "선택 없음", "삭제할 키워드 행을 선택해주세요.")
            return

        keywords = [self._table.item(r, 0).text() for r in selected_rows if self._table.item(r, 0)]
        reply = QMessageBox.question(
            self, "삭제 확인",
            f"{len(keywords)}개 키워드를 삭제할까요?\n{', '.join(keywords[:5])}{'...' if len(keywords) > 5 else ''}",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        from keyword_engine.db_handler import delete_keyword
        for kw in keywords:
            delete_keyword(kw)

        # in-memory 및 테이블에서 제거
        cat_list = self._cat_keywords[self._selected_category]
        self._cat_keywords[self._selected_category] = [k for k in cat_list if k["keyword"] not in keywords]
        for row in selected_rows:
            self._table.removeRow(row)
        self._update_cat_btn(self._selected_category)
        self._status_label.setText(f"[{self._selected_category}] {len(keywords)}개 삭제됨")

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(2000)
        super().closeEvent(event)



class BlogAutomationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Blog Automation v2")
        self.setFixedWidth(320)
        self.resize(320, 600)
        self.setMinimumHeight(400)
        self.sched_worker  = None
        self._single_worker = None
        self._selected_keyword = None   # 키워드 큐에서 선택된 키워드 저장
        self._forced_title = None       # 키워드 분석에서 강제 적용 제목
        self._build_ui()
        self._refresh_stats()
        # 앱 시작 시 스케줄러 자동 실행
        # 자동 시작 비활성화 — 수동으로 실행 버튼 눌러야 함
        pass

    def _auto_start_scheduler(self):
        pass

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 스택 (메인 뷰 / 설정 뷰) ──
        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        # ── 메인 뷰 ──
        main_w = QWidget()
        ml = QVBoxLayout(main_w)
        ml.setContentsMargins(10, 10, 10, 10)
        ml.setSpacing(8)

        # 1. 상단바
        topbar = QHBoxLayout()
        title_lbl = QLabel("🚀 Auto-Posting")
        title_lbl.setStyleSheet(
            "color:#e0e0e0;font-size:14px;font-weight:bold;background:transparent;")
        topbar.addWidget(title_lbl)
        topbar.addStretch()

        # AI 토글 프레임
        ai_frame = QFrame()
        ai_frame.setStyleSheet(
            "background:#1a1d2e;border:1px solid #1e2233;border-radius:6px;")
        ai_lay = QHBoxLayout(ai_frame)
        ai_lay.setContentsMargins(2, 2, 2, 2)
        ai_lay.setSpacing(2)
        self._ai_claude_btn = QPushButton("Claude")
        self._ai_claude_btn.setFixedSize(54, 22)
        self._ai_gemini_btn = QPushButton("Gemini")
        self._ai_gemini_btn.setFixedSize(54, 22)
        self._ai_claude_btn.clicked.connect(lambda: self._set_ai_provider("claude"))
        self._ai_gemini_btn.clicked.connect(lambda: self._set_ai_provider("gemini"))
        ai_lay.addWidget(self._ai_claude_btn)
        ai_lay.addWidget(self._ai_gemini_btn)
        topbar.addWidget(ai_frame)

        # ⚙ 설정 버튼
        self._settings_btn = QPushButton("⚙")
        self._settings_btn.setFixedSize(28, 28)
        self._settings_btn.setStyleSheet(
            "background:#1a1d2e;color:#9ca3af;border:1px solid #1e2233;"
            "border-radius:5px;font-size:13px;")
        self._settings_btn.clicked.connect(self._toggle_settings)
        topbar.addWidget(self._settings_btn)
        ml.addLayout(topbar)

        # 2. 에이전트 드롭다운 + 뱃지
        agent_row = QHBoxLayout()
        self._agent_combo = QComboBox()
        self._agent_combo.addItems([
            "goodisak", "nolja100", "salim1su", "baremi542",
            "woll100", "phn0502", "triplog", "me1091",
            "blogspot_travel", "blogspot_it", "blogspot_daily",
        ])
        # config_custom.json에 저장된 커스텀 블로그 로드
        self._load_custom_blogs()
        self._agent_combo.currentTextChanged.connect(self._on_agent_changed)
        agent_row.addWidget(self._agent_combo, 1)

        # 블로그 추가 버튼
        self._add_blog_btn = QPushButton("＋")
        self._add_blog_btn.setFixedSize(28, 28)
        self._add_blog_btn.setToolTip("새 블로그 추가")
        self._add_blog_btn.setStyleSheet(
            "background:#1a1d2e;color:#4f8ef7;border:1px solid #1e2233;"
            "border-radius:5px;font-size:15px;font-weight:bold;")
        self._add_blog_btn.clicked.connect(self._open_add_blog_dialog)
        agent_row.addWidget(self._add_blog_btn)

        self._badge = QLabel()
        self._badge.setFixedHeight(24)
        self._badge.setContentsMargins(8, 2, 8, 2)
        self._badge.setStyleSheet("border-radius:4px;font-size:10px;font-weight:bold;")
        agent_row.addWidget(self._badge)
        ml.addLayout(agent_row)

        # 2-1. 키워드 직접 입력란
        kw_row = QHBoxLayout()
        kw_row.setSpacing(6)
        self._kw_input = QLineEdit()
        self._kw_input.setPlaceholderText("키워드 직접 입력 (비워두면 큐에서 자동 선택)")
        self._kw_input.setStyleSheet(
            "background:#1a1d2e;color:#e0e0e0;border:1px solid #1e2233;"
            "border-radius:5px;font-size:12px;padding:5px 8px;")
        self._kw_input.returnPressed.connect(self._run_selected)
        kw_row.addWidget(self._kw_input)
        self._kw_analyze_btn = QPushButton("🔍 분석")
        self._kw_analyze_btn.setFixedSize(64, 30)
        self._kw_analyze_btn.setStyleSheet(
            "background:#1e3a5f;color:#4f8ef7;border:1px solid #2a4a7f;"
            "border-radius:5px;font-size:11px;font-weight:bold;")
        self._kw_analyze_btn.clicked.connect(self._open_keyword_analysis)
        kw_row.addWidget(self._kw_analyze_btn)
        ml.addLayout(kw_row)

        # 3. 통계 카드 3개
        stats_row = QHBoxLayout()
        stats_row.setSpacing(6)
        self._card_today = self._make_stat_card("오늘 발행", "0",    "#22c55e")
        self._card_queue = self._make_stat_card("대기 키워드", "0",  "#f5a623")
        self._card_next  = self._make_stat_card("다음 발행", "--:--","#4f8ef7")
        for c in (self._card_today, self._card_queue, self._card_next):
            stats_row.addWidget(c)
        ml.addLayout(stats_row)

        # 4. 탭 (로그 / 키워드 큐)
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane {
                border:1px solid #1e2233; background:#0d0f18; border-radius:6px;
            }
            QTabBar::tab {
                background:#1a1d2e; color:#9ca3af;
                padding:5px 14px; font-size:11px; border:none;
            }
            QTabBar::tab:selected { background:#4f8ef7; color:#fff; border-radius:3px; }
        """)

        # 로그 탭
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("Menlo", 10))
        self.log_box.setStyleSheet(
            "background:#0d0f18;color:#c9d1d9;border:none;padding:6px;")
        self._tabs.addTab(self.log_box, "로그")

        # 키워드 큐 탭
        kw_w = QWidget()
        kw_l = QVBoxLayout(kw_w)
        kw_l.setContentsMargins(6, 6, 6, 6)
        kw_l.setSpacing(4)
        self._kw_list = QListWidget()
        self._kw_list.setStyleSheet(
            "background:#0d0f18;color:#c9d1d9;border:none;font-size:11px;")
        self._kw_list.itemClicked.connect(
            lambda item: setattr(self, '_selected_keyword', item.text()))
        kw_l.addWidget(self._kw_list)
        add_kw_btn = QPushButton("+ 키워드 추가")
        add_kw_btn.setStyleSheet(
            "background:#1a1d2e;color:#9ca3af;border:1px solid #1e2233;"
            "border-radius:5px;font-size:11px;padding:4px;")
        add_kw_btn.clicked.connect(self._add_keyword)
        kw_l.addWidget(add_kw_btn)

        kw_engine_btn = QPushButton("🔑 키워드 엔진")
        kw_engine_btn.setStyleSheet(
            "background:#1a2a1a;color:#55dd77;border:1px solid #2a4a2a;"
            "border-radius:5px;font-size:11px;padding:4px;")
        kw_engine_btn.clicked.connect(self._open_keyword_engine)
        kw_l.addWidget(kw_engine_btn)

        self._tabs.addTab(kw_w, "키워드 큐")
        self._agent_combo.currentTextChanged.connect(
            lambda _: (self._load_kw_queue(), self._refresh_stats(), setattr(self, '_selected_keyword', None)))

        ml.addWidget(self._tabs, 1)

        # 5. 하단 버튼
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.run_all_btn = QPushButton("▶▶  전체 실행")
        self.run_all_btn.setStyleSheet(
            "background:#27ae60;color:#fff;border:none;border-radius:6px;"
            "font-size:12px;font-weight:bold;min-height:32px;")
        self.run_all_btn.clicked.connect(self._run_all)
        self.run_btn = QPushButton("▶  실행")
        self.run_btn.setStyleSheet(
            "background:#4f8ef7;color:#fff;border:none;border-radius:6px;"
            "font-size:12px;font-weight:bold;min-height:32px;")
        self.run_btn.clicked.connect(self._run_selected)
        self.pause_btn = QPushButton("⏸  정지")
        self.pause_btn.setEnabled(False)
        self.pause_btn.setStyleSheet(
            "background:#1a1d2e;color:#e0e0e0;border:1px solid #1e2233;"
            "border-radius:6px;font-size:12px;min-height:32px;")
        self.pause_btn.clicked.connect(self._stop_worker)
        reset_btn = QPushButton("↺  리셋")
        reset_btn.setStyleSheet(
            "background:#1a1d2e;color:#e0e0e0;border:1px solid #1e2233;"
            "border-radius:6px;font-size:12px;min-height:32px;")
        reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(self.run_all_btn, 2)
        btn_row.addWidget(self.run_btn, 2)
        btn_row.addWidget(self.pause_btn, 1)
        btn_row.addWidget(reset_btn, 1)
        ml.addLayout(btn_row)

        self._stack.addWidget(main_w)

        # ── 설정 뷰 ──
        settings_wrap = QWidget()
        sw_l = QVBoxLayout(settings_wrap)
        sw_l.setContentsMargins(0, 0, 0, 0)
        sw_l.setSpacing(0)

        back_bar = QWidget()
        back_bar.setStyleSheet("background:#13151f;border-bottom:1px solid #1e2233;")
        bb_l = QHBoxLayout(back_bar)
        bb_l.setContentsMargins(10, 6, 10, 6)
        back_btn = QPushButton("← 돌아가기")
        back_btn.setStyleSheet(
            "background:transparent;color:#4f8ef7;border:none;"
            "font-size:12px;text-align:left;")
        back_btn.clicked.connect(self._toggle_settings)
        bb_l.addWidget(back_btn)
        bb_l.addStretch()
        sw_l.addWidget(back_bar)

        self._settings_panel = _SettingsPanel()
        self._settings_panel.saved.connect(self._toggle_settings)
        sw_l.addWidget(self._settings_panel, 1)
        self._stack.addWidget(settings_wrap)

        # 초기화
        self._set_ai_provider("claude")
        self._on_agent_changed(self._agent_combo.currentText())
        self._load_kw_queue()

    # ── 통계 카드 헬퍼 ──
    def _make_stat_card(self, label: str, val: str, color: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "background:#1a1d2e;border:1px solid #1e2233;border-radius:7px;")
        l = QVBoxLayout(card)
        l.setContentsMargins(6, 8, 6, 8)
        l.setSpacing(2)
        v = QLabel(val)
        v.setStyleSheet(f"color:{color};font-size:15px;font-weight:bold;"
                        "background:transparent;border:none;")
        v.setAlignment(Qt.AlignCenter)
        n = QLabel(label)
        n.setStyleSheet(
            "color:#9ca3af;font-size:9px;background:transparent;border:none;")
        n.setAlignment(Qt.AlignCenter)
        l.addWidget(v)
        l.addWidget(n)
        card._val = v
        return card

    def _set_card_val(self, card: QFrame, val: str):
        card._val.setText(val)

    # ── 통계 갱신 ──
    def _refresh_stats(self):
        try:
            from keyword_engine import db_handler as _db
            blog_id  = self._agent_combo.currentText()
            category = BLOG_CATEGORIES.get(blog_id, "")
            rows = _db.get_keywords_by_category(category, n=200)
            pending   = sum(1 for r in rows if r.get("status", "pending") == "pending")
            published = sum(1 for r in rows if r.get("status", "pending") == "published")
            self._set_card_val(self._card_today, str(published))
            self._set_card_val(self._card_queue, str(pending))
        except Exception:
            pass
        QTimer.singleShot(60000, self._refresh_stats)

    # ── 커스텀 블로그 로드 ──
    def _load_custom_blogs(self):
        """config_custom.json에 저장된 블로그를 콤보박스에 추가"""
        custom_path = _Path(os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(_Path(__file__).parent))) / "config_custom.json"
        if not custom_path.exists():
            return
        import json
        try:
            data = json.loads(custom_path.read_text(encoding="utf-8"))
        except Exception:
            return
        existing = [self._agent_combo.itemText(i) for i in range(self._agent_combo.count())]
        for account in data.get("accounts", []):
            blog_id  = account.get("blog", "")
            category = account.get("category", "기타")
            platform = account.get("platform", "tistory")
            if blog_id and blog_id not in existing:
                self._agent_combo.addItem(blog_id)
                BLOG_CATEGORIES[blog_id] = category
                _bg, _fg, _border, _name = AddBlogDialog._PLATFORM_COLORS.get(
                    platform, ("#33333322", "#aaa", "#33333344", "Unknown"))
                _PLATFORM_INFO[blog_id] = (_name, _bg, _fg, _border)

    # ── 블로그 추가 다이얼로그 열기 ──
    def _open_add_blog_dialog(self):
        dlg = AddBlogDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            blog_id = dlg.result_blog_id
            if blog_id:
                existing = [self._agent_combo.itemText(i) for i in range(self._agent_combo.count())]
                if blog_id not in existing:
                    self._agent_combo.addItem(blog_id)
                self._agent_combo.setCurrentText(blog_id)

    # ── 에이전트 선택 → 뱃지 갱신 ──
    def _on_agent_changed(self, blog_id: str):
        info = _PLATFORM_INFO.get(blog_id, ("Unknown","#22222266","#888","#22222244"))
        platform, bg, text, border = info
        self._badge.setText(platform)
        self._badge.setStyleSheet(
            f"background:{bg};color:{text};border:1px solid {border};"
            "border-radius:4px;font-size:10px;font-weight:bold;padding:2px 8px;")

    # ── 설정 패널 토글 ──
    def _toggle_settings(self):
        self._stack.setCurrentIndex(1 - self._stack.currentIndex())

    # ── AI 프로바이더 선택 ──
    def _set_ai_provider(self, provider: str):
        os.environ["AI_PROVIDER"] = provider
        act = ("background:#2563eb;color:#fff;border-radius:4px;border:none;"
               "font-size:11px;font-weight:bold;")
        inact = ("background:transparent;color:#4a5568;border:none;"
                 "border-radius:4px;font-size:11px;")
        self._ai_claude_btn.setStyleSheet(act  if provider == "claude" else inact)
        self._ai_gemini_btn.setStyleSheet(act  if provider == "gemini" else inact)
        self.log_box.append(f"[AI] {provider.upper()} 선택됨")

    # ── 실행 버튼 ──
    def _run_all(self):
        if self._single_worker and self._single_worker.isRunning():
            self.log_box.append("[전체실행] 이미 실행 중입니다.")
            return
        if hasattr(self, '_all_proc') and self._all_proc and self._all_proc.poll() is None:
            self.log_box.append("[전체실행] 이미 실행 중입니다.")
            return
        import subprocess, threading, shutil
        from pathlib import Path
        # PyInstaller 빌드 내부가 아닌 실제 프로젝트 폴더 사용
        project_dir = Path("/Users/hana/Downloads/blog-automation-v2")
        script = project_dir / "overnight_run.py"
        self.log_box.append("[전체실행] overnight_run.py 시작...")
        self.run_all_btn.setEnabled(False)
        self.run_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self._all_stop = threading.Event()
        # PyInstaller 환경에서 sys.executable은 앱 자체 → python3 직접 사용
        python_bin = shutil.which("python3") or shutil.which("python") or "/usr/local/bin/python3"
        self._all_proc = subprocess.Popen(
            [python_bin, str(script)],
            cwd=str(project_dir),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
        def _stream():
            for line in self._all_proc.stdout:
                if self._all_stop.is_set():
                    break
                self._append_log(line.rstrip())
            self._all_proc.wait()
            self.run_all_btn.setEnabled(True)
            self.run_btn.setEnabled(True)
            self.pause_btn.setEnabled(False)
            if self._all_stop.is_set():
                self._append_log("[전체실행] 정지됨")
            else:
                self._append_log("[전체실행] 완료")
        threading.Thread(target=_stream, daemon=True).start()

    def _run_selected(self):
        try:
            if self._single_worker and self._single_worker.isRunning():
                self.log_box.append("[실행] 이미 실행 중입니다.")
                return
            blog_id = self._agent_combo.currentText()
            keyword = self._kw_input.text().strip() or getattr(self, '_selected_keyword', None) or None
            if keyword:
                self.log_box.append(f"[실행] {blog_id} — 키워드: '{keyword}'")
            else:
                self.log_box.append(f"[실행] {blog_id} 시작...")
            self.run_btn.setEnabled(False)
            self.pause_btn.setEnabled(True)
            forced_title = getattr(self, '_forced_title', None)
            self._forced_title = None
            self._single_worker = SingleRunWorker(blog_id, keyword=keyword, forced_title=forced_title)
            self._single_worker.log_signal.connect(self._append_log)
            self._single_worker.status_signal.connect(self._on_status)
            self._single_worker.finished.connect(self._on_run_done)
            self._single_worker.start()
        except Exception as e:
            import traceback
            self.log_box.append(f"[오류] 실행 실패: {e}")
            self.log_box.append(traceback.format_exc())
            self.run_btn.setEnabled(True)
            self.pause_btn.setEnabled(False)

    def _stop_worker(self):
        if self.sched_worker and self.sched_worker.isRunning():
            self.sched_worker.stop()
        if self._single_worker and self._single_worker.isRunning():
            self._single_worker.terminate()
        if hasattr(self, '_all_proc') and self._all_proc and self._all_proc.poll() is None:
            if hasattr(self, '_all_stop'):
                self._all_stop.set()
            self._all_proc.terminate()
            self.run_all_btn.setEnabled(True)
            self.run_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.run_btn.setEnabled(True)

    def _reset(self):
        self.log_box.clear()
        self._set_card_val(self._card_today, "0")
        self._set_card_val(self._card_queue, "0")
        self._set_card_val(self._card_next,  "--:--")
        self._refresh_stats()
        self._load_kw_queue()

    def _on_run_done(self, text):
        self._append_log(text)
        self.run_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self._refresh_stats()
        self._load_kw_queue()

    def _on_status(self, agent_id: str, state: str):
        pass  # 씬 없음 — 로그로 충분

    def _append_log(self, msg):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.append(
            f'<span style="color:#4a5568;">[{ts}]</span> {msg}')

    # ── 키워드 큐 로드 ──
    def _load_kw_queue(self):
        self._kw_list.clear()
        try:
            from keyword_engine import db_handler as _db
            blog_id  = self._agent_combo.currentText()
            category = BLOG_CATEGORIES.get(blog_id, "")
            rows = _db.get_keywords_by_category(category, n=30)
            for r in rows:
                kw     = r["keyword"]
                status = r.get("status", "pending")
                item   = QListWidgetItem(kw)
                if status == "published":
                    f = item.font(); f.setStrikeOut(True); item.setFont(f)
                    item.setForeground(QColor("#4a5568"))
                else:
                    item.setForeground(QColor("#9ca3af"))
                self._kw_list.addItem(item)
        except Exception:
            pass

    def _open_keyword_engine(self):
        dlg = KeywordEngineDialog(self)
        dlg.exec()

    def _open_keyword_analysis(self):
        try:
            keyword = self._kw_input.text().strip()
            if not keyword:
                QMessageBox.warning(self, "키워드 없음", "분석할 키워드를 먼저 입력하세요.")
                return
            blog_id = self._agent_combo.currentText()
            dlg = KeywordAnalysisDialog(keyword, blog_id, self)
            def _on_kw(kw):
                self._kw_input.setText(kw)
                self._forced_title = None
            def _on_title(kw, title):
                self._kw_input.setText(kw)
                self._forced_title = title
                self.log_box.append(f"[키워드분석] 강제 제목 설정: '{title}' — 지금 실행 버튼을 눌러주세요")
            dlg.keyword_selected.connect(_on_kw)
            dlg.title_forced.connect(_on_title)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"키워드 분석 창 열기 실패:\n{e}")

    def _add_keyword(self):
        text, ok = QInputDialog.getText(self, "키워드 추가", "키워드:")
        if not ok or not text.strip():
            return
        blog_id  = self._agent_combo.currentText()
        category = BLOG_CATEGORIES.get(blog_id, "")
        try:
            from keyword_engine import db_handler as _db
            _db.upsert_keyword(text.strip(), score=0, volume=0,
                               pub_count=0, category=category)
            self.log_box.append(f"[큐] 키워드 추가: {text.strip()}")
        except Exception as e:
            self.log_box.append(f"[오류] 키워드 추가 실패: {e}")
        self._load_kw_queue()
        self._refresh_stats()


if __name__ == "__main__":
    import traceback

    def _excepthook(exc_type, exc_val, exc_tb):
        msg = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
        print(msg, file=sys.stderr)
        try:
            QMessageBox.critical(None, "오류 발생", f"{exc_type.__name__}: {exc_val}\n\n앱을 계속 사용할 수 있습니다.")
        except Exception:
            pass

    sys.excepthook = _excepthook

    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLE)
    window = BlogAutomationApp()
    window.show()
    sys.exit(app.exec_())
