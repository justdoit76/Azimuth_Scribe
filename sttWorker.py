# sttWorker.py
import threading

from PySide6.QtCore import QThread, Signal

class SttWorker(QThread):

    done = Signal(str, str)
    error = Signal(str, str)
    cancelled = Signal(str)        # 사용자가 중단하면 파일 경로 전달 (이 경우 done/error는 나가지 않음)
    progress = Signal(str, str)

    _model = None

    def __init__(self, file_name, language='ko'):
        super().__init__()

        self.file_name = file_name
        self.language = language
        self._cancel = threading.Event()

    def cancel(self):
        """중단 요청. faster-whisper는 구간(segment, 최대 약 30초 분량) 단위로
        결과를 내놓으므로, 현재 구간 처리가 끝나는 시점에 멈춘다."""
        self._cancel.set()

    def run(self):
        try:
            if SttWorker._model is None:
                raise RuntimeError(
                    'STT 모델이 준비되지 않았습니다.'
                )

            if self._cancel.is_set():
                self.cancelled.emit(self.file_name)
                return

            segments, info = SttWorker._model.transcribe(
                self.file_name,
                language=self.language,
                beam_size=5
            )

            text_parts = []

            for segment in segments:
                if self._cancel.is_set():
                    # 중간 결과는 버린다 (일부만 들어간 텍스트가 섞이는 것 방지)
                    self.cancelled.emit(self.file_name)
                    return
                text_parts.append(segment.text)

            text = ''.join(text_parts).strip()

            self.done.emit(
                self.file_name,
                text
            )

        except Exception as e:                    
            import traceback
            traceback.print_exc()
            self.error.emit(self.file_name, str(e))