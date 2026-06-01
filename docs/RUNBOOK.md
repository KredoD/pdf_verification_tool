# RUNBOOK: запуск и эксплуатационная проверка

## 1. Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Запуск веб-сервиса

```bash
uvicorn app.main:app --reload
```

Проверить страницу:

```text
http://127.0.0.1:8000
```

## 3. Локальный CLI-прогон

```bash
python scripts/run_local_check.py \
  --reference sample_data/egrul_reference.txt \
  --documents sample_data/business_license.txt sample_data/oem_contract.txt sample_data/lease_agreement.txt \
  --out output/manual_test
```

## 4. Проверка результата

Открыть:

```text
output/manual_test/report.html
output/manual_test/report.docx
output/manual_test/report.json
```

## 5. Быстрая диагностика

Если PDF/DOCX читается плохо:

- проверить, есть ли текстовый слой;
- если документ состоит из картинок, включить/проверить OCR;
- проверить наличие Tesseract в системе;
- смотреть `stats` в JSON-отчете: сколько текста извлечено, сколько OCR-страниц использовано.

## 6. Рекомендации для production

- вынос OCR в очередь задач;
- хранение проектов в S3/Yandex Object Storage;
- автоматическая очистка загруженных файлов;
- логирование действий сотрудников;
- авторизация;
- Dockerfile и docker-compose;
- HTTPS через reverse proxy.
