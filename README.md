# Azimuth Scribe

음성을 녹음하면 **텍스트로 변환(STT)** 하고, 목적에 맞는 형식으로 **요약·문서화**해 주는 Windows 데스크톱 앱입니다.
음성 인식과 요약 모두 내 컴퓨터에서 실행되므로, 녹음 내용이 외부 서버로 전송되지 않습니다.

<!-- 스크린샷을 docs/screenshot.png 로 넣고 아래 줄의 주석을 해제하세요 -->
<!-- ![Azimuth Scribe](docs/screenshot.png) -->

## 주요 기능

- 마이크 녹음 (16kHz mono WAV) 및 기존 오디오 파일 변환
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 기반 음성 인식 (한국어 / 영어 / 일본어 / 중국어 / 자동 감지)
- [Ollama](https://ollama.com)의 로컬 LLM으로 요약 (실시간 스트리밍 출력, 중간에 중단 가능)
- 용도별 프롬프트 제공: 일반 요약, 회의록, 진료 기록, 법률 상담 (직접 추가·수정 가능)
- CPU / GPU(NVIDIA CUDA) 선택, GPU 실패 시 자동으로 CPU 전환
- 입력이 컨텍스트 길이를 넘을 위험이 있으면 미리 알려 줌

## 설치 (사용자)

### 1. 앱 내려받기

[Releases](../../releases) 페이지에서 최신 `Azimuth_Scribe-vX.Y.Z-win64.zip`을 받아 원하는 폴더에 압축을 풀고 `Azimuth_Scribe.exe`를 실행합니다.

### 2. Ollama 설치와 요약 모델 받기

요약 기능을 쓰려면 [Ollama](https://ollama.com/download)가 설치되어 실행 중이어야 합니다.
설치 후 터미널에서 기본 모델을 받습니다.

```
ollama pull qwen3:4b-instruct
```

다른 모델을 쓰고 싶다면 앱의 **설정 → 요약 모델**에서 설치된 모델 중 선택할 수 있습니다.

### 3. 음성 인식 모델

처음 실행하면 Whisper 모델(`large-v3`, 약 3GB)을 내려받아 불러옵니다. 인터넷 연결이 필요하고 시간이 걸릴 수 있습니다.
컴퓨터 사양이 낮다면 **설정 → 음성 인식**에서 `medium`, `small`, `base`처럼 작은 모델을 고르거나, 미리 받아 둔 모델 폴더를 지정할 수 있습니다.

### GPU 사용 (선택)

NVIDIA GPU로 음성 인식을 가속하려면 CUDA 12, cuBLAS, cuDNN 9 라이브러리가 필요합니다.
설치되어 있지 않거나 실패하면 자동으로 CPU로 동작합니다. 설정 화면의 "시스템 상태"에서 감지 여부를 확인할 수 있습니다.

## 사용 방법

1. 앱을 실행하고, 설정에서 요약 모델과 음성 인식 옵션을 확인합니다.
2. 녹음하거나 오디오 파일을 선택해 텍스트로 변환합니다.
3. 용도에 맞는 프롬프트를 고르고 요약을 실행합니다.
4. 결과를 확인하고 필요하면 수정해 저장합니다.

## 데이터 저장 위치

앱이 만드는 파일은 실행 위치와 관계없이 아래 폴더에 저장됩니다.

| 운영체제 | 경로 |
|---|---|
| Windows | `%APPDATA%\Azimuth_Scribe` |
| macOS | `~/Library/Application Support/Azimuth_Scribe` |
| Linux | `~/.local/share/Azimuth_Scribe` |

폴더 안에는 `settings.json`, `prompts.json`, `Recordings/`(녹음 파일), `Results/`(결과)가 있습니다.

## 주의사항

- 음성 인식과 요약 결과에는 **오류가 있을 수 있습니다.** 특히 진료 기록, 법률 상담처럼 중요한 용도에서는 반드시 원문과 대조해 확인하세요.
- 이 앱의 결과물은 의료·법률 자문이 아니며, 최종 판단과 책임은 사용자에게 있습니다.
- 긴 녹음은 컨텍스트 길이가 부족하면 앞부분의 지시가 잘려 결과가 부정확해질 수 있습니다. 경고가 나오면 설정에서 컨텍스트 길이를 늘리거나 텍스트를 나누어 요약하세요.
- 녹음할 때는 대화 상대의 동의 등 관련 법규를 확인하세요.

## 문제 해결

| 증상 | 확인할 것 |
|---|---|
| "Ollama에 연결할 수 없습니다" | Ollama가 실행 중인지 확인 (기본 주소 `127.0.0.1:11434`) |
| 모델을 찾을 수 없다는 오류 | `ollama pull <모델명>` 으로 모델 설치 |
| 녹음이 안 됨 | 마이크 연결과 Windows의 마이크 접근 권한 확인 |
| GPU로 실행되지 않음 | CUDA 12 / cuBLAS / cuDNN 9 설치 확인. 안 되면 CPU로 자동 전환됨 |
| STT 모델 로딩이 오래 걸림 | 첫 실행 시 모델 다운로드 중일 수 있음. 작은 모델로 변경 가능 |

## 소스에서 실행 (개발자)

Python 3.10 이상을 권장합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install pyside6 faster-whisper sounddevice numpy requests "av>=11,<17"
python main.py
```

> **참고:** `faster-whisper`는 PyAV 16 이하와 맞춰져 있습니다. 더 최신 PyAV가 설치되면
> `open() got an unexpected keyword argument 'metadata_errors'` 오류가 나므로 `av` 버전을 위처럼 제한하세요.

### 배포판 빌드

```powershell
pip install pyinstaller
pyinstaller --clean Azimuth_Scribe.spec
```

결과물은 `dist\Azimuth_Scribe` 폴더에 생성됩니다. 용량을 줄이기 위해 spec에서 사용하지 않는 Qt 모듈과 `onnxruntime` 등을 제외하고 있으니, 의존성을 바꾸면 빌드 후 모든 기능(설정, 녹음, 변환, 요약)을 한 번씩 확인하세요.

## 라이선스

이 프로젝트의 소스 코드는 [MIT 라이선스](LICENSE)로 공개됩니다.

앱이 사용하는 서드파티 구성요소(PySide6/Qt, faster-whisper, CTranslate2, PyAV/FFmpeg, NumPy, python-sounddevice, Requests 등)는 각자의 라이선스를 따릅니다.
목록은 앱의 **Third-Party Software Notices** 화면에서 볼 수 있습니다.
Ollama와 요약 모델(Qwen3 등)은 앱에 포함되지 않으며, 사용하는 모델의 라이선스는 해당 배포처에서 확인하세요.

## 기여

버그 제보와 개선 제안은 [Issues](../../issues)로 남겨 주세요.
