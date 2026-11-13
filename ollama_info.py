# 설정 화면용: Ollama 상태 / GPU 감지 / 모델 언로드 (모두 백그라운드 스레드)
import subprocess
import requests
from PySide6.QtCore import QThread, Signal

OLLAMA_BASE = "http://127.0.0.1:11434"

# 실행 중인 QThread가 파이썬 쪽에서 먼저 삭제되면 앱이 죽으므로 끝날 때까지 참조 유지
_alive = set()


def keep_alive(thread):
    _alive.add(thread)
    thread.finished.connect(lambda t=thread: _alive.discard(t))
    return thread


def _session():
    s = requests.Session()
    s.trust_env = False   # 시스템 프록시가 localhost 요청에 끼어드는 것 방지
    return s


class SystemInfoWorker(QThread):
    result = Signal(dict)

    def run(self):
        info = {
            "ollama_ok": False,
            "ollama_error": "",
            "models": [],      # [{name, size}]
            "running": [],     # [{name, size, size_vram}]
            "cuda_count": 0,
            "gpu_names": [],
        }

        try:
            s = _session()
            r = s.get(f"{OLLAMA_BASE}/api/tags", timeout=(3, 5))
            r.raise_for_status()
            info["models"] = [
                {"name": m.get("name", ""), "size": m.get("size", 0)}
                for m in r.json().get("models", [])
            ]
            info["ollama_ok"] = True

            try:  # 현재 메모리에 올라간 모델과 GPU/CPU 배치
                r = s.get(f"{OLLAMA_BASE}/api/ps", timeout=(3, 5))
                r.raise_for_status()
                info["running"] = [
                    {"name": m.get("name", ""), "size": m.get("size", 0),
                     "size_vram": m.get("size_vram", 0)}
                    for m in r.json().get("models", [])
                ]
            except Exception:
                pass
        except requests.exceptions.RequestException:
            info["ollama_error"] = "Ollama에 연결할 수 없습니다. 실행 중인지 확인하세요."
        except Exception as e:
            info["ollama_error"] = str(e)

        # Whisper(CTranslate2)가 쓸 수 있는 CUDA GPU 수
        try:
            import ctranslate2
            info["cuda_count"] = ctranslate2.get_cuda_device_count()
        except Exception:
            pass

        # GPU 이름 (NVIDIA 드라이버가 있을 때만)
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total",
                 "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if out.returncode == 0:
                info["gpu_names"] = [
                    ln.strip() for ln in out.stdout.splitlines() if ln.strip()
                ]
        except Exception:
            pass

        self.result.emit(info)


class OllamaUnloadWorker(QThread):
    """모델 변경 시 이전 모델을 메모리(VRAM)에서 내림"""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model

    def run(self):
        try:
            _session().post(
                f"{OLLAMA_BASE}/api/generate",
                json={"model": self.model, "keep_alive": 0},
                timeout=(3, 15),
            )
        except Exception:
            pass