import os
import threading

import sounddevice as sd
import numpy as np
#from scipy.io.wavfile import write
import wave
from PySide6.QtCore import QThread, Signal


class AudioRecorder(QThread):
    done = Signal(str)    # 녹음이 정상 저장되면 파일 경로 전달
    error = Signal(str)   # 장치 오류 / 빈 녹음 / 저장 실패 시 메시지 전달

    def __init__(self, name="recording.wav", rate=16000):
        super().__init__()
        self.file_name = name
        self.sample_rate = rate
        self.frames = []
        # start() 전에 stop()이 호출돼도 안전하도록 Event 사용
        # (예전에는 run() 안에서 isRec=True로 덮어써서, 시작 직후 Stop이 무시될 수 있었음)
        self._stop_event = threading.Event()

    def run(self):
        self.frames = []
        interrupted = False

        def callback(indata, frame_count, time_info, status):
            self.frames.append(indata.copy())

        try:
            # mono 채널, 16kHz가 STT에 적합 (Whisper 계열은 16kHz 기준)
            with sd.InputStream(samplerate=self.sample_rate, channels=1,
                                dtype="int16", callback=callback) as stream:
                # stop()이 호출되면 wait()가 True를 반환하며 루프 종료
                while not self._stop_event.wait(0.1):
                    if not stream.active:      # 녹음 중 마이크가 분리된 경우 등
                        interrupted = True
                        break
        except Exception as e:
            self.error.emit(
                "녹음 장치를 열 수 없거나 녹음 중 오류가 발생했습니다.\n"
                "마이크 연결과 운영체제의 마이크 권한을 확인하세요.\n\n"
                f"{e}"
            )
            return

        if not self.frames:
            self.error.emit("녹음된 데이터가 없습니다. 마이크 연결과 권한을 확인하세요.")
            return

        try:
            audio_data = np.concatenate(self.frames, axis=0)
            os.makedirs(os.path.dirname(self.file_name) or ".", exist_ok=True)
            with wave.open(self.file_name, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)              # int16
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_data.tobytes())
        except Exception as e:
            self.error.emit(f"녹음 파일을 저장하지 못했습니다.\n{e}")
            return

        self.done.emit(self.file_name)

        if interrupted:
            self.error.emit("녹음 장치 연결이 끊겨 녹음이 중단되었습니다.\n여기까지의 내용은 저장했습니다.")

    def stop(self):
        self._stop_event.set()