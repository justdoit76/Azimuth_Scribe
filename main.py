from PySide6.QtWidgets import (QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
                               QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QProgressBar, 
                               QFileDialog, QMessageBox, QHeaderView, QComboBox, QDialog)        
from PySide6.QtCore import Qt, QTimer, QUrl     
from PySide6.QtGui import QTextCursor, QAction, QIcon, QDesktopServices            
import sys
import re
import datetime as dt
from pathlib import Path
from audioRecorder import AudioRecorder
from sttWorker import SttWorker
from sttLoader import SttLoader
 
from llmWorker import LLMWorker
from prompt_manager import PromptManager
from setting_manager import SettingsManager
from setting_dialog import SettingsDlg
from license_dialog import ThirdParty_Notice_Dlg
from ollama_info import OllamaUnloadWorker, keep_alive
from app_paths import recordings_dir, results_dir, resource_path
 
class Window(QMainWindow):
 
    APP_TITLE = 'Azimuth Scribe'
    VERSION = '1.0.0'
    RESULT_DIR = 'Results'
    STT_STATUS = ('Pending', 'Processing', 'Completed', 'Error')
 
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'{Window.APP_TITLE} {Window.VERSION}')
        self.resize(640,480)
 
        self.prom_manager = PromptManager()
        self.settings = SettingsManager()
        self.llm_worker = None
        self.stt_worker = None
        self.recorder = None
        self._llm_warnings = []
        self._stt_cancel = False
 
        self.stt_queue = []        
        self.stt_total = 0
        # 설정 화면은 모델 로딩/STT/요약 중에는 열 수 없다
        self._model_loading = False
        self._stt_busy = False
        self._llm_busy = False
        # idx:현재 stt 순서
        # row:현재 stt 테이블위젯 행 (사운드파일을 모두 선택하지 않을 수도 있기 때문)
        self.stt_curridx = 0
        self.stt_currrow = -1        
 
        self.initUi()
 
        self.pb_rec.setCheckable(True)
 
        # signal
        self.pb_rec.clicked.connect(self.onRecord)
        self.pb_stt.clicked.connect(self.onSTT)
        self.pb_add.clicked.connect(self.onAddSound)
        self.pb_del.clicked.connect(self.onDelSound)
        self.pb_clear.clicked.connect(self.onClear)
        self.pb_summary.clicked.connect(self.onSummary)
        self.pb_copy.clicked.connect(self.onCopy)
        self.pb_save_stt.clicked.connect(self.onSaveStt)
        self.pb_save_summary.clicked.connect(self.onSaveSummary)
 
        self.pb_stt.setEnabled(False)
        self.pb_stt.setText('STT model loading...')
        self.pbar.show()
 
        self.stt_loader = None
        self._model_loading = True
        self._updateSettingsEnabled()
 
        QTimer.singleShot(0, self._startSttLoader)
        # Window.__init__()
        # ↓
        # w.show()
        # ↓
        # 화면 표시 준비
        # ↓
        # Qt 이벤트 루프
        # ↓
        # singleShot(0)
        # ↓
        # stt_loader.start()
        # ↓
        # SttLoader.run()
        # ↓
        # faster_whisper 로딩
 
    def initUi(self):
        # 전체 컨테이너
        widget = QWidget()
 
        # 전체 레이아웃
        hbox = QHBoxLayout()

        vbox = QVBoxLayout() 
        vbox.addWidget(self.initBox1())
        vbox.addWidget(self.initBox2())
        vbox.addWidget(self.initBox3())

        hbox.addLayout(vbox)
        hbox.addWidget(self.initBox4())    
 
        widget.setLayout(hbox)
        self.setCentralWidget(widget)
 
        self.initStatusBar(label='STT model loading...')
        self.initMenu()
 
    def initMenu(self):
        menubar = self.menuBar()
        menu0 = menubar.addMenu('File')
        menu1 = menubar.addMenu('Settings')
        menu2 = menubar.addMenu('Third-Party Licenses')

        self.act_settings = QAction('Preferences', self)
        self.act_settings.setShortcut('Ctrl+p,')

        self.act_license = QAction('License notice', self)
        self.act_license.setShortcut('Ctrl+n,')

        self.act_settings.triggered.connect(self.onSettings)
        self.act_license.triggered.connect(self.onLicense)

        menu1.addAction(self.act_settings)
        menu2.addAction(self.act_license)

        act_save_stt = QAction('Save STT text...', self)
        act_save_sum = QAction('Save summary...', self)
        act_open_res = QAction('Open Results folder', self)
        act_open_rec = QAction('Open Recordings folder', self)
        act_save_stt.triggered.connect(self.onSaveStt)
        act_save_sum.triggered.connect(self.onSaveSummary)
        act_open_res.triggered.connect(lambda: self._openFolder(results_dir()))
        act_open_rec.triggered.connect(lambda: self._openFolder(recordings_dir()))
        menu0.addAction(act_save_stt)
        menu0.addAction(act_save_sum)
        menu0.addSeparator()
        menu0.addAction(act_open_res)
        menu0.addAction(act_open_rec)
 
    def initBox1(self):
        # STEP 1
        gbox1 = QGroupBox('STEP 1 : Record')
        self.lb_rec = QLabel('Ready')
        self.pb_rec = QPushButton('Start record')
 
        hbox = QHBoxLayout()
        hbox.addWidget(self.lb_rec)
        hbox.addWidget(self.pb_rec)
        gbox1.setLayout(hbox)
        return gbox1
 
    def initBox2(self):
        # STEP 2
        gbox2 = QGroupBox('STEP 2 : Record Files')
        self.tw = QTableWidget()
        hlabel = ('select', 'file name', 'duration', 'status')
        self.tw.setColumnCount(len(hlabel))
        self.tw.setHorizontalHeaderLabels(hlabel)
 
        header = self.tw.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
 
        self.pb_stt = QPushButton('STT')      
        self.pb_add = QPushButton('Add') 
        self.pb_del = QPushButton('Delete')
        hbox = QHBoxLayout()
        hbox.addWidget(self.pb_stt)     
        hbox.addWidget(self.pb_add)   
        hbox.addWidget(self.pb_del)
 
        vbox = QVBoxLayout()
        vbox.addLayout(hbox)
        vbox.addWidget(self.tw)        
        gbox2.setLayout(vbox)
        return gbox2
 
    def initBox3(self):
        # STEP 3, STT result
        gbox3 = QGroupBox('STEP 3 : STT result')
        self.pb_clear = QPushButton('Clear')
        hbox = QHBoxLayout()
        self.pb_save_stt = QPushButton('Save...')
        hbox.addWidget(self.pb_clear)
        hbox.addWidget(self.pb_save_stt)
        self.te = QTextEdit()
        vbox = QVBoxLayout()
        vbox.addWidget(self.te)
        vbox.addLayout(hbox)
        gbox3.setLayout(vbox)
        return gbox3
 
    def initBox4(self):                
        gbox4 = QGroupBox('STEP 4 : Local LLM Summary')
 
        self.cb_prompt = QComboBox()
        prom_names = self.prom_manager.names()
        self.cb_prompt.addItems(prom_names)
 
        self.pb_summary = QPushButton('Summary')
        self.pb_copy = QPushButton('Copy to Clipboard')
 
        self.te_summary = QTextEdit()
        self.te_summary.setPlaceholderText('Local LLM summary result...')
 
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel('Prompt:'))
        hbox.addWidget(self.cb_prompt)
        hbox.addWidget(self.pb_summary)
        hbox.addWidget(self.pb_copy)
 
        self.lb_llm_info = QLabel()
        self.lb_llm_info.setStyleSheet('color: gray;')
        self._updateLlmInfo()
 
        vbox = QVBoxLayout()
        vbox.addLayout(hbox)
        vbox.addWidget(self.lb_llm_info)
        vbox.addWidget(self.te_summary)

        self.pb_save_summary = QPushButton('Save...')
        hbox_save = QHBoxLayout()
        hbox_save.addStretch()
        hbox_save.addWidget(self.pb_save_summary)
        vbox.addLayout(hbox_save)
 
        gbox4.setLayout(vbox)
 
        return gbox4
    
 
    def initStatusBar(self, label='', _min=0, _max=0, width=100):
        self.status = QWidget()
        hbox = QHBoxLayout(self.status)
        hbox.setContentsMargins(0, 0, 0, 0)
 
        self.label = QLabel(label)
        self.pbar = QProgressBar()
        self.pbar.setFixedWidth(width)
        self.pbar.setRange(_min, _max)
 
        hbox.addWidget(self.label)
        hbox.addWidget(self.pbar)
        self.statusBar().addPermanentWidget(self.status)
 
    def setStatusBar(self, show_label=True, show_pbar=True, label='', _min=None, _max=None, value=None):      
        if show_label:
            self.label.show()
            self.label.setText(label)
        else:
            self.label.hide()
 
        if show_pbar:
            self.pbar.show()
            if _min is not None and _max is not None:
                self.pbar.setRange(_min, _max)
 
            if value is not None:
                self.pbar.setValue(value)
        else:
            self.pbar.hide()
        
    def onSettings(self, *_):        
        old = self.settings.snapshot()
 
        dlg = SettingsDlg(self.settings, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
 
        new = self.settings.snapshot()
        self._updateLlmInfo()
 
        # 모델/장치가 바뀌면 이전 설정으로 올라간 모델을 메모리에서 내림
        if old['llm']['model'] != new['llm']['model'] or old['llm']['device'] != new['llm']['device']:
            w = OllamaUnloadWorker(old['llm']['model'])
            keep_alive(w)
            w.start()
 
        # Whisper 설정이 바뀌면 모델 재로딩
        if old['stt'] != new['stt']:
            self._startSttLoader()
        else:
            self.setStatusBar(show_label=True, show_pbar=False, label='Settings saved.')

    def onLicense(self):
        dlg = ThirdParty_Notice_Dlg(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        
    def _startSttLoader(self):
        cfg = self.settings.get('stt')
 
        self._model_loading = True
        self._updateSettingsEnabled()
        self.pb_stt.setEnabled(False)
        self.pb_stt.setText('STT model loading...')
        self.setStatusBar(show_label=True, show_pbar=True,
                          label='STT model loading...', _min=0, _max=0)
 
        self.stt_loader = SttLoader(
            model_size=cfg['model'],
            device=cfg['device'],
            compute_type=cfg['compute_type']
        )
        self.stt_loader.model_ready.connect(self.onSttModelReady)
        self.stt_loader.error.connect(self.onSttModelError)
        keep_alive(self.stt_loader)
        self.stt_loader.start()
 
    def onSttModelReady(self, info):
        self._model_loading = False
        self._updateSettingsEnabled()
        self.pb_stt.setEnabled(True)
        self.pb_stt.setText('STT')
        self.setStatusBar(show_pbar=False, label=f'STT model ready. [{info}]')
 
    def onSttModelError(self, msg):
        self._model_loading = False
        self._updateSettingsEnabled()
        self.pb_stt.setEnabled(False)
        self.pb_stt.setText('STT model error')
        self.setStatusBar(show_pbar=False,
                          label=f'STT model loading error! (Settings에서 변경 가능) : {msg}')
 
    # ---------- 설정 ----------
    def _updateSettingsEnabled(self):
        busy = self._model_loading or self._stt_busy or self._llm_busy
        self.act_settings.setEnabled(not busy)
 
    def _updateLlmInfo(self):
        cfg = self.settings.get('llm')
        dev = {'auto': 'Auto', 'cpu': 'CPU', 'gpu': 'GPU'}.get(cfg['device'], cfg['device'])
        self.lb_llm_info.setText(f"Model: {cfg['model']}  ·  Device: {dev}")
 
    
    def onRecord(self):
        if self.pb_rec.isChecked():
            file_path = self._newRecordingPath()

            self.recorder = AudioRecorder(name=str(file_path))
            self.recorder.done.connect(self.onRecFinished)
            self.recorder.error.connect(self.onRecError)
            keep_alive(self.recorder)

            self.lb_rec.setText('Recording...')
            self.pb_rec.setText('Stop record')
            self.recorder.start()
        else:
            if self.recorder and self.recorder.isRunning():
                # 파일 저장이 끝날 때까지 새 녹음을 시작하지 못하게 막는다
                self.pb_rec.setEnabled(False)
                self.pb_rec.setText('Saving...')
                self.lb_rec.setText('Saving...')
                self.recorder.stop()
            else:
                self._resetRecUi()

    def _resetRecUi(self):
        self.pb_rec.setChecked(False)
        self.pb_rec.setEnabled(True)
        self.pb_rec.setText('Start record')
        self.lb_rec.setText('Ready')

    def _newRecordingPath(self):
        # 같은 초에 다시 녹음해도 기존 파일을 덮어쓰지 않도록 번호를 붙인다
        base = recordings_dir()
        stem = self.getDateTime()
        path = base / f'{stem}.wav'
        n = 1
        while path.exists():
            path = base / f'{stem}_{n}.wav'
            n += 1
        return path.resolve()

    def getDateTime(self):
        now = dt.datetime.now()
        return now.strftime('%Y-%m-%d_%H-%M-%S')    
 
    def onRecFinished(self, file_path):
        print(f"recorded : {file_path}")
        self._resetRecUi()
        self._addSoundFile(file_path)

    def onRecError(self, msg):
        self._resetRecUi()
        self.setStatusBar(show_label=True, show_pbar=False, label='Recording error.')
        QMessageBox.critical(self, 'Recording Error', msg, QMessageBox.StandardButton.Ok)

    def onSTT(self):
        # STT 진행 중에는 이 버튼이 'Stop' 역할을 한다
        if self._stt_busy:
            self.cancelStt()
            return

        # 체크된 파일들 큐에 담기
        self.stt_queue = []
        for i in range(self.tw.rowCount()):
            item_chk = self.tw.item(i, 0)
            item_name = self.tw.item(i, 1)
            if item_chk.checkState() == Qt.CheckState.Checked:
                file_path = item_name.data(Qt.ItemDataRole.UserRole)
                self.stt_queue.append((i, file_path))

        if not self.stt_queue:
            QMessageBox.critical(self, 'Error', 'No file selected.', QMessageBox.StandardButton.Ok)
            return

        self.stt_total = len(self.stt_queue)
        self.stt_curridx = 0
        self._stt_cancel = False

        self._setSttBusy(True)
        self._processNextStt()

    def _setSttBusy(self, busy):
        self._stt_busy = busy
        self._updateSettingsEnabled()
        # 진행 중에는 STT 버튼을 'Stop'으로 쓴다 (취소 요청 후에는 cancelStt()가 잠시 비활성화)
        self.pb_stt.setEnabled(True)
        self.pb_stt.setText('Stop' if busy else 'STT')
        self.pb_add.setEnabled(not busy)
        self.pb_del.setEnabled(not busy)

    def cancelStt(self):
        if not (self.stt_worker and self.stt_worker.isRunning()):
            return

        self._stt_cancel = True
        self.stt_queue.clear()              # 남은 파일은 Pending 상태로 남는다
        self.pb_stt.setEnabled(False)
        self.pb_stt.setText('Stopping...')
        self.setStatusBar(show_label=True, show_pbar=True,
                          label='STT stopping... (현재 구간 처리 후 중단됩니다)',
                          _min=0, _max=0)
        self.stt_worker.cancel()

    def onSttCancelled(self, file_name):
        # 중단된 파일은 결과가 없으므로 Pending으로 되돌린다
        item = self.tw.item(self.stt_currrow, 3)
        if item:
            item.setText(Window.STT_STATUS[0])
        self._processNextStt()      # 큐가 비어 있으므로 마무리만 수행

    def _processNextStt(self):
        if not self.stt_queue:
            self._setSttBusy(False)
            self.setStatusBar(show_label=True,show_pbar=False, label='STT cancelled.' if self._stt_cancel else 'STT completed.')
            errs = getattr(self, '_stt_errors', [])
            self._stt_errors = []
            if errs:
                QMessageBox.critical(self, 'STT Error', '\n\n'.join(errs), QMessageBox.StandardButton.Ok)
            return
 
        self.stt_curridx+=1
        row, file_path = self.stt_queue.pop(0)      
        self.stt_currrow = row
 
        self.tw.item(row, 3).setText(Window.STT_STATUS[1])
 
        file_name = Path(file_path).name  
        self.setStatusBar(
        show_label=True,
        show_pbar=False,
        label=f'[{file_name}] processing... '
              f'({self.stt_curridx}/{self.stt_total})'
        )
 
        lang = self.settings.get('stt')['language']
        self.stt_worker = SttWorker(file_path, language=None if lang == 'auto' else lang)
        self.stt_worker.done.connect(self.onSttFinished)
        self.stt_worker.error.connect(self.onSttError)
        self.stt_worker.cancelled.connect(self.onSttCancelled)
        keep_alive(self.stt_worker)
        self.stt_worker.start()
 
    def onSttFinished(self, file_name, text):        
        self.setStatusBar(show_label=True, show_pbar=False, label=f'[{file_name}]')
        self.tw.item(self.stt_currrow, 3).setText(Window.STT_STATUS[2]) 
        self.te.append(f'{text}\n')
        self._processNextStt()  # 다음 파일 처리
 
    def onSttError(self, file_name, msg):
        self.tw.item(self.stt_currrow, 3).setText(Window.STT_STATUS[3])
        self.setStatusBar(show_label=True, show_pbar=False, label=f'[{file_name}] 오류: {msg}')
        if not hasattr(self, '_stt_errors'):
            self._stt_errors = []
        self._stt_errors.append(f'{file_name}\n{msg}')
        self._processNextStt()
 
    def onAddSound(self):
        files, _ = QFileDialog.getOpenFileNames(self, '', '', 'Sound Files(*.wav *.mp3 *.m4a *.flac *.ogg *.aac)')
        for path in files:
            self._addSoundFile(path)
 
    def onDelSound(self):
        cnt = self.tw.rowCount()
        for i in range(cnt-1, -1, -1):
            item = self.tw.item(i, 0)
            if item.checkState() == Qt.CheckState.Checked:
                self.tw.removeRow(i)
 
    def _getDuration(self, file_path):
        try:
            # faster-whisper가 이미 의존하는 PyAV(BSD)로 길이를 읽는다. (mutagen은 GPL이라 제거)
            import av

            with av.open(file_path) as container:
                if container.duration is not None:
                    sec = container.duration / av.time_base      # 마이크로초 -> 초
                else:
                    stream = container.streams.audio[0]
                    if stream.duration is None:
                        return '-'
                    sec = float(stream.duration * stream.time_base)

            sec = int(sec)
            return f'{sec // 60:02d}:{sec % 60:02d}'

        except Exception:
            return '-'

    def _addSoundFile(self, file_path):
        file_path = str(Path(file_path).resolve())
        file_name = Path(file_path).name
 
        row = self.tw.rowCount()
        self.tw.setRowCount(row + 1)
 
        item_chk = QTableWidgetItem()
        item_chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        item_chk.setCheckState(Qt.CheckState.Checked)
 
        item_name = QTableWidgetItem(file_name)
 
        # 실제 절대경로 저장
        item_name.setData(Qt.ItemDataRole.UserRole, file_path)
 
        duration = self._getDuration(file_path)
        item_dur = QTableWidgetItem(duration)
 
        self.tw.setItem(row, 0, item_chk)
        self.tw.setItem(row, 1, item_name)
        self.tw.setItem(row, 2, item_dur)
        self.tw.setItem(row, 3, QTableWidgetItem(Window.STT_STATUS[0]))
 
    def onClear(self):
        self.te.clear()
 
    def onSummary(self):
        text = self.te.toPlainText().strip()

        if not text:
            QMessageBox.critical(self, 'Error', 'No STT result.', QMessageBox.StandardButton.Ok)
            return

        # 요약 진행 중에는 이 버튼이 'Stop' 역할을 한다
        if self._llm_busy:
            self.cancelLlm()
            return

        if self.llm_worker and self.llm_worker.isRunning():
            return

        prom_name = self.cb_prompt.currentText()
        prompt = self.prom_manager.get(prom_name)

        # 입력이 컨텍스트 길이에 들어가는지 먼저 확인 (넘치면 앞부분=작성 지시가 조용히 잘림)
        llm_cfg = self._checkLlmContext(text, prompt, self.settings.get('llm'))
        if llm_cfg is None:
            return  # 사용자가 취소 / 너무 김

        self._llm_warnings = []
        self._setLlmBusy(True)
        self.te_summary.clear()

        # 최소=최대=0 이면 진행률이 무한(busy) 표시로 동작
        self.setStatusBar(
            show_label=True,
            show_pbar=True,
            label=f"[{prom_name}] LLM summarizing... ({llm_cfg['model']})",
            _min=0,
            _max=0
        )

        self.llm_worker = LLMWorker(text, prompt, settings=llm_cfg)
        self.llm_worker.progress.connect(self.onLlmProgress)
        self.llm_worker.warning.connect(self.onLlmWarning)
        self.llm_worker.done.connect(self.onLlmFinished)
        self.llm_worker.error.connect(self.onLlmError)
        self.llm_worker.cancelled.connect(self.onLlmCancelled)
        keep_alive(self.llm_worker)
        self.llm_worker.start()

    def _checkLlmContext(self, text, prompt, cfg):
        """진행 가능하면 (필요 시 num_ctx를 이번 한 번만 늘린) 설정 dict, 취소/불가면 None"""
        plan = LLMWorker.plan_context(text, prompt, cfg['num_ctx'], cfg['num_predict'])
        if plan['fits']:
            return cfg

        if plan['too_long']:
            QMessageBox.critical(
                self, 'Text too long',
                f"텍스트가 너무 깁니다. (추정 약 {plan['needed']:,}토큰, "
                f"처리 가능 최대 약 {LLMWorker.CTX_HARD_CAP:,}토큰)\n\n"
                "녹음 파일별로 나누어 요약하거나, 텍스트를 일부씩 잘라 요약해 주세요.",
                QMessageBox.StandardButton.Ok)
            return None

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle('컨텍스트 길이 초과 가능')
        box.setText(
            f"입력이 현재 컨텍스트 길이({cfg['num_ctx']:,})를 넘을 수 있습니다.\n"
            f"(추정: 입력 약 {plan['prompt_tokens']:,}토큰 + 출력 여유)\n\n"
            "그대로 실행하면 작성 지시가 담긴 앞부분이 잘려 엉뚱한 결과가 나올 수 있습니다.\n"
            f"이번 한 번만 컨텍스트 길이를 {plan['suggested']:,}로 늘려 실행할까요?\n"
            "(메모리 사용량이 늘고, 모델을 다시 불러오느라 첫 응답이 느려질 수 있습니다.)"
        )
        btn_expand = box.addButton('늘려서 실행', QMessageBox.ButtonRole.AcceptRole)
        btn_asis = box.addButton('그대로 실행', QMessageBox.ButtonRole.DestructiveRole)
        box.addButton('취소', QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_expand)
        box.exec()

        clicked = box.clickedButton()
        if clicked is btn_expand:
            cfg['num_ctx'] = plan['suggested']   # cfg는 복사본이라 저장된 설정은 바뀌지 않는다
            return cfg
        if clicked is btn_asis:
            return cfg
        return None

    def _setLlmBusy(self, busy):
        self._llm_busy = busy
        self._updateSettingsEnabled()
        # 진행 중에는 Summary 버튼을 'Stop'으로 쓴다
        self.pb_summary.setEnabled(True)
        self.pb_summary.setText('Stop' if busy else 'Summary')
        self.cb_prompt.setEnabled(not busy)

    def cancelLlm(self):
        if not (self.llm_worker and self.llm_worker.isRunning()):
            return

        self.pb_summary.setEnabled(False)
        self.pb_summary.setText('Stopping...')
        self.setStatusBar(show_label=True, show_pbar=True, label='LLM stopping...',
                          _min=0, _max=0)
        self.llm_worker.cancel()

    def onLlmCancelled(self):
        # 이미 생성된 부분 결과는 요약창에 그대로 남겨 둔다
        self._setLlmBusy(False)
        self.setStatusBar(show_label=True, show_pbar=False, label='Summary cancelled.')

    def onLlmProgress(self, piece):
        # 생성되는 토큰을 요약창 끝에 이어붙여 진행 상황을 보여줌
        self.te_summary.moveCursor(QTextCursor.MoveOperation.End)
        self.te_summary.insertPlainText(piece)
 
    def onLlmFinished(self, result):
        self.te_summary.setPlainText(result)
        self._setLlmBusy(False)

        if self._llm_warnings:
            self.setStatusBar(show_label=True, show_pbar=False, label='Summary completed (경고 있음).')
            QMessageBox.warning(self, 'Summary warning',
                                '\n\n'.join(self._llm_warnings),
                                QMessageBox.StandardButton.Ok)
        else:
            self.setStatusBar(show_label=True, show_pbar=False, label='Summary completed.')

    def onLlmWarning(self, msg):
        self._llm_warnings.append(msg)

    def onLlmError(self, msg):
        self._setLlmBusy(False)
        self.setStatusBar(show_label=True, show_pbar=False, label='Summary error.')
        QMessageBox.critical(self, 'LLM Error', msg, QMessageBox.StandardButton.Ok)
 
    def onCopy(self):
        text = self.te_summary.toPlainText()
        if not text:
            return

        QApplication.clipboard().setText(text)
        self.setStatusBar(show_label=True, show_pbar=False, label='Copied to clipboard.')

    # ---------- 결과 저장 ----------
    def onSaveStt(self):
        self._saveText(self.te.toPlainText(), 'stt')

    def onSaveSummary(self):
        name = re.sub(r'[\\/:*?"<>|\s]+', '_', self.cb_prompt.currentText()).strip('_')
        self._saveText(self.te_summary.toPlainText(), f'summary_{name}' if name else 'summary')

    def _saveText(self, text, stem):
        if not text.strip():
            QMessageBox.information(self, 'Save', '저장할 내용이 없습니다.', QMessageBox.StandardButton.Ok)
            return

        default = results_dir() / f'{self.getDateTime()}_{stem}.txt'
        path, selected = QFileDialog.getSaveFileName(
            self, 'Save', str(default), 'Text (*.txt);;Markdown (*.md)')
        if not path:
            return

        p = Path(path)
        if not p.suffix:
            p = p.with_suffix('.md' if '*.md' in selected else '.txt')

        try:
            p.write_text(text, encoding='utf-8')
        except OSError as e:
            QMessageBox.critical(self, 'Save Error', f'파일을 저장하지 못했습니다.\n{e}',
                                 QMessageBox.StandardButton.Ok)
            return

        self.setStatusBar(show_label=True, show_pbar=False, label=f'Saved: {p}')

    def _openFolder(self, folder):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def closeEvent(self, e):
        if self.recorder and self.recorder.isRunning():
            self.recorder.stop()
            self.recorder.wait()

        # 진행 중인 작업은 취소를 요청하고 일정 시간만 기다린다.
        # (끝까지 기다리면 요약/STT가 끝날 때까지 창이 멈춘 것처럼 보인다)
        for t in (self.llm_worker, self.stt_worker, self.stt_loader):
            self._stopThread(t)

        e.accept()

    @staticmethod
    def _stopThread(t, timeout=10000):
        if not t or not t.isRunning():
            return
        if hasattr(t, 'cancel'):
            t.cancel()
        if not t.wait(timeout):     # 취소가 안 먹는 작업(모델 로딩 등)은 종료 시에만 강제 종료
            t.terminate()
            t.wait()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    import ctypes


    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID( Window.APP_TITLE )

    icon_path = resource_path("Azimuth_logo.png")
    app.setWindowIcon(QIcon(str(icon_path)))

    w = Window()
    w.show()
    sys.exit(app.exec())