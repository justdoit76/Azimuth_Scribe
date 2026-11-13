from html import escape

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QTextBrowser,
    QPushButton,
    QHBoxLayout,
)

# (이름, 라이선스, 링크, 비고)
# 배포 전에 `pip-licenses --with-urls` 등으로 실제 설치된 패키지(하위 의존성 포함)와 대조하세요.
# MIT/BSD/Apache 라이선스는 배포물에 저작권 고지와 라이선스 전문을 함께 넣어야 하므로,
# 링크만 두지 말고 THIRD_PARTY_LICENSES 같은 파일로 전문을 같이 배포하는 것을 권장합니다.
COMPONENTS = [
    ("faster-whisper", "MIT",
     "https://github.com/SYSTRAN/faster-whisper", "음성 인식 엔진"),
    ("CTranslate2", "MIT",
     "https://github.com/OpenNMT/CTranslate2", "faster-whisper가 사용하는 추론 엔진"),
    ("OpenAI Whisper (model weights)", "MIT",
     "https://github.com/openai/whisper", "음성 인식 모델"),
    ("PyAV", "BSD-3-Clause",
     "https://github.com/PyAV-Org/PyAV", "오디오 파일 디코딩 / 길이 확인"),
    ("FFmpeg", "LGPL-2.1+ / GPL (빌드에 따라 다름)",
     "https://ffmpeg.org/legal.html", "PyAV 배포본에 포함된 라이브러리"),
    ("NumPy", "BSD-3-Clause",
     "https://numpy.org", ""),
    # ("SciPy", "BSD-3-Clause",
    #  "https://scipy.org", "WAV 파일 저장"),
    ("python-sounddevice", "MIT",
     "https://github.com/spatialaudio/python-sounddevice", "마이크 녹음"),
    ("PortAudio", "MIT 계열",
     "http://www.portaudio.com", "sounddevice에 포함"),
    ("Requests", "Apache-2.0",
     "https://github.com/psf/requests", "Ollama와 통신"),
]

# 앱에 포함되지 않고 사용자가 따로 설치해서 쓰는 구성요소
EXTERNAL = [
    ("Ollama", "MIT",
     "https://github.com/ollama/ollama", "로컬 LLM 실행 환경 (별도 설치)"),
    ("Qwen3 models", "Apache-2.0 (모델마다 다를 수 있음)",
     "https://github.com/QwenLM/Qwen3", "요약 모델 (별도 다운로드, 사용하는 모델의 라이선스를 확인하세요)"),
]


def _rows(items):
    out = []
    for name, lic, url, note in items:
        out.append(
            "<tr>"
            f"<td><b>{escape(name)}</b></td>"
            f"<td>{escape(lic)}</td>"
            f'<td><a href="{escape(url)}">{escape(url)}</a></td>'
            f"<td>{escape(note)}</td>"
            "</tr>"
        )
    return "\n".join(out)


def _build_html():
    head = "<tr><th>Component</th><th>License</th><th>Link</th><th>Note</th></tr>"
    return f"""
    <html>
    <head>
        <style>
            body {{ font-size: 10pt; }}
            a {{ color: #268bd2; text-decoration: underline; }}
            p {{ margin-bottom: 12px; }}
            td, th {{ padding: 4px; }}
        </style>
    </head>
    <body>
        <h3>PySide6 (Qt for Python)</h3>

        <p>
        This application uses
        <b>PySide6 (Qt for Python)</b>, which is distributed under
        the GNU Lesser General Public License (LGPL) and other
        applicable licenses.
        </p>

        <p>
        PySide6 and the relevant Qt components are subject to their
        respective copyright notices and license terms.
        </p>

        <p>
        A copy of the applicable license terms and information about
        obtaining the corresponding source code should be provided
        with this distribution, as required by the applicable licenses.
        </p>

        <p>
            <a href="https://doc.qt.io/qtforpython/">Qt for Python Documentation</a><br>
            <a href="https://www.gnu.org/licenses/lgpl-3.0.html">GNU Lesser General Public License v3.0</a><br>
            <a href="https://www.qt.io/development/open-source-lgpl-obligations">Qt LGPL Compliance Information</a>
        </p>

        <hr>

        <h3>Other open-source components</h3>
        <p>
        This application also uses the following open-source software.
        Each component is subject to its own copyright notice and license terms.
        </p>
        <table border="1" cellspacing="0">
            {head}
            {_rows(COMPONENTS)}
        </table>

        <h4>Used separately (not included in this application)</h4>
        <table border="1" cellspacing="0">
            {head}
            {_rows(EXTERNAL)}
        </table>

        <hr>

        <p>
        The source code of this application is released under the MIT License.
        </p>
    </body>
    </html>
    """


class ThirdParty_Notice_Dlg(QDialog):
    """Third-party software license notices."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Third-Party Software Notices")
        self.setMinimumSize(520, 400)
        self.resize(760, 560)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        # 제목
        title = QLabel("Third-Party Software Notices")
        title.setStyleSheet("""
            QLabel {
                font-size: 17px;
                font-weight: bold;
            }
        """)
        layout.addWidget(title)

        # 라이선스 고지 내용
        self.notice_view = QTextBrowser(self)
        self.notice_view.setOpenExternalLinks(False)
        self.notice_view.setOpenLinks(False)
        self.notice_view.setStyleSheet("""
            QTextBrowser {
                background-color: palette(base);
                color: palette(text);
                border: 1px solid palette(mid);
                padding: 8px;
            }
        """)

        self.notice_view.setHtml(_build_html())

        # 링크 클릭 시 외부 브라우저로 열기
        self.notice_view.anchorClicked.connect(self._open_url)

        layout.addWidget(self.notice_view)

        # 하단 버튼
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.close_button = QPushButton("닫기")
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.accept)

        button_layout.addWidget(self.close_button)
        layout.addLayout(button_layout)

    @staticmethod
    def _open_url(url: QUrl):
        if url.isValid():
            QDesktopServices.openUrl(url)