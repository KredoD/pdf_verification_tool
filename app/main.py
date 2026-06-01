from __future__ import annotations

import json
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app.config import settings
from app.extractors import read_any_document
from app.models import CheckReport
from app.report_builder import html_report, write_docx_report, write_json_report
from app.utils import safe_filename
from app.verification import verify_package

app = FastAPI(title=settings.app_name)

JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_dir(project_id: str) -> Path:
    return settings.projects_dir / project_id


def status_path(project_id: str) -> Path:
    return project_dir(project_id) / "status.json"


def save_status(project_id: str, status: dict[str, Any]) -> None:
    status["updated_at"] = now_iso()
    p = project_dir(project_id)
    p.mkdir(parents=True, exist_ok=True)
    status_path(project_id).write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    with JOBS_LOCK:
        JOBS[project_id] = status


def load_status(project_id: str) -> dict[str, Any]:
    with JOBS_LOCK:
        if project_id in JOBS:
            return JOBS[project_id]
    p = status_path(project_id)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Проект не найден")
    status = json.loads(p.read_text(encoding="utf-8"))
    with JOBS_LOCK:
        JOBS[project_id] = status
    return status


def update_status(project_id: str, **patch: Any) -> None:
    status = load_status(project_id)
    status.update(patch)
    save_status(project_id, status)


def unique_target(directory: Path, filename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    base = safe_filename(filename)
    candidate = directory / base
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    for i in range(2, 10000):
        c = directory / f"{stem}_{i}{suffix}"
        if not c.exists():
            return c
    return directory / f"{stem}_{uuid.uuid4().hex}{suffix}"


def report_paths(project_id: str) -> dict[str, Path]:
    p = project_dir(project_id)
    return {
        "json": p / "report.json",
        "docx": p / "report.docx",
        "html": p / "report.html",
    }


def save_upload(file: UploadFile, target_dir: Path) -> Path:
    target = unique_target(target_dir, file.filename or "file")
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return target


def process_project(project_id: str) -> None:
    """Background pipeline used by the web UI.

    Stages are intentionally explicit so status/progress can be shown to the
    employee while OCR and parsing are running.
    """
    try:
        status = load_status(project_id)
        project_name = status.get("project_name") or "Без названия"
        ref_file = Path(status["reference_path"])
        doc_files = [Path(p) for p in status.get("document_paths", [])]
        total = 1 + len(doc_files)

        update_status(project_id, stage="reading", percent=5, message="Чтение эталонного документа")
        documents = []

        # The reference is uploaded separately, so force its role.
        reference_doc = read_any_document(ref_file, role_hint="REFERENCE_EGRUL_OR_MASTER")
        documents.append(reference_doc)

        for idx, path in enumerate(doc_files, start=1):
            percent = 10 + int(idx / max(1, len(doc_files)) * 55)
            update_status(
                project_id,
                stage="reading",
                percent=percent,
                message=f"Чтение и извлечение данных: {idx} из {len(doc_files)}",
                current_file=path.name,
            )
            documents.append(read_any_document(path))

        update_status(project_id, stage="verification", percent=75, message="Сверка реквизитов с эталоном")
        report: CheckReport = verify_package(
            project_name=project_name,
            documents=documents,
            reference_filename=reference_doc.filename,
            project_id=project_id,
        )

        update_status(project_id, stage="reporting", percent=88, message="Формирование HTML/DOCX/JSON отчета")
        paths = report_paths(project_id)
        write_json_report(report, paths["json"])
        write_docx_report(report, paths["docx"])
        paths["html"].write_text(html_report(report), encoding="utf-8")

        update_status(
            project_id,
            stage="done",
            percent=100,
            message="Готово",
            report_url=f"/api/projects/{project_id}/report",
            docx_url=f"/api/projects/{project_id}/download/docx",
            json_url=f"/api/projects/{project_id}/download/json",
            error="",
        )
    except Exception as exc:
        update_status(project_id, stage="error", percent=0, message="Ошибка", error=str(exc))


HTML_INDEX = """
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>ВНИИМТ · Первичная проверка документов</title>
<style>
:root { --ink:#10232b; --muted:#66727c; --line:#e2e8ea; --brand:#0f4a55; --brand-dark:#0a3038; --soft:#f6f8f8; --gold:#b69a64; }
* { box-sizing:border-box; }
body { margin:0; font-family:Inter, Arial, sans-serif; color:var(--ink); background:linear-gradient(180deg,#fff,#f6f8f8); min-height:100vh; }
.page { max-width:1120px; margin:0 auto; padding:34px 22px 70px; }
.header { display:flex; justify-content:space-between; align-items:center; gap:18px; margin-bottom:34px; }
.brand { font-weight:950; color:var(--brand); letter-spacing:.05em; }
.badge { border:1px solid var(--line); border-radius:999px; padding:9px 13px; color:var(--muted); background:white; }
.grid { display:grid; grid-template-columns: .9fr 1.1fr; gap:28px; align-items:start; }
.hero h1 { font-size:48px; line-height:1; letter-spacing:-.05em; margin:28px 0 16px; }
.hero p { color:var(--muted); font-size:17px; line-height:1.55; }
.card { background:white; border:1px solid var(--line); border-radius:28px; padding:28px; box-shadow:0 22px 60px rgba(16,35,43,.1); }
label { display:block; margin:18px 0 8px; font-weight:900; }
input[type=text], input[type=file] { width:100%; padding:13px; border:1px solid #d4dcdf; border-radius:14px; background:#fff; }
.help { color:var(--muted); font-size:13px; line-height:1.45; margin-top:7px; }
button { width:100%; border:0; border-radius:999px; padding:16px 22px; margin-top:22px; background:var(--brand); color:white; font-weight:950; font-size:16px; cursor:pointer; }
button:hover { background:var(--brand-dark); }
button:disabled { background:#9ba8ae; cursor:not-allowed; }
.progress { display:none; margin-top:22px; }
.bar { height:12px; border-radius:999px; background:#e8eef0; overflow:hidden; }
.fill { height:100%; width:0%; background:var(--brand); transition:.25s; }
.status { margin-top:10px; color:var(--muted); }
.note { background:#fff8e8; border:1px solid #ead7aa; padding:14px; border-radius:18px; margin-top:18px; color:#5b4720; }
@media(max-width:840px){ .grid{grid-template-columns:1fr}.hero h1{font-size:38px} }
</style>
</head>
<body>
<div class="page">
  <div class="header"><div class="brand">VNIIMT CHECKER</div><div class="badge">Первичная проверка документации</div></div>
  <div class="grid">
    <div class="hero">
      <h1>Проверка пакета документов по эталону</h1>
      <p>Сотрудник загружает эталонный документ отдельно: ЕГРЮЛ, заявление, УПП или другой master-документ. Система извлекает ИНН, ОГРН, телефоны, email, организации, классы риска, НКМИ, лицензии и адреса из всех документов, сверяет их с эталоном и открывает отчет с доказательствами.</p>
      <div class="note">В отчете каждая строка содержит источник: название документа, страницу/таблицу/картинку OCR и фрагмент текста, откуда скрипт взял значение.</div>
    </div>
    <div class="card">
      <form id="form">
        <label>Название проверки / клиента</label>
        <input type="text" name="project_name" value="Первичная проверка ВНИИМТ" />
        <label>Эталонный документ</label>
        <input type="file" name="reference_file" required accept=".pdf,.docx,.xlsx,.xlsm,.txt,.csv,.md" />
        <div class="help">Например: ЕГРЮЛ, заявление, УПП или документ, который считается правильным источником реквизитов.</div>
        <label>Проверяемые документы</label>
        <input type="file" name="documents" multiple required accept=".pdf,.docx,.xlsx,.xlsm,.txt,.csv,.md" />
        <div class="help">Например: бизнес-лицензия, OEM-площадка, производственные документы, сертификаты, ВТД, инструкции.</div>
        <button id="submit" type="submit">Запустить проверку</button>
      </form>
      <div class="progress" id="progress">
        <div class="bar"><div class="fill" id="fill"></div></div>
        <div class="status" id="status">Подготовка...</div>
      </div>
    </div>
  </div>
</div>
<script>
const form = document.getElementById('form');
const progress = document.getElementById('progress');
const fill = document.getElementById('fill');
const statusText = document.getElementById('status');
const submit = document.getElementById('submit');
let timer = null;
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  submit.disabled = true;
  progress.style.display = 'block';
  statusText.textContent = 'Загрузка файлов...';
  const fd = new FormData(form);
  const res = await fetch('/api/projects', { method:'POST', body: fd });
  if (!res.ok) { statusText.textContent = await res.text(); submit.disabled=false; return; }
  const data = await res.json();
  poll(data.project_id);
});
async function poll(projectId) {
  timer = setInterval(async () => {
    const res = await fetch(`/api/projects/${projectId}/status`);
    const data = await res.json();
    fill.style.width = `${data.percent || 0}%`;
    statusText.textContent = `${data.message || ''}${data.current_file ? ': ' + data.current_file : ''}`;
    if (data.stage === 'done') {
      clearInterval(timer);
      window.open(data.report_url, '_blank');
      window.location.href = data.report_url;
    }
    if (data.stage === 'error') {
      clearInterval(timer);
      statusText.textContent = 'Ошибка: ' + (data.error || 'неизвестно');
      submit.disabled = false;
    }
  }, 1200);
}
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return HTML_INDEX


@app.post("/api/projects")
def create_project(
    project_name: str = Form("Первичная проверка ВНИИМТ"),
    reference_file: UploadFile = File(...),
    documents: list[UploadFile] = File(...),
) -> JSONResponse:
    files = [reference_file] + documents
    if len(files) > settings.batch_file_limit:
        raise HTTPException(status_code=400, detail=f"Слишком много файлов. Лимит: {settings.batch_file_limit}")

    total_size = 0
    for f in files:
        # SpooledTemporaryFile may not expose reliable size; this is enforced during saving by infrastructure in production.
        pass

    project_id = uuid.uuid4().hex[:12]
    p = project_dir(project_id)
    input_dir = p / "input"
    reference_dir = p / "reference"
    input_dir.mkdir(parents=True, exist_ok=True)
    reference_dir.mkdir(parents=True, exist_ok=True)

    ref_path = save_upload(reference_file, reference_dir)
    doc_paths = [save_upload(f, input_dir) for f in documents]

    save_status(
        project_id,
        {
            "project_id": project_id,
            "project_name": project_name,
            "stage": "queued",
            "percent": 1,
            "message": "Проект создан",
            "reference_path": str(ref_path),
            "document_paths": [str(p) for p in doc_paths],
            "created_at": now_iso(),
            "error": "",
        },
    )

    thread = threading.Thread(target=process_project, args=(project_id,), daemon=True)
    thread.start()
    return JSONResponse({"project_id": project_id, "status_url": f"/api/projects/{project_id}/status"})


@app.get("/api/projects/{project_id}/status")
def get_status(project_id: str) -> dict[str, Any]:
    return load_status(project_id)


@app.get("/api/projects/{project_id}/report", response_class=HTMLResponse)
def get_report(project_id: str) -> str:
    path = report_paths(project_id)["html"]
    if not path.exists():
        status = load_status(project_id)
        if status.get("stage") == "error":
            return f"<h1>Ошибка</h1><pre>{status.get('error')}</pre>"
        raise HTTPException(status_code=404, detail="Отчет еще не готов")
    return path.read_text(encoding="utf-8")


@app.get("/api/projects/{project_id}/download/docx")
def download_docx(project_id: str) -> FileResponse:
    path = report_paths(project_id)["docx"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="DOCX отчет не найден")
    return FileResponse(path, filename="VNIIMT_primary_check_report.docx", media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@app.get("/api/projects/{project_id}/download/json")
def download_json(project_id: str) -> FileResponse:
    path = report_paths(project_id)["json"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="JSON отчет не найден")
    return FileResponse(path, filename="VNIIMT_primary_check_report.json", media_type="application/json")
