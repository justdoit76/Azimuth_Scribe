# Ollama와 통신하는 부분
import json
import math
import re
import socket
import textwrap
import threading
import requests
from PySide6.QtCore import QThread, Signal


SYSTEM_PROMPT = textwrap.dedent("""
    당신은 음성 기록을 문서화하는 AI입니다.

    반드시 지켜야 할 규칙:
    1. 원문에 있는 정보만 사용합니다.
    2. 원문에 없는 사실을 추가하지 않습니다.
    3. 추측하거나 진단하지 않습니다.
    4. 사용자가 지정한 형식에 맞춰 작성합니다.
    5. 불필요한 설명이나 분석 과정은 출력하지 않습니다.
    6. 최종 결과만 한국어로 출력합니다.
    7. 생각 과정이나 작업 과정을 출력하지 않습니다.
    """).strip()


def build_user_prompt(prompt, text):
    prompt = textwrap.dedent(prompt).strip()
    return f"{prompt}\n\n[원문]\n{text}"


def estimate_tokens(text):
    """토큰 수를 대략(보수적으로) 추정한다. 정확한 값이 아니라 '넘칠 위험'을 미리 알리기 위한 용도.
    한글/한자/가나는 글자당 약 1.5토큰, 그 외(영문·숫자·공백·기호)는 글자당 약 0.4토큰으로 계산한다."""
    cjk = 0
    for ch in text:
        o = ord(ch)
        if (0xAC00 <= o <= 0xD7A3 or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F
                or 0x3040 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF):
            cjk += 1
    return math.ceil(cjk * 1.5 + (len(text) - cjk) * 0.4)


class _ThinkFilter:
    """스트리밍 중 <think>...</think> 구간을 걸러낸다.
    태그가 청크 경계에서 쪼개져 들어올 수 있어 꼬리 일부를 버퍼에 보류한다."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self):
        self.pending = ""
        self.in_think = False

    def feed(self, text):
        self.pending += text
        out = []
        while True:
            if self.in_think:
                idx = self.pending.find(self.CLOSE)
                if idx == -1:
                    self.pending = self.pending[-(len(self.CLOSE) - 1):]
                    break
                self.pending = self.pending[idx + len(self.CLOSE):].lstrip()
                self.in_think = False
            else:
                idx = self.pending.find(self.OPEN)
                if idx == -1:
                    keep = len(self.OPEN) - 1
                    if len(self.pending) > keep:
                        out.append(self.pending[:-keep])
                        self.pending = self.pending[-keep:]
                    break
                out.append(self.pending[:idx])
                self.pending = self.pending[idx + len(self.OPEN):]
                self.in_think = True
        return "".join(out)

    def flush(self):
        rest, self.pending = self.pending, ""
        return "" if self.in_think else rest


class LLMWorker(QThread):

    progress = Signal(str)   # 생성되는 토큰(조각)을 실시간 전달
    warning = Signal(str)    # 결과는 나왔지만 품질에 영향을 줄 수 있는 경고 (done보다 먼저 전달됨)
    done = Signal(str)
    cancelled = Signal()     # 사용자가 중단함 (이 경우 done/error는 나가지 않음)
    error = Signal(str)

    BASE_URL = "http://127.0.0.1:11434"

    # ---- 컨텍스트 계획용 상수 ----
    CTX_STEP = 1024            # 자동 제안 시 올림 단위
    CTX_HARD_CAP = 32768       # 이 이상은 메모리 문제로 자동 제안하지 않음 (필요하면 조정)
    OUTPUT_RESERVE = 1024      # 출력용으로 남겨둘 최소 여유 토큰
    TEMPLATE_OVERHEAD = 64     # 채팅 템플릿(특수 토큰) 몫

    def __init__(self, text, prompt, settings=None, parent=None):
        super().__init__(parent)
        s = settings or {}
        self.text = text
        self.prompt = prompt
        self.model = s.get("model", "qwen3:4b-instruct")
        self.device = s.get("device", "auto")          # auto | cpu | gpu
        self.temp = s.get("temperature", 0.2)
        self.num_ctx = s.get("num_ctx", 8192)
        self.num_predict = s.get("num_predict", 2048)

        self._cancel = threading.Event()
        self._response = None

    # ---------- 컨텍스트 사전 점검 ----------
    @classmethod
    def plan_context(cls, text, prompt, num_ctx, num_predict):
        """요청 전에 입력이 컨텍스트에 들어가는지 추정한다. (UI 스레드에서 호출해도 가벼움)

        반환: dict
          prompt_tokens : 입력(시스템+지시+원문) 추정 토큰
          needed        : 입력 + 출력 여유
          fits          : needed <= num_ctx
          suggested     : 이번 요청에 권장하는 num_ctx (CTX_STEP 배수, CTX_HARD_CAP 이하)
          too_long      : needed가 CTX_HARD_CAP을 넘음 (나눠서 처리해야 함)
        """
        prompt_tokens = (
            estimate_tokens(SYSTEM_PROMPT)
            + estimate_tokens(build_user_prompt(prompt, text))
            + cls.TEMPLATE_OVERHEAD
        )
        needed = prompt_tokens + min(int(num_predict), cls.OUTPUT_RESERVE)
        suggested = min(cls.CTX_HARD_CAP,
                        math.ceil(needed / cls.CTX_STEP) * cls.CTX_STEP)
        return {
            "prompt_tokens": prompt_tokens,
            "needed": needed,
            "fits": needed <= int(num_ctx),
            "suggested": suggested,
            "too_long": needed > cls.CTX_HARD_CAP,
        }

    # ---------- 취소 ----------
    def cancel(self):
        """중단 요청. 연결을 끊어 Ollama의 생성도 멈추게 한다.
        토큰을 기다리며 블로킹된 읽기(첫 토큰 전, 긴 프롬프트 처리 중)도 소켓을 shutdown해서 깨운다."""
        self._cancel.set()
        resp = self._response
        if resp is None:
            return

        raw = getattr(resp, "raw", None)
        socks = [
            getattr(getattr(raw, "_connection", None), "sock", None),                     # urllib3 2.x
            getattr(getattr(getattr(raw, "_fp", None), "fp", None), "raw", None),         # http.client 쪽 소켓 파일
        ]
        for sk in socks:
            sk = getattr(sk, "_sock", sk)          # SocketIO -> socket
            if isinstance(sk, socket.socket):
                try:
                    sk.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        try:
            resp.close()
        except Exception:
            pass

    # ---------- 요청 구성 ----------
    def _gpu_options(self):
        # num_gpu = GPU에 올릴 계층(layer) 수. 생략하면 Ollama가 자동 결정.
        if self.device == "cpu":
            return {"num_gpu": 0}        # GPU 사용 안 함
        if self.device == "gpu":
            return {"num_gpu": 999}      # 가능한 모든 계층을 GPU로
        return {}

    def _build_request(self, system_prompt, user_prompt):
        options = {
            "temperature": self.temp,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
            "repeat_penalty": 1.1,
        }
        options.update(self._gpu_options())

        name = self.model.lower()

        if "qwen" in name:
            # raw 모드로 ChatML 프롬프트를 직접 구성 (qwen 계열 형식)
            raw_prompt = (
                f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
                f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
                f"<|im_start|>assistant\n"
            )
            # qwen3 하이브리드(4b, 8b 등)는 사고 과정을 먼저 쓰려 하므로 빈 think 블록을 채워 건너뛴다.
            # '-instruct' 빌드는 사고 과정이 없으므로 필요 없다.
            if name.startswith("qwen3") and "instruct" not in name:
                raw_prompt += "<think>\n\n</think>\n\n"
            options["stop"] = ["<|im_end|>", "<|im_start|>"]

            return "/api/generate", "response", {
                "model": self.model,
                "prompt": raw_prompt,
                "raw": True,
                "stream": True,
                "keep_alive": "30m",
                "options": options,
            }

        # qwen이 아닌 모델은 Ollama가 모델 고유 템플릿을 적용하도록 chat API 사용
        return "/api/chat", "message", {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": True,
            "keep_alive": "30m",
            "options": options,
        }

    # ---------- 사후 점검 ----------
    def _check_final(self, final):
        """Ollama의 마지막 응답 조각에 든 실제 사용량으로 잘림 여부를 확인한다.
        (프롬프트 캐시가 적용되면 prompt_eval_count가 작게 나올 수 있어, 어디까지나 보조 점검)"""
        if final.get("done_reason") == "length":
            self.warning.emit(
                f"출력이 '최대 출력 토큰'({self.num_predict:,})에서 잘렸습니다.\n"
                "설정에서 값을 늘리거나 텍스트를 나누어 요약하세요."
            )

        used = int(final.get("prompt_eval_count", 0)) + int(final.get("eval_count", 0))
        if self.num_ctx and used >= self.num_ctx * 0.97:
            self.warning.emit(
                f"입력과 출력이 컨텍스트 길이({self.num_ctx:,})를 거의 다 채웠습니다 (사용 약 {used:,}토큰).\n"
                "작성 지시가 담긴 앞부분이 잘려 결과가 부정확할 수 있으니 반드시 확인하세요.\n"
                "설정에서 컨텍스트 길이를 늘리거나 텍스트를 나누어 요약하세요."
            )

    # ---------- 실행 ----------
    def run(self):
        try:
            system_prompt = SYSTEM_PROMPT
            user_prompt = build_user_prompt(self.prompt, self.text)

            endpoint, field, payload = self._build_request(system_prompt, user_prompt)

            session = requests.Session()
            session.trust_env = False

            think = _ThinkFilter()
            chunks = []
            final = {}

            def emit_visible(text):
                if text:
                    chunks.append(text)
                    self.progress.emit(text)

            # (연결 5초, 토큰 간 최대 대기 300초: 첫 토큰은 모델 로딩+프롬프트 처리 시간 포함)
            with session.post(
                self.BASE_URL + endpoint,
                json=payload,
                stream=True,
                timeout=(5, 300)
            ) as response:
                self._response = response
                response.raise_for_status()

                for line in response.iter_lines():
                    if self._cancel.is_set():
                        break
                    if not line:
                        continue
                    data = json.loads(line)

                    if "error" in data:
                        raise RuntimeError(data["error"])

                    if field == "message":
                        piece = data.get("message", {}).get("content", "")
                    else:
                        piece = data.get("response", "")

                    if piece:
                        emit_visible(think.feed(piece))

                    if data.get("done"):
                        final = data
                        break

            if self._cancel.is_set():
                self.cancelled.emit()
                return

            emit_visible(think.flush())

            result = "".join(chunks)
            if "</think>" in result:   # 안전장치
                result = result.split("</think>")[-1]
            result = re.sub(r"<think>.*?</think>", "", result, flags=re.DOTALL).strip()

            if not result:
                raise RuntimeError("LLM이 빈 응답을 반환했습니다.")

            self._check_final(final)
            self.done.emit(result)

        except Exception as e:
            # 사용자가 취소하며 연결을 닫을 때 생기는 예외는 오류로 취급하지 않는다
            if self._cancel.is_set():
                self.cancelled.emit()
                return
            self.error.emit(self._describe_error(e))

    def _describe_error(self, e):
        # ConnectTimeout은 Timeout과 ConnectionError 둘 다 상속하므로 Timeout을 먼저 처리
        if isinstance(e, requests.exceptions.Timeout):
            return "LLM 응답 시간이 초과되었습니다."

        if isinstance(e, requests.exceptions.ConnectionError):
            return (
                "Ollama에 연결할 수 없습니다.\n"
                "Ollama가 실행 중인지 확인하세요."
            )

        if isinstance(e, requests.exceptions.HTTPError):
            detail = ""
            try:
                detail = e.response.json().get("error", "")
            except Exception:
                pass
            return (
                f"Ollama 오류: {detail or e}\n"
                f"모델({self.model})이 설치되어 있는지 확인하세요.\n"
                f"설정 화면에서 설치된 모델을 선택하거나, 예) ollama pull {self.model}"
            )

        return str(e)