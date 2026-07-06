# 02_SPEC - Job Radar. Контракты модулей и краевые случаи

Этот файл - главный. Кодирующая модель обязана реализовать ровно это поведение.

## 1. Единая схема Job (выход normalize.py)
```python
@dataclass
class Job:
    source: str                 # "remotive" | "remoteok" | "wwr"
    source_id: str | None
    title: str                  # обязателен; если пуст - вакансия отбрасывается с логом
    company: str | None
    url: str                    # обязателен
    location_raw: str | None
    remote_confidence: str      # "yes" | "probably" | "no" (правила ниже)
    salary_raw: str | None      # исходная строка/числа как текст, для отладки
    salary_known: bool
    salary_min_usd_month: float | None
    salary_max_usd_month: float | None
    description: str            # plain text: HTML вычищен, обрезан до 20 000 символов
    tags: list[str]
    date_posted: str | None     # ISO date
    fetched_at: str             # ISO UTC now
```

## 2. Контракты коллекторов

Общее для всех (base.py):
- timeout: connect 10s / read 30s; 2 retry с backoff 5s и 15s только на сетевых ошибках и 5xx.
- User-Agent: `job-radar/1.0 (personal job search; contact in repo)`.
- Возвращают list[dict] сырых записей. Любое исключение ловится в main.py, источник
  помечается как failed, пайплайн продолжается.
- Если источник вернул 0 записей - это warning в лог и в дайджест, не ошибка.

### 2.1 Remotive
- GET `https://remotive.com/api/remote-jobs?category=software-dev` и второй запрос
  с `?search=automation`. Итого 2 HTTP-запроса. Лимит источника: не чаще 4/день - соблюдён.
- Ответ: `{"0-legal-notice": ..., "job-count": N, "jobs": [...]}`. Брать `jobs`.
- Поля вакансии: id, url, title, company_name, category, tags[], job_type,
  publication_date, candidate_required_location, salary (СВОБОДНЫЙ ТЕКСТ, часто пустой),
  description (HTML).
- Маппинг: company_name -> company; candidate_required_location -> location_raw;
  salary -> salary_raw (парсится salary.py); publication_date -> date_posted.
- remote_confidence: у Remotive всё remote -> "yes", НО если candidate_required_location
  содержит одиночную страну/регион не из allowlist (см. filters) - это учитывает location-фильтр,
  не remote_confidence.
- Условие ToS: хранить и показывать ссылку на страницу Remotive (поле url) - выполняется схемой.

### 2.2 RemoteOK - проверено на живом ответе 2026-07, реализовать ровно так
- GET `https://remoteok.com/api`. ВАЖНО: без нормального User-Agent может отдать 403.
- Ответ - JSON-массив. **Первый элемент - legal-notice без поля "id". Пропускать все
  элементы, где нет ключа "id".**
- Поле должности называется **`position`**, НЕ title.
- `salary_min` / `salary_max`: числа, ГОДОВЫЕ. **0 означает "не указано"**, а не ноль долларов.
  Валюта не гарантирована USD: в живых данных встречен диапазон 200000-225000, который по
  описанию оказался PLN/год. Правило: если в description в пределах 200 символов от числа
  встречается код валюты (PLN, EUR, GBP, INR, BRL...) или символ не-$, и он не USD -
  salary_known=False, salary_raw = найденный фрагмент. Иначе трактуем как USD/год.
- description: HTML + битая кодировка (mojibake вида `â€™`, `Â`). Обработка:
  1) снять HTML (html.unescape + strip tags);
  2) попытка починки: `text.encode('latin-1', 'ignore').decode('utf-8', 'ignore')`,
     применять только если в тексте есть маркеры `â€` или `Ã`; обернуть в try, при
     неудаче оставить как есть;
  3) **вырезать анти-спам блок**: всё от `Please mention the word` до конца текста
     (regex, case-insensitive). Он есть в каждой вакансии и загрязняет hash и embeddings.
- **Фид содержит откровенно НЕ-remote мусор** (onsite-ритейл, пожарные и т.п.).
  remote_confidence = "no", если location_raw содержит конкретный город/адрес И в
  title+description нет слов remote/anywhere/worldwide/work from home. Иначе "probably".
  ("yes" у RemoteOK не ставим никогда - фид не заслужил.)

### 2.3 We Work Remotely (RSS)
- 3 фида: `.../categories/remote-programming-jobs.rss`,
  `.../categories/remote-devops-sysadmin-jobs.rss`, `.../categories/all-other-remote-jobs.rss`.
- Парсить feedparser'ом. item.title имеет формат `"Company: Position"` - сплит по первому
  `": "`; если разделителя нет, company=None, title=целиком.
- description: HTML; внутри есть строки `Headquarters: ...` и `URL: ...` - Headquarters
  извлечь в location_raw. В item может быть тег `region` - если есть, приоритет у него.
- Зарплата почти никогда не указана: если в тексте есть паттерн `$NNN,NNN` или
  `Salary: ...` - отдать в salary.py, иначе salary_known=False.
- remote_confidence = "yes" (борда курируемая), но location-фильтр по region всё равно работает
  (частый кейс: "Remote Worker - United States" -> это US-only).
- guid/link -> url и source_id.

## 3. salary.py - контракт и таблица кейсов
Вход: salary_raw (строка) ИЛИ пара годовых чисел (RemoteOK). Выход:
(salary_known, min_usd_month, max_usd_month).

Конверсии: hourly * 160; yearly / 12; k-суффикс * 1000. Курсы из config.yaml:
EUR 1.08, GBP 1.27, остальные валюты -> salary_known=False.

Обязательные тест-кейсы (tests/test_salary.py, все должны проходить):
| вход                          | known | min/мес | max/мес |
|-------------------------------|-------|---------|---------|
| "$20/hr"                      | True  | 3200    | 3200    |
| "$1500/month"                 | True  | 1500    | 1500    |
| "€40k/year"                   | True  | 3600    | 3600    |
| "£35,000 - £45,000 per year"  | True  | 3704    | 4763    |
| "$60k - $90k"                 | True  | 5000    | 7500    |  # без периода: числа >=10000 или с k = годовые
| "$90,000 USD or more"         | True  | 7500    | None    |
| "Competitive salary"          | False | None    | None    |
| "" / None                     | False | None    | None    |
| remoteok (0, 0)               | False | None    | None    |
| remoteok (60000, 90000)       | True  | 5000    | 7500    |
| "200000-225000 PLN/year"      | False | None    | None    |
| "$15-20/hour"                 | True  | 2400    | 3200    |
Округление до целого допустимо (assert с tolerance ±1).
Эвристика периода, если он не указан: число < 200 -> hourly; 200..9999 -> monthly;
>= 10000 -> yearly.

## 4. filters.py - hard-фильтры (до скоринга)
Результат - не удаление, а установка category="skip" + причина (в БД попадает всё,
кроме дублей; см. retention). Порядок:
1. remote_confidence == "no" -> skip ("not remote").
2. salary_known и salary_max_usd_month < 1300 -> skip ("salary below threshold").
   salary_known=False -> НЕ фильтровать, risk "salary unknown".
3. Location: если location/description содержит паттерны US-only
   ("US only", "United States only", "must be based in the US", "US work authorization",
   "authorized to work in the United States", "W2", "US citizens") -> skip ("US-only").
   Аналогичные паттерны для "must be located in <одна страна>" (кроме worldwide-формулировок) ->
   risk, минус к location-компоненте, но не skip.
4. Title содержит слово из title_blacklist (config): senior, staff, principal, lead,
   head of, director, VP, chief -> НЕ skip, а seniority-штраф (см. скоринг). Skip только
   для явно нерелевантных: nurse, driver, teacher, accountant, attorney и т.п.
   (irrelevant_blacklist в config, стартовый список из 30-40 слов пусть предложит кодер,
   утверждается по первым дайджестам).

## 5. scoring.py
Каждый компонент нормируется в 0..1, итог:
```
raw = 0.30*title + 0.25*similarity + 0.15*salary + 0.10*remote + 0.10*seniority + 0.10*keywords
score = clamp(round(raw*100 - penalties), 0, 100)
```
- **title**: 1.0 если title содержит фразу из positive_titles (ai automation, automation
  specialist, workflow automation, no-code, zapier, make.com, n8n, ai operations, chatbot,
  implementation specialist, ai engineer (0.6), prompt engineer, crm, business process);
  учитывать лучшее совпадение, значения фраз задаются в config.yaml словарём фраза->вес.
- **similarity**: cosine(resume_emb, job_emb), где job_text = title + " " + description[:4000].
  Модель all-MiniLM-L6-v2. Вектор резюме считается один раз за запуск.
  cosine обычно живёт в диапазоне ~0.05..0.65; нормировать линейно: (cos-0.1)/0.5, clamp 0..1.
- **salary**: known и min>=1300 -> 0.7; known и min>=2000 -> 1.0; unknown -> 0.4 (+risk);
  known и max<1300 сюда не доходит (отсёкся фильтром).
- **remote**: yes -> 1.0; probably -> 0.6.
- **seniority**: junior/associate/specialist/coordinator/consultant/implementation в title -> 1.0;
  нейтрально -> 0.6; senior/staff/principal/lead/head/director в title -> 0.1.
- **keywords**: доля positive_keywords (config, ~25 слов: ai automation, automation, zapier,
  make.com, n8n, openai, chatgpt, claude, llm, prompt, workflow, notion, airtable, crm,
  api, webhook, chatbot, business process, integration, low-code, gpt, rag, embeddings),
  найденных в title+description; нормировка: min(hits/5, 1.0).
- **penalties** (абсолютные пункты): каждое вхождение negative_keywords
  ("5+ years", "7+ years", "kubernetes", "machine learning engineer",
  "computer science degree required", "PhD") -> -8, cap -25; location-risk -> -10.
- reasons[]: человекочитаемые строки для каждого компонента > 0.6 и каждого штрафа.
- risks[]: salary unknown, location-ограничения, seniority-риск, сработавшие negative keywords.

Категории: >=80 apply_first, 65-79 good, 50-64 maybe, 35-49 weak, <35 skip.

## 6. dedupe.py
content_hash = sha256(lower(normalize_spaces(company + "|" + title + "|" + first 500 chars
описания ПОСЛЕ очистки))). URL в hash не входит (у источников бывают трекинг-параметры).
Вставка INSERT OR IGNORE по UNIQUE(content_hash). Кросс-источниковые дубли (одна вакансия
на Remotive и RemoteOK) этим же покрываются в большинстве случаев; идеал не требуется.

## 7. Гарантии против раздувания БД (обязательные)
1. UNIQUE(content_hash) + INSERT OR IGNORE - повторные запуски не плодят строки.
2. description обрезается до 20 000 символов ДО записи. raw_json не хранится вовсе.
3. **Guard на запуск**: если новых вставок за один запуск > 2000 - прервать ПОСЛЕ вставки,
   пометить run как аномальный, отправить alert в Telegram ("possible parser bug").
4. **Retention** (выполняется в конце каждого запуска):
   DELETE FROM jobs WHERE category IN ('skip','weak') AND fetched_at < now-30d AND status='new';
   DELETE FROM jobs WHERE fetched_at < now-90d AND status='new';
   строки со status applied/seen/ignored не трогаются никогда.
   Раз в 30 запусков (счётчик в runs) - VACUUM.
5. **Guard на размер**: если файл jobs.sqlite > 200 MB - запуск завершается с alert,
   вставки не выполняются. При текущих источниках реальный размер - единицы MB, guard
   существует на случай бага.
6. Lock-файл (data/.run.lock, проверка возраста > 1 час = устаревший, перезаписать):
   параллельные запуски невозможны. На GitHub Actions дополнительно concurrency group.

## 8. Обработка ошибок и коды выхода main.py
- exit 0: успех (даже если часть источников упала - это degraded, не failure;
  дайджест содержит блок "Source errors").
- exit 1: фатально (БД недоступна, все источники упали, guard сработал). Actions уронит
  workflow, GitHub пришлёт письмо.
- Логи: stdout, формат `%(asctime)s %(levelname)s %(name)s %(message)s`, уровень INFO.
- notify.py: Telegram sendMessage, parse_mode=HTML, сообщение > 3800 символов режется
  на части. Ошибка отправки в Telegram - лог ERROR, но exit-код не меняет.

## 9. Формат дайджеста (Telegram)
```
Job Radar - 04.07.2026
Собрано: 312 | новых: 47 | apply_first: 2 | good: 5

1. [87] AI Automation Specialist - Acme (remotive)
   $2000-3500/mo | Worldwide
   + title match, automation+zapier+api keywords, salary ok
   - mentions "3+ years python"
   <ссылка>
... (до 10 позиций, score >= 65; если таких нет - top-5 из maybe с пометкой)

Source errors: remoteok: HTTP 403 (если были)
```

## 10. config.yaml (структура)
```yaml
salary_min_usd_month: 1300
currency_rates_to_usd: {USD: 1.0, EUR: 1.08, GBP: 1.27}
hours_per_month: 160
weights: {title: 0.30, similarity: 0.25, salary: 0.15, remote: 0.10, seniority: 0.10, keywords: 0.10}
positive_titles: {"ai automation": 1.0, "automation specialist": 1.0, ...}
positive_keywords: [...]
negative_keywords: [...]
irrelevant_blacklist: [...]
us_only_patterns: [...]
digest: {top_n: 10, min_score: 65}
retention_days: {weak: 30, all_new: 90}
guards: {max_new_per_run: 2000, max_db_mb: 200}
```
Все словари и веса - ТОЛЬКО в config.yaml, не в коде. Это позволит крутить настройки
без перечитывания кода и это же аргумент на собеседовании (конфигурируемость).
