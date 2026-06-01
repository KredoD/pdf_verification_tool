from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime settings.

    All settings are environment-variable based so the technical director can
    deploy the same code locally, in a VM, or in Kubernetes without changing
    application code.
    """

    app_name: str = "VNIIMT Primary Documentation Checker"
    projects_dir: Path = Path(os.getenv("VNIIMT_PROJECTS_DIR", "output/projects"))

    batch_file_limit: int = int(os.getenv("VNIIMT_BATCH_FILE_LIMIT", "50"))
    batch_size_limit_mb: int = int(os.getenv("VNIIMT_BATCH_SIZE_LIMIT_MB", "800"))

    ocr_enabled: bool = os.getenv("OCR_ENABLED", "true").lower() in {"1", "true", "yes", "y"}
    ocr_lang: str = os.getenv("OCR_LANG", "rus+eng")
    ocr_dpi: int = int(os.getenv("OCR_DPI", "220"))
    ocr_max_pages_per_file: int = int(os.getenv("OCR_MAX_PAGES_PER_FILE", "80"))
    ocr_max_docx_images: int = int(os.getenv("OCR_MAX_DOCX_IMAGES", "120"))

    fuzzy_match_threshold: int = int(os.getenv("FUZZY_MATCH_THRESHOLD", "85"))
    possible_match_threshold: int = int(os.getenv("POSSIBLE_MATCH_THRESHOLD", "70"))

    @property
    def batch_size_limit_bytes(self) -> int:
        return self.batch_size_limit_mb * 1024 * 1024


settings = Settings()
settings.projects_dir.mkdir(parents=True, exist_ok=True)
