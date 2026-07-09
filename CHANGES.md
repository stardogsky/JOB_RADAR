
## Diff 7 (2026-07-09) — Workable ATS + automatic Telegram mining
- Workable now supported as a collector: ats.py ATS_URL + normalize._norm_workable (public widget endpoint apply.workable.com/api/v1/widget/accounts/SLUG?details=true). Parses title/url/description/location/remote/date/department.
- Added confirmed company: workable/vivid-money (Vivid Money) — common RU-founder ATS.
- tools/mine_telegram.py: Workable moved from "unsupported gap" to reliable hosted {ats,slug} extraction.
- Telegram mining is now AUTOMATIC (part of every pipeline run, not manual). config.telegram_mine.enabled:true. ats.fetch() calls _discover_from_telegram(): fetches each t.me/s/<channel>, extracts hosted-ATS slugs, unions them with the static companies list before collecting. Non-fatal on failure; dead slugs isolated as before. Manual `python -m tools.mine_telegram` preview still available.
- Verified: workable normalizer (remote vs on-site), miner promotion of workable, py_compile of ats/normalize/mine_telegram.

## Diff 8 (2026-07-09) — +9 Telegram channels
- Added to telegram_mine.channels: remotegeekjob, remoteit, foranalysts, opento_data, pydevjobc, young_june, wntdan, it_vakansii_jobs, hiddengurus (now 11 total).
- Public preview verified (mineable): remotegeekjob, remoteit, foranalysts, opento_data, young_june, it_vakansii_jobs.
- No public t.me/s preview (kept in config, miner skips harmlessly): pydevjobc, wntdan, hiddengurus — verify usernames.
- Note: several channels link to non-hosted-ATS destinations (teletype.in, zohorecruit.eu, youngjunior.ru, vseti.app) which the miner does not extract; they yield fewer companies than zarubezhom_jobs/geekjobs.
