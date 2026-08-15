# Smoke test: alert semantics

**Date (UTC):** 2026-08-15T13:49:25Z  
**HEAD:** `d2a13c68092032fb6d84acc4bdb88ed429ed7200`  
**Checkout stayed on:** `cursor/self-hosted-mousewatcher`

## Confirmed present

- `AGENTS.md`
- `.cursor/rules/disney-session-protection.mdc`

## Command

```bash
python3 -m unittest tests.test_alert_semantics
```

## Result

PASS — 37 tests, 0.005s

```
.....................................
----------------------------------------------------------------------
Ran 37 tests in 0.005s

OK
```

## Not done

No merge to `main`, no deploy, no SSH, no `disney_bot.py` / `seed_disney_session.py` / `playwright install`, no secrets added or requested.
