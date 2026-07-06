# 05_RUNBOOK - деплой и эксплуатация

## Вариант A: GitHub Actions (основной, стоимость 0)
1. Создать **private** репозиторий job-radar, залить код.
2. Settings -> Secrets and variables -> Actions: добавить TELEGRAM_BOT_TOKEN,
   TELEGRAM_CHAT_ID.
   Токен: @BotFather -> /newbot. chat_id: написать боту любое сообщение, затем
   GET https://api.telegram.org/bot<TOKEN>/getUpdates -> взять message.chat.id.
3. Workflow `.github/workflows/daily.yml`:
   - `on: {schedule: [{cron: "0 6 * * *"}], workflow_dispatch: {}}`
   - `concurrency: {group: job-radar, cancel-in-progress: false}`
   - `timeout-minutes: 20`
   - steps: checkout (с token, fetch-depth 1) -> setup-python 3.11 -> actions/cache
     для pip и ~/.cache/huggingface -> pip install -r requirements.txt ->
     `python -m src.main` -> git commit/push data/jobs.sqlite и data/digest_latest.csv
     (только если изменились; `git diff --quiet || commit`).
   - permissions: contents: write.
4. Первый запуск сделать руками через workflow_dispatch и проверить дайджест в Telegram.
5. Нюанс: GH Actions cron исполняется с задержкой до 15-30 минут - это нормально.
   Cron в UTC: 06:00 UTC = 09:00 МСК.

Данные живут в самом репо (sqlite маленький). Приватность: репо обязан быть private,
в БД нет секретов, но есть твой поисковый профиль.

## Вариант B: VPS (запасной, пока он жив)
```
git clone <repo> && cd job-radar
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # вписать TELEGRAM_*
crontab -e:  0 9 * * *  cd /path/job-radar && .venv/bin/python -m src.main >> logs/run.log 2>&1
```
Миграция с VPS на Actions = просто включить workflow, ничего переносить не надо
(БД в репо, коммитить с VPS: добавить git push в конец cron-команды).

## Диагностика
| Симптом | Действие |
|---|---|
| Нет дайджеста утром | GitHub -> Actions -> последний run -> логи. Если run красный, GitHub уже прислал e-mail |
| "Source errors: remoteok 403" в дайджесте | RemoteOK капризничает по UA/IP; если 3 дня подряд - обновить UA или временно выключить источник в config |
| Дайджест пустой (0 вакансий >= 65) | Норма в отдельные дни; если неделю - ослабить min_score до 55 в config или расширить positive_titles |
| Alert "possible parser bug" (guard) | Источник поменял формат. Снять свежий fixture (scripts/capture_fixtures.py), отнести diff в чат LLM, обновить нормализатор |
| БД растёт | Проверить runs.inserted_new по дням; retention работает автоматом, вручную: `sqlite3 data/jobs.sqlite VACUUM;` |

## Регулярная рутина человека (реалистично)
- Ежедневно 2-5 минут: прочитать дайджест, открыть 1-3 ссылки.
- Раз в неделю 10 минут: пометить статусы (applied/ignored) в sqlite или CSV,
  глянуть, не мусорит ли скоринг, поправить словари в config.yaml, git push.
