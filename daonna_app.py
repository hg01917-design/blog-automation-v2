"""
다온나 상점 상품등록 앱
=======================
사전 준비:
  - Chrome CDP 포트 9223 실행 중
  - domeggook.com 로그인 탭 열려 있어야 함
  - gemini.google.com 탭 열려 있어야 썸네일 자동 생성
"""
import sys
import os
import json
import subprocess
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QFrame, QSpinBox, QCheckBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont

PROJECT_DIR  = Path(__file__).parent
COMPARE_FILE = Path("/tmp/daonna_compare.json")
PROGRESS_FILE = Path("/tmp/daonna_upload_progress.json")

DARK_STYLE = """
QMainWindow { background: #13151f; }
QWidget     { background: #13151f; color: #e0e0e0; }
QLabel      { color: #e0e0e0; font-size: 12px; }
QTextEdit {
    background: #0d0f18; color: #c9d1d9;
    border: 1px solid #1e2233; border-radius: 6px;
    padding: 6px; font-size: 11px;
}
QPushButton {
    padding: 4px 12px; border: none; border-radius: 5px;
    font-size: 12px; color: #fff;
}
QSpinBox {
    background: #1a1d2e; color: #e0e0e0;
    border: 1px solid #1e2233; border-radius: 5px;
    padding: 4px 8px; font-size: 12px;
}
QScrollBar:vertical {
    background: #1a1d2e; width: 6px; border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #4a5568; border-radius: 3px;
}
"""


class DaonnaWorker(QThread):
    log_signal = pyqtSignal(str)
    finished   = pyqtSignal(bool)   # True=성공

    def __init__(self, mode: str, max_count: int = 10, skip_gemini: bool = False):
        super().__init__()
        self.mode        = mode       # "collect" | "upload" | "all"
        self.max_count   = max_count
        self.skip_gemini = skip_gemini
        self._proc     = None

    def stop(self):
        if self._proc:
            self._proc.terminate()

    def _run_script(self, script: str, args: list[str] = []) -> bool:
        cmd = [sys.executable, str(PROJECT_DIR / script)] + args
        self.log_signal.emit(f"▶ {' '.join(cmd)}")
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in self._proc.stdout:
            self.log_signal.emit(line.rstrip())
        self._proc.wait()
        return self._proc.returncode == 0

    def run(self):
        try:
            if self.mode in ("collect", "all"):
                self.log_signal.emit("\n[1단계] 미등록 상품 수집 중...")
                ok = self._run_script("daonna_collector.py")
                if not ok:
                    self.log_signal.emit("❌ 수집 실패")
                    self.finished.emit(False)
                    return
                self.log_signal.emit("✅ 수집 완료")
                if self.mode == "collect":
                    self.finished.emit(True)
                    return

            if self.mode in ("upload", "all"):
                self.log_signal.emit(f"\n[2단계] 상품 등록 시작 (최대 {self.max_count}개)...")
                args = [str(self.max_count)]
                if self.skip_gemini:
                    args.append("--no-gemini")
                ok = self._run_script("daonna_upload_bot.py", args)
                if ok:
                    self.log_signal.emit("✅ 등록 완료")
                else:
                    self.log_signal.emit("⚠️ 등록 중 오류 발생")
                self.finished.emit(ok)
        except Exception as e:
            self.log_signal.emit(f"❌ 오류: {e}")
            self.finished.emit(False)


class DaonnaApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🛒 다온나 상품등록")
        self.setFixedWidth(340)
        self.resize(340, 580)
        self._worker = None
        self._build_ui()
        self._refresh_stats()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # 타이틀
        title = QLabel("🛒  다온나 상품등록 봇")
        title.setStyleSheet(
            "color:#e0e0e0;font-size:14px;font-weight:bold;background:transparent;")
        root.addWidget(title)

        # 통계 카드
        stats_row = QHBoxLayout()
        stats_row.setSpacing(6)
        self._card_missing  = self._card("미등록", "—", "#f5a623")
        self._card_done     = self._card("완료",   "—", "#22c55e")
        self._card_failed   = self._card("실패",   "—", "#ef4444")
        for c in (self._card_missing, self._card_done, self._card_failed):
            stats_row.addWidget(c)
        root.addLayout(stats_row)

        # 등록 수 설정 + Gemini 건너뛰기
        max_row = QHBoxLayout()
        max_lbl = QLabel("오늘 등록 최대")
        max_lbl.setStyleSheet("color:#9ca3af;font-size:11px;background:transparent;")
        self._max_spin = QSpinBox()
        self._max_spin.setRange(1, 100)
        self._max_spin.setValue(10)
        self._max_spin.setFixedWidth(70)
        max_row.addWidget(max_lbl)
        max_row.addWidget(self._max_spin)
        max_row.addStretch()
        self._skip_gemini_chk = QCheckBox("Gemini 건너뛰기")
        self._skip_gemini_chk.setStyleSheet(
            "color:#9ca3af;font-size:11px;background:transparent;")
        max_row.addWidget(self._skip_gemini_chk)
        root.addLayout(max_row)

        # 버튼 행
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._btn_all = QPushButton("▶  수집 + 등록")
        self._btn_all.setStyleSheet(
            "background:#4f8ef7;color:#fff;border:none;border-radius:6px;"
            "font-size:12px;font-weight:bold;min-height:32px;")
        self._btn_all.clicked.connect(lambda: self._start("all"))

        self._btn_collect = QPushButton("🔍 수집만")
        self._btn_collect.setStyleSheet(
            "background:#1a1d2e;color:#e0e0e0;border:1px solid #1e2233;"
            "border-radius:6px;font-size:12px;min-height:32px;")
        self._btn_collect.clicked.connect(lambda: self._start("collect"))

        self._btn_upload = QPushButton("⬆ 등록만")
        self._btn_upload.setStyleSheet(
            "background:#1a1d2e;color:#e0e0e0;border:1px solid #1e2233;"
            "border-radius:6px;font-size:12px;min-height:32px;")
        self._btn_upload.clicked.connect(lambda: self._start("upload"))

        self._btn_stop = QPushButton("⏹")
        self._btn_stop.setEnabled(False)
        self._btn_stop.setFixedWidth(36)
        self._btn_stop.setStyleSheet(
            "background:#1a1d2e;color:#ef4444;border:1px solid #2d1f1f;"
            "border-radius:6px;font-size:14px;min-height:32px;")
        self._btn_stop.clicked.connect(self._stop)

        btn_row.addWidget(self._btn_all, 3)
        btn_row.addWidget(self._btn_collect, 2)
        btn_row.addWidget(self._btn_upload, 2)
        btn_row.addWidget(self._btn_stop, 1)
        root.addLayout(btn_row)

        # 로그 박스
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Menlo", 10))
        root.addWidget(self._log, 1)

    def _card(self, label: str, val: str, color: str) -> QFrame:
        f = QFrame()
        f.setStyleSheet(
            "background:#1a1d2e;border:1px solid #1e2233;border-radius:7px;")
        l = QVBoxLayout(f)
        l.setContentsMargins(6, 8, 6, 8)
        l.setSpacing(2)
        v = QLabel(val)
        v.setStyleSheet(
            f"color:{color};font-size:15px;font-weight:bold;"
            "background:transparent;border:none;")
        v.setAlignment(Qt.AlignCenter)
        n = QLabel(label)
        n.setStyleSheet(
            "color:#9ca3af;font-size:9px;background:transparent;border:none;")
        n.setAlignment(Qt.AlignCenter)
        l.addWidget(v)
        l.addWidget(n)
        f._val = v
        return f

    def _refresh_stats(self):
        # 미등록
        missing = "—"
        if COMPARE_FILE.exists():
            try:
                d = json.loads(COMPARE_FILE.read_text(encoding="utf-8"))
                missing = str(len(d.get("missing_in_daonna", [])))
            except Exception:
                pass
        self._card_missing._val.setText(missing)

        # 완료/실패
        done, failed = "—", "—"
        if PROGRESS_FILE.exists():
            try:
                d = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
                done   = str(len(d.get("done", [])))
                failed = str(len(d.get("failed", [])))
            except Exception:
                pass
        self._card_done._val.setText(done)
        self._card_failed._val.setText(failed)

    def _start(self, mode: str):
        if self._worker and self._worker.isRunning():
            return
        self._set_busy(True)
        self._log.clear()
        self._worker = DaonnaWorker(mode, self._max_spin.value(), self._skip_gemini_chk.isChecked())
        self._worker.log_signal.connect(self._append_log)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _stop(self):
        if self._worker:
            self._worker.stop()
        self._set_busy(False)

    def _on_done(self, ok: bool):
        self._set_busy(False)
        self._refresh_stats()

    def _set_busy(self, busy: bool):
        self._btn_all.setEnabled(not busy)
        self._btn_collect.setEnabled(not busy)
        self._btn_upload.setEnabled(not busy)
        self._btn_stop.setEnabled(busy)

    def _append_log(self, msg: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.append(
            f'<span style="color:#4a5568;">[{ts}]</span> {msg}')


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLE)
    win = DaonnaApp()
    win.show()
    sys.exit(app.exec_())
