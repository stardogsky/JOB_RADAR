# JOB_RADAR — Задача 1: расширение источников + жёсткая отсечка

Это дифф поверх твоего репо. Просто скопируй файлы на их места (структура ниже).
Пайплайн A (ежедневный сбор → фильтр → скоринг → Telegram) остаётся тем же —
добавлены только новые источники и подправлена отсечка. LLM не трогали.

## Что менялось

### Новые файлы (положить в `src/collectors/`)
- `jobicy.py`       — Jobicy API v2 (JSON)
- `arbeitnow.py`    — Arbeitnow API (JSON)
- `himalayas.py`    — Himalayas API (JSON)
- `jobscollider.py` — JobsCollider (RSS)
- `jobspresso.py`   — Jobspresso (RSS)

### Изменённые файлы (заменить целиком)
- `src/normalize.py` — дописаны нормализаторы: normalize_jobicy / normalize_arbeitnow /
  normalize_himalayas / normalize_jobscollider / normalize_jobspresso + общий
  помощник `_annual_salary` (годовая зарплата с валютой) и `_normalize_rss`.
  Существующие функции не тронуты.
- `src/main.py` — новые импорты + `collect_all` переписан на реестр `SOURCES`
  (табличный, чтобы 8 источников не были стеной копипаста). Семантика каждого
  источника сохранена 1-в-1 (remoteok = single, остальные = each).
- `config.yaml` — три правки (см. ниже).

## Правки config.yaml
1. В `sources:` добавлены блоки: himalayas, jobicy, arbeitnow, jobscollider, jobspresso.
2. Из `irrelevant_blacklist` убрано слово `senior` (по твоему решению: senior не режем
   жёстко, а понижаем скор — это делается в scoring.py, см. «Не сделано»).
   В `seniority_negative` `senior` намеренно ОСТАВЛЕН.
3. `guards.max_new_per_run` поднят 2000 → 4000 на время первого бэкфилла
   (8 источников за один первый прогон легко дадут >2000 новых и без этого
   сработает guard «possible parser bug» и остановит запуск). После первого
   успешного прогона можешь вернуть 2000.

## Решения по фильтрации (реализовано в отсечке источников)
- Зарплата не указана → вакансия ОСТАЁТСЯ (salary_known=false, не режем).
- remote_confidence: 'no' режется жёстко (как и было); 'probably' и 'yes' остаются.
- Новые источники проставляют remote_confidence так:
  - Jobicy: 'yes' если jobGeo содержит worldwide/anywhere-маркер, иначе 'probably'.
  - Arbeitnow: remote=false → 'no'; remote=true и гео пустое/worldwide → 'yes'; иначе 'probably'.
  - Himalayas: нет locationRestrictions или worldwide → 'yes', иначе 'probably'.
  - JobsCollider/Jobspresso (remote-only RSS) → 'yes' (US-only ловится фильтром по тексту).

## !!! ДОПУЩЕНИЯ по именам полей API (проверь на первом прогоне)
Сеть в песочнице была закрыта — схемы не удалось дёрнуть живьём, поля взяты по
документации. Если источник вернёт 0 вакансий или KeyError — почти наверняка
разошлось имя поля, поправь в normalize.py (падение одного источника изолировано,
весь запуск не роняет).
- Jobicy v2: jobs[].jobTitle, url, companyName, jobGeo, jobDescription/jobExcerpt,
  annualSalaryMin/annualSalaryMax, salaryCurrency, pubDate, id, jobIndustry[], jobType[].
- Arbeitnow: data[].title, url, company_name, location, remote(bool), description,
  created_at(unix), slug, tags[], job_types[]. Зарплаты в API нет.
- Himalayas: jobs[].title, applicationLink/guid, companyName, description/excerpt,
  locationRestrictions[], minSalary/maxSalary, salaryCurrency, pubDate(unix),
  categories[], seniority[]. (limit=100 может упереться в потолок API — проверь.)
- Зарплата: USD-годовая → parse_salary_numbers; не-USD → строка вида
  "{min}-{max} {CUR} per year" → parse_salary_text (использует currency_rates_to_usd).

## Не сделано в этом диффе (ждёт scoring.py)
Присланный `scoring.py` пришёл битым (страница ошибки GitHub 429, 199 байт).
Без него НЕ реализованы:
1. Сильное понижение скора для senior/lead/principal.
2. Флаг + сильное понижение скора для remote_confidence='probably'.
3. Команда ре-скоринга всей базы (для обновлённого резюме).
Пришли scoring.py через Raw — доделаю это отдельным диффом.

## Как проверить локально
```bash
# синтаксис
python -m py_compile src/*.py src/collectors/*.py
# точечно один источник (временно выключи остальные в config.yaml enabled:false)
python -m src.main
# либо ваш smoke на фикстурах
python scripts/smoke_local.py
```
