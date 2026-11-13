# 앱이 사용하는 경로를 한 곳에서 관리
#  - 사용자 데이터(settings.json, prompts.json, Recordings, Results)는 항상 같은 위치에 저장
#    (실행 위치(cwd)나 설치 위치(읽기 전용/임시 폴더)에 영향받지 않음)
#  - 리소스(아이콘 등)는 개발 환경과 PyInstaller 빌드 모두에서 찾을 수 있게 처리
import os
import shutil
import sys
from pathlib import Path

APP_DIR_NAME = "Azimuth_Scribe"


def app_data_dir() -> Path:
    """사용자 데이터 폴더 (없으면 생성)
    Windows: %APPDATA%\\Azimuth_Scribe
    macOS  : ~/Library/Application Support/Azimuth_Scribe
    Linux  : ~/.local/share/Azimuth_Scribe
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))

    d = base / APP_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def data_path(*parts) -> Path:
    """사용자 데이터 폴더 안의 경로"""
    return app_data_dir().joinpath(*parts)


def recordings_dir() -> Path:
    d = data_path("Recordings")
    d.mkdir(parents=True, exist_ok=True)
    return d


def results_dir() -> Path:
    d = data_path("Results")
    d.mkdir(parents=True, exist_ok=True)
    return d


def resource_path(name) -> Path:
    """앱과 함께 배포되는 리소스(아이콘 등)의 경로
    PyInstaller로 묶으면 sys._MEIPASS 아래에 풀리므로 그쪽을 먼저 본다."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def migrate_legacy(target: Path, *candidates: Path) -> bool:
    """예전 위치에 있던 파일을 새 위치로 한 번만 복사한다.
    target이 이미 있으면 아무것도 하지 않는다. (원본은 지우지 않음)"""
    target = Path(target)
    if target.exists():
        return False

    for src in candidates:
        try:
            src = Path(src)
            if src.is_file() and src.resolve() != target.resolve():
                shutil.copy2(src, target)
                return True
        except OSError:
            continue
    return False