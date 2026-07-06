# Job Radar

Ежедневный пайплайн подбора зарубежных remote-вакансий под мой профиль.
Три источника (Remotive API, RemoteOK API, We Work Remotely RSS) -> нормализация ->
дедупликация по content-hash -> hard-фильтры -> гибридный скоринг (правила из конфига +
cosine similarity резюме и вакансии на локальных embeddings) -> SQLite + CSV ->
утренний дайджест top-10 в Telegram. Без LLM в рантайме. Бесплатный запуск на
GitHub Actions по cron.

## Быстрый старт (локально, 5 минут)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # вписать TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID
python -m pytest tests/ -q    # 36 тестов, без сети
python scripts/smoke_local.py # сквозной прогон на fixtures, без сети
python -m src.main            # боевой прогон на живых источниках
```
Без .env дайджест печатается в stdout вместо Telegram - удобно для проверки.
Первый боевой прогон скачает модель embeddings (~90 MB), дальше она в кеше.

## Деплой на GitHub Actions (стоимость 0)
1. Private-репозиторий, push этого кода.
2. Settings -> Secrets -> Actions: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
3. Actions -> daily-job-radar -> Run workflow (первый запуск руками).
4. Дальше сам по cron 06:00 UTC ежедневно; обновлённая БД коммитится в репо.

## Управление
- Все словари, веса, пороги и источники: `config.yaml`. Правка = git commit.
- Пометка статусов (applied/ignored): любым SQLite-браузером в `data/jobs.sqlite`,
  поле `status`. Строки с ненулевым статусом retention не трогает.
- Защита БД: UNIQUE-hash, обрезка описаний, retention 30/90 дней, guard на 2000
  вставок/запуск, guard на 200 MB, lock от параллельных запусков.
- Профиль для матчинга: `profile/resume_en.md` (вектор) и `profile/profile.json`.

## Архитектура
```
collectors (изолированы) -> normalize -> salary(USD/mo) -> dedupe(sha256)
-> hard filters -> scoring(rules + MiniLM cosine) -> SQLite -> CSV -> Telegram
```
Падение одного источника не роняет запуск: ошибки попадают в дайджест.
Уровни автономии по процессам: см. docs/AUTOMATION_MATRIX.md.
