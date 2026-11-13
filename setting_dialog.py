# 설정 화면 (요약 모델 / 실행 장치 / 음성 인식 설정)
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QLabel,
    QComboBox, QPushButton, QCheckBox, QSpinBox, QDoubleSpinBox,
    QFileDialog, QMessageBox,
)
from PySide6.QtGui import QIcon
from ollama_info import SystemInfoWorker, keep_alive
from app_paths import resource_path

LLM_DEVICES = [
    ("자동 (권장)", "auto"),
    ("CPU만 사용", "cpu"),
    ("GPU 우선", "gpu"),
]
LLM_DEVICE_HINTS = {
    "auto": "Ollama가 GPU(VRAM)를 자동으로 감지해 사용하고, 모자라면 일부를 CPU로 나눠 실행합니다.",
    "cpu": "GPU를 사용하지 않습니다. 느리지만 GPU 오류가 있을 때 가장 안전합니다.",
    "gpu": "가능한 모든 계층을 GPU에 올립니다. VRAM이 부족하면 오류가 나거나 오히려 느려질 수 있습니다.",
}

STT_DEVICES = [
    ("자동 (GPU 있으면 GPU)", "auto"),
    ("CPU", "cpu"),
    ("GPU (NVIDIA CUDA)", "cuda"),
]
STT_COMPUTE = [
    ("자동 (CPU: int8 / GPU: float16)", "auto"),
    ("int8 (가볍고 빠름, 정확도 약간 낮음)", "int8"),
    ("int8_float16 (GPU, VRAM 절약)", "int8_float16"),
    ("float16 (GPU, 정확도 높음)", "float16"),
]
STT_LANGS = [
    ("한국어", "ko"), ("영어", "en"), ("일본어", "ja"), ("중국어", "zh"),
    ("자동 감지", "auto"),
]
WHISPER_PRESETS = ["large-v3", "medium", "small", "base"]


def _set_combo_by_data(combo, data):
    idx = combo.findData(data)
    combo.setCurrentIndex(idx if idx >= 0 else 0)


class SettingsDlg(QDialog):

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("설정")

        icon_path = resource_path("settings_24dp.png")
        self.setWindowIcon(QIcon(str(icon_path)))

        self.setMinimumWidth(520)

        self.info = None
        self.saved_model = manager.get("llm")["model"]

        root = QVBoxLayout(self)
        root.addWidget(self._build_status_box())
        root.addWidget(self._build_llm_box())
        root.addWidget(self._build_stt_box())

        btns = QHBoxLayout()
        btns.addStretch()
        self.pb_save = QPushButton("저장")
        self.pb_cancel = QPushButton("취소")
        self.pb_save.setDefault(True)
        btns.addWidget(self.pb_save)
        btns.addWidget(self.pb_cancel)
        root.addLayout(btns)

        self.pb_save.clicked.connect(self._onSave)
        self.pb_cancel.clicked.connect(self.reject)

        self._loadValues()
        self._refresh()

    # ---------- UI 구성 ----------
    def _build_status_box(self):
        box = QGroupBox("시스템 상태")
        v = QVBoxLayout(box)
        self.lb_ollama = QLabel("Ollama 확인 중...")
        self.lb_gpu = QLabel("GPU 확인 중...")
        self.lb_loaded = QLabel("")
        for lb in (self.lb_ollama, self.lb_gpu, self.lb_loaded):
            lb.setWordWrap(True)
        self.lb_gpu.setMinimumHeight(self.lb_gpu.fontMetrics().height() * 2)
        self.pb_refresh = QPushButton("새로고침")
        self.pb_refresh.clicked.connect(self._refresh)

        v.addWidget(self.lb_ollama)
        v.addWidget(self.lb_gpu)
        v.addWidget(self.lb_loaded)
        v.addWidget(self.pb_refresh, alignment=Qt.AlignmentFlag.AlignRight)
        return box

    def _build_llm_box(self):
        box = QGroupBox("요약 모델 (Ollama)")
        form = QFormLayout(box)

        self.cb_model = QComboBox()
        self.ck_qwen = QCheckBox("qwen 모델만 표시")
        self.ck_qwen.setChecked(True)
        self.ck_qwen.toggled.connect(self._populateModels)
        row = QHBoxLayout()
        row.addWidget(self.cb_model, 1)
        row.addWidget(self.ck_qwen)
        form.addRow("모델", row)

        self.cb_llm_dev = QComboBox()
        for label, data in LLM_DEVICES:
            self.cb_llm_dev.addItem(label, data)
        self.cb_llm_dev.currentIndexChanged.connect(self._updateHints)
        form.addRow("실행 장치", self.cb_llm_dev)

        self.lb_llm_hint = QLabel()
        self.lb_llm_hint.setWordWrap(True)
        self.lb_llm_hint.setStyleSheet("color: gray;")
        self.lb_llm_hint.setMinimumHeight(self.lb_llm_hint.fontMetrics().height() * 3)
        form.addRow("", self.lb_llm_hint)

        self.sp_ctx = QSpinBox()
        self.sp_ctx.setRange(2048, 65536)
        self.sp_ctx.setSingleStep(1024)
        form.addRow("컨텍스트 길이", self.sp_ctx)

        self.sp_pred = QSpinBox()
        self.sp_pred.setRange(256, 16384)
        self.sp_pred.setSingleStep(256)
        form.addRow("최대 출력 토큰", self.sp_pred)

        self.sp_temp = QDoubleSpinBox()
        self.sp_temp.setRange(0.0, 1.0)
        self.sp_temp.setSingleStep(0.1)
        self.sp_temp.setDecimals(1)
        form.addRow("온도", self.sp_temp)

        note = QLabel("컨텍스트 길이를 늘리면 긴 상담도 처리하지만 메모리를 더 사용합니다.")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        form.addRow("", note)
        return box

    def _build_stt_box(self):
        box = QGroupBox("음성 인식 (Whisper)")
        form = QFormLayout(box)

        self.cb_stt_model = QComboBox()
        self.cb_stt_model.setEditable(True)
        self.cb_stt_model.addItems(WHISPER_PRESETS)
        self.pb_browse = QPushButton("폴더 선택...")
        self.pb_browse.clicked.connect(self._browseModel)
        row = QHBoxLayout()
        row.addWidget(self.cb_stt_model, 1)
        row.addWidget(self.pb_browse)
        form.addRow("모델", row)

        self.cb_stt_dev = QComboBox()
        for label, data in STT_DEVICES:
            self.cb_stt_dev.addItem(label, data)
        self.cb_stt_dev.currentIndexChanged.connect(self._updateHints)
        form.addRow("실행 장치", self.cb_stt_dev)

        self.cb_stt_ct = QComboBox()
        for label, data in STT_COMPUTE:
            self.cb_stt_ct.addItem(label, data)
        form.addRow("연산 방식", self.cb_stt_ct)

        self.cb_lang = QComboBox()
        for label, data in STT_LANGS:
            self.cb_lang.addItem(label, data)
        form.addRow("언어", self.cb_lang)

        self.lb_stt_hint = QLabel()
        self.lb_stt_hint.setWordWrap(True)
        self.lb_stt_hint.setStyleSheet("color: gray;")
        self.lb_stt_hint.setMinimumHeight(self.lb_stt_hint.fontMetrics().height() * 3)
        form.addRow("", self.lb_stt_hint)

        note = QLabel("음성 인식 설정을 바꾸면 저장 후 모델을 다시 불러옵니다. (수 초~수 분)")
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        form.addRow("", note)
        return box

    # ---------- 값 로드 ----------
    def _loadValues(self):
        llm = self.manager.get("llm")
        stt = self.manager.get("stt")

        _set_combo_by_data(self.cb_llm_dev, llm["device"])
        self.sp_ctx.setValue(int(llm["num_ctx"]))
        self.sp_pred.setValue(int(llm["num_predict"]))
        self.sp_temp.setValue(float(llm["temperature"]))
        self._populateModels()   # 목록이 오기 전에는 저장된 모델만 표시

        self.cb_stt_model.setCurrentText(stt["model"])
        _set_combo_by_data(self.cb_stt_dev, stt["device"])
        _set_combo_by_data(self.cb_stt_ct, stt["compute_type"])
        _set_combo_by_data(self.cb_lang, stt["language"])
        self._updateHints()

    # ---------- 시스템 정보 ----------
    def _refresh(self):
        self.pb_refresh.setEnabled(False)
        self.lb_ollama.setText("Ollama 확인 중...")
        self.lb_gpu.setText("GPU 확인 중...")
        self.lb_loaded.setText("")

        self.worker = SystemInfoWorker()
        self.worker.result.connect(self._onInfo)
        keep_alive(self.worker)
        self.worker.start()

    def _onInfo(self, info):
        self.info = info
        self.pb_refresh.setEnabled(True)

        if info["ollama_ok"]:
            self.lb_ollama.setText(
                f"● Ollama 연결됨 (설치된 모델 {len(info['models'])}개)")
            self.lb_ollama.setStyleSheet("color: green;")
        else:
            self.lb_ollama.setText(f"● {info['ollama_error']}")
            self.lb_ollama.setStyleSheet("color: red;")

        names = ", ".join(info["gpu_names"])
        if info["cuda_count"] > 0:
            self.lb_gpu.setText(f"● NVIDIA GPU 감지: {names or 'CUDA 장치 ' + str(info['cuda_count']) + '개'}")
            self.lb_gpu.setStyleSheet("color: green;")
        elif names:
            self.lb_gpu.setText(
                f"● GPU 감지: {names}\n"
                "  (단, Whisper용 CUDA를 사용할 수 없습니다. CUDA 12 / cuBLAS / cuDNN 9 설치를 확인하세요.)")
            self.lb_gpu.setStyleSheet("color: darkorange;")
        else:
            self.lb_gpu.setText("● NVIDIA GPU가 감지되지 않았습니다. Whisper는 CPU로 동작합니다.")
            self.lb_gpu.setStyleSheet("color: gray;")

        lines = []
        for m in info["running"]:
            size, vram = m["size"], m["size_vram"]
            if size > 0:
                pct = round(vram * 100 / size)
                where = "GPU" if pct >= 99 else ("CPU" if pct == 0 else f"GPU {pct}% / CPU {100 - pct}%")
                lines.append(f"• 메모리에 로드됨: {m['name']} → {where}")
            else:
                lines.append(f"• 메모리에 로드됨: {m['name']}")
        self.lb_loaded.setText("\n".join(lines))

        self._populateModels()
        self._updateHints()

    def _populateModels(self):
        # 현재 선택값(없으면 저장된 값)을 유지한 채 목록 재구성
        want = self.cb_model.currentData() if self.cb_model.count() else self.saved_model
        want = want or self.saved_model

        models = self.info["models"] if self.info else []
        qwen_only = self.ck_qwen.isChecked()

        self.cb_model.blockSignals(True)
        self.cb_model.clear()
        names = []
        for m in sorted(models, key=lambda x: x["name"]):
            if qwen_only and "qwen" not in m["name"].lower():
                continue
            gb = m["size"] / (1024 ** 3)
            self.cb_model.addItem(f"{m['name']}  ({gb:.1f} GB)", m["name"])
            names.append(m["name"])

        if want and want not in names:
            label = f"{want}  (설치 목록에 없음)" if self.info else want
            self.cb_model.addItem(label, want)
        self.cb_model.blockSignals(False)

        _set_combo_by_data(self.cb_model, want)

    def _updateHints(self):
        self.lb_llm_hint.setText(LLM_DEVICE_HINTS[self.cb_llm_dev.currentData()])

        dev = self.cb_stt_dev.currentData()
        cuda = self.info["cuda_count"] if self.info else 0
        if dev == "cpu":
            hint = "CPU로 실행합니다. large-v3는 긴 녹음에서 시간이 오래 걸릴 수 있습니다."
        elif cuda == 0 and self.info:
            hint = "CUDA GPU가 감지되지 않았습니다. 실패하면 자동으로 CPU로 전환됩니다."
        elif dev == "cuda":
            hint = "GPU 사용에는 CUDA 12와 cuBLAS, cuDNN 라이브러리가 필요합니다. 실패하면 자동으로 CPU로 전환됩니다."
        else:
            hint = "GPU가 있으면 GPU를, 없으면 CPU를 사용합니다."
        self.lb_stt_hint.setText(hint)

    def _browseModel(self):
        path = QFileDialog.getExistingDirectory(self, "Whisper 모델 폴더 선택")
        if path:
            self.cb_stt_model.setCurrentText(path)

    # ---------- 저장 ----------
    def _onSave(self):
        stt_model = self.cb_stt_model.currentText().strip()
        if not stt_model:
            QMessageBox.warning(self, "설정", "Whisper 모델을 입력하세요.")
            return

        looks_like_path = any(c in stt_model for c in ("/", "\\")) or Path(stt_model).is_absolute()
        if looks_like_path and not Path(stt_model).is_dir():
            QMessageBox.warning(self, "설정", f"Whisper 모델 폴더를 찾을 수 없습니다.\n{stt_model}")
            return

        llm_model = self.cb_model.currentData()
        if not llm_model:
            QMessageBox.warning(self, "설정", "요약 모델을 선택하세요.")
            return

        if self.info and self.info["ollama_ok"]:
            installed = {m["name"] for m in self.info["models"]}
            if llm_model not in installed:
                ans = QMessageBox.question(
                    self, "설정",
                    f"'{llm_model}' 모델이 설치되어 있지 않습니다.\n"
                    f"그래도 저장할까요?\n(설치: ollama pull {llm_model})")
                if ans != QMessageBox.StandardButton.Yes:
                    return

        self.manager.update("llm", {
            "model": llm_model,
            "device": self.cb_llm_dev.currentData(),
            "num_ctx": self.sp_ctx.value(),
            "num_predict": self.sp_pred.value(),
            "temperature": round(self.sp_temp.value(), 1),
        })
        self.manager.update("stt", {
            "model": stt_model,
            "device": self.cb_stt_dev.currentData(),
            "compute_type": self.cb_stt_ct.currentData(),
            "language": self.cb_lang.currentData(),
        })
        self.accept()