# 프롬프트 관리
import json
import os
import textwrap
import time
from pathlib import Path

from app_paths import data_path, migrate_legacy

_DEFAULTS_RAW = {
    "일반 요약": """
        다음 내용을 핵심 내용 중심으로 요약하세요.

        1. 주요 내용
        2. 중요한 사실
        3. 요청사항
        4. 후속 조치

        원문에 없는 내용을 추가하지 마세요.
        """,

    "회의록": """
        다음 회의 내용을 정리하세요.

        1. 회의 목적
        2. 주요 논의사항
        3. 결정사항
        4. 요청사항
        5. 후속 조치

        원문에 없는 내용을 추가하지 마세요.
        """,

    "진료 기록": """
        다음 진료 내용을 진료기록 작성에 도움이 되도록 정리하세요.

        1. 주요 증상
        2. 증상 발생 시점
        3. 환자의 주요 호소
        4. 과거 병력
        5. 현재 복용약
        6. 의사의 설명
        7. 검사 및 치료 계획
        8. 주의사항

        원문에 없는 내용을 추측하지 마세요.
        """,

    "법률 상담": """
        다음 법률 상담 내용을 상담 기록으로 정리하세요.

        1. 사건 개요
        2. 사실관계
        3. 주요 쟁점
        4. 고객의 요청사항
        5. 상담 중 설명된 내용
        6. 확인이 필요한 사항
        7. 향후 조치

        원문에 없는 사실이나 법률적 판단을 추가하지 마세요.
        """,
}

DEFAULT_PROMPTS = {name: textwrap.dedent(p).strip() for name, p in _DEFAULTS_RAW.items()}


class PromptManager:
    def __init__(self, filename="prompts.json"):
        # 실행 위치(cwd)와 무관하게 항상 사용자 데이터 폴더에 저장
        self.path = data_path(filename)

        # 예전 버전이 만든 파일(현재 작업 폴더 / 앱 폴더)이 있으면 한 번만 복사
        migrate_legacy(
            self.path,
            Path.cwd() / filename,
            Path(__file__).resolve().parent / filename,
        )

        self.prompts = {}
        self.load()

    def _load_defaults(self):
        self.prompts = dict(DEFAULT_PROMPTS)
        self.save()

    def _backup_corrupt(self):
        # 손상된 파일을 덮어써서 잃어버리지 않도록 옆에 보관
        try:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            self.path.replace(self.path.with_name(f"{self.path.name}.corrupt-{stamp}"))
        except OSError:
            pass

    def load(self):
        if not self.path.exists():
            self._load_defaults()
            return

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("prompts.json 최상위 구조가 객체가 아닙니다.")

            self.prompts = {
                name: "\n".join(lines) if isinstance(lines, list) else str(lines)
                for name, lines in data.items()
            }
        except Exception:
            self._backup_corrupt()
            self._load_defaults()

    def save(self):
        # 저장 도중 꺼져도 파일이 깨지지 않도록 임시 파일 → 교체
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.prompts, f, ensure_ascii=False, indent=4)
        os.replace(tmp, self.path)

    def names(self):
        return list(self.prompts.keys())

    def get(self, name):
        return self.prompts.get(name, "")

    def set(self, name, prompt):
        self.prompts[name] = prompt
        self.save()

    def delete(self, name):
        if name in self.prompts:
            del self.prompts[name]
            self.save()