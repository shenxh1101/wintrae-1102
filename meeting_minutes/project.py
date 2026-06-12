from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .models import MeetingMinutes

DEFAULT_BASE_DIR = Path.home() / ".meeting_minutes"


class ProjectManager:
    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = Path(base_dir) if base_dir else DEFAULT_BASE_DIR

    def init_project(self, name: str) -> Path:
        project_dir = self.base_dir / name
        if project_dir.exists():
            return project_dir
        dirs = [
            project_dir,
            project_dir / "raw",
            project_dir / "processed",
            project_dir / "exports",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
        meta = {
            "name": name,
            "created_at": datetime.now().isoformat(),
            "meetings": [],
        }
        meta_path = project_dir / "meta.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return project_dir

    def list_projects(self) -> List[str]:
        if not self.base_dir.exists():
            return []
        return [
            d.name
            for d in self.base_dir.iterdir()
            if d.is_dir() and (d / "meta.json").exists()
        ]

    def get_project_dir(self, name: str) -> Optional[Path]:
        project_dir = self.base_dir / name
        if project_dir.exists() and (project_dir / "meta.json").exists():
            return project_dir
        return None

    def import_transcript(self, project_name: str, file_path: str, meeting_name: Optional[str] = None) -> Path:
        project_dir = self.get_project_dir(project_name)
        if project_dir is None:
            raise FileNotFoundError(f"项目 '{project_name}' 不存在，请先执行 init")

        src = Path(file_path)
        if not src.exists():
            raise FileNotFoundError(f"文件 '{file_path}' 不存在")

        if meeting_name is None:
            meeting_name = src.stem

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_name = f"{meeting_name}_{timestamp}.txt"
        dest = project_dir / "raw" / dest_name
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        self._register_meeting(project_name, meeting_name, dest_name)
        return dest

    def _register_meeting(self, project_name: str, meeting_name: str, raw_file: str):
        project_dir = self.base_dir / project_name
        meta_path = project_dir / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["meetings"].append({
            "name": meeting_name,
            "raw_file": raw_file,
            "imported_at": datetime.now().isoformat(),
        })
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_minutes(self, project_name: str, minutes: MeetingMinutes, filename: Optional[str] = None) -> Path:
        project_dir = self.get_project_dir(project_name)
        if project_dir is None:
            raise FileNotFoundError(f"项目 '{project_name}' 不存在")

        if filename is None:
            filename = f"{minutes.title or 'meeting'}_{minutes.date or datetime.now().strftime('%Y%m%d')}.json"

        if not filename.endswith(".json"):
            filename += ".json"

        dest = project_dir / "processed" / filename
        dest.write_text(minutes.to_json(), encoding="utf-8")
        return dest

    def load_minutes(self, project_name: str, filename: str) -> MeetingMinutes:
        project_dir = self.get_project_dir(project_name)
        if project_dir is None:
            raise FileNotFoundError(f"项目 '{project_name}' 不存在")

        filepath = project_dir / "processed" / filename
        if not filepath.exists():
            raise FileNotFoundError(f"纪要文件 '{filename}' 不存在")

        return MeetingMinutes.from_json(filepath.read_text(encoding="utf-8"))

    def list_minutes(self, project_name: str) -> List[str]:
        project_dir = self.get_project_dir(project_name)
        if project_dir is None:
            return []
        processed = project_dir / "processed"
        if not processed.exists():
            return []
        return [f.name for f in processed.iterdir() if f.suffix == ".json"]

    def load_raw(self, project_name: str, raw_file: str) -> str:
        project_dir = self.get_project_dir(project_name)
        if project_dir is None:
            raise FileNotFoundError(f"项目 '{project_name}' 不存在")
        filepath = project_dir / "raw" / raw_file
        if not filepath.exists():
            raise FileNotFoundError(f"原始文件 '{raw_file}' 不存在")
        return filepath.read_text(encoding="utf-8")

    def list_raw_files(self, project_name: str) -> List[str]:
        project_dir = self.get_project_dir(project_name)
        if project_dir is None:
            return []
        raw_dir = project_dir / "raw"
        if not raw_dir.exists():
            return []
        return [f.name for f in raw_dir.iterdir() if f.is_file()]

    def get_export_dir(self, project_name: str) -> Path:
        project_dir = self.get_project_dir(project_name)
        if project_dir is None:
            raise FileNotFoundError(f"项目 '{project_name}' 不存在")
        export_dir = project_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        return export_dir
