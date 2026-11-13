# 앱 설정(settings.json) 관리
import copy
import json
import os
from pathlib import Path

from app_paths import data_path, migrate_legacy

DEFAULTS = {
    "llm": {
        "model": "qwen3:4b-instruct",   # Ollama에 설치된 모델 이름(태그 포함)
        "device": "auto",               # auto | cpu | gpu
        "num_ctx": 8192,                # 한 번에 처리할 최대 토큰(긴 녹취록은 늘려야 함)
        "num_predict": 2048,            # 최대 출력 토큰
        "temperature": 0.2,
    },
    "stt": {
        "model": "large-v3",            # 모델 이름 또는 로컬 폴더 경로
        "device": "auto",               # auto | cpu | cuda
        "compute_type": "auto",         # auto | int8 | int8_float16 | float16
        "language": "ko",               # ko | en | ja | zh | auto(자동 감지)
    },
}


class SettingsManager:
    def __init__(self, filename="settings.json"):
        # 실행 위치(cwd)·설치 위치와 무관하게 항상 사용자 데이터 폴더에 저장
        self.path = data_path(filename)
        # 예전 버전이 앱 폴더에 만든 settings.json이 있으면 한 번만 복사
        migrate_legacy(self.path, Path(__file__).resolve().parent / filename)
        self.data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self):
        if not self.path.exists():
            self.save()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except Exception:
            return  # 파일이 손상되었으면 기본값 사용

        for section, defaults in DEFAULTS.items():
            src = saved.get(section)
            if not isinstance(src, dict):
                continue
            for key, default in defaults.items():
                if key not in src:
                    continue
                value = src[key]
                if isinstance(default, bool) or isinstance(value, bool):
                    continue
                if isinstance(default, float) and isinstance(value, (int, float)):
                    self.data[section][key] = float(value)
                elif isinstance(value, type(default)):
                    self.data[section][key] = value

    def save(self):
        # 저장 도중 꺼져도 파일이 깨지지 않도록 임시 파일 → 교체
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)
        os.replace(tmp, self.path)

    def get(self, section):
        return dict(self.data[section])

    def update(self, section, values):
        self.data[section].update(values)
        self.save()

    def snapshot(self):
        return copy.deepcopy(self.data)