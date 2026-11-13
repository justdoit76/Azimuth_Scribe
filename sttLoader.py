from pathlib import Path
from PySide6.QtCore import QThread, Signal


class SttLoader(QThread):
    """
    faster-whisper 모델을 백그라운드에서 로딩하는 Worker

    device      : 'auto'(GPU 있으면 GPU) | 'cpu' | 'cuda'
    compute_type: 'auto' | 'int8' | 'int8_float16' | 'float16'
    GPU 로딩/실행에 실패하면 자동으로 CPU로 전환한다.
    """

    model_ready = Signal(str)   # 사용 중인 모델/장치 정보 문자열
    error = Signal(str)

    def __init__(self, model_size='large-v3', device='auto', compute_type='auto'):
        super().__init__()
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type

    @staticmethod
    def _cuda_available():
        try:
            import ctranslate2
            return ctranslate2.get_cuda_device_count() > 0
        except Exception:
            return False

    def _plans(self):
        """시도할 (device, compute_type) 목록. 앞에서부터 시도하고 실패하면 다음으로."""
        plans = []

        if self.device == 'cuda' or (self.device == 'auto' and self._cuda_available()):
            ct = 'float16' if self.compute_type == 'auto' else self.compute_type
            plans.append(('cuda', ct))

        # CPU에서는 float16 계열이 의미 없으므로 int8로 대체
        ct = self.compute_type
        if ct in ('auto', 'float16', 'int8_float16'):
            ct = 'int8'
        plans.append(('cpu', ct))
        return plans

    @staticmethod
    def _warmup(model):
        # CUDA는 로딩이 성공해도 cuBLAS/cuDNN 누락 오류가 첫 실행 때 나므로
        # 1초짜리 무음으로 미리 돌려 본다.
        import numpy as np
        audio = np.zeros(16000, dtype=np.float32)
        segments, _ = model.transcribe(audio, language='ko', beam_size=1)
        for _ in segments:
            pass

    def run(self):
        from sttWorker import SttWorker
        SttWorker._model = None   # 설정 변경 후 재로딩 시 이전 모델이 남지 않게

        try:
            # 앱 시작 시 import하지 않고 이 스레드에서 import
            from faster_whisper import WhisperModel
        except Exception as e:
            self.error.emit(str(e))
            return

        failures = []
        for dev, ct in self._plans():
            try:
                print(f'Whisper model loading... ({dev}, {ct})')
                model = WhisperModel(self.model_size, device=dev, compute_type=ct)
                if dev == 'cuda':
                    self._warmup(model)
            except Exception as e:
                print(f'Whisper {dev} failed: {e}')
                failures.append(f'{dev}/{ct}: {e}')
                continue

            SttWorker._model = model
            name = Path(self.model_size).name or self.model_size
            info = f'{name} · {dev.upper()} ({ct})'
            if failures:
                info += ' · GPU 실패 → CPU로 전환'
            print('Whisper model ready')
            self.model_ready.emit(info)
            return

        self.error.emit('\n'.join(failures))