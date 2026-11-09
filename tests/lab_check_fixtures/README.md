# Lab check synthetic fixtures

Every ID, event, execution and export here is synthetic test data. These files
are not the missing school-PC evidence or a teammate's report. They do not
resolve the historical S10 receipt or establish current device readiness.

- `s10`: B/D-only normalization check; no A/C wait.
- `s8-baseline`: five synthetic events, undefined detection, unavailable ticket
  store, and an out-of-window dry_run execution kept separate.
- `s8-postchange`: synthetic actual-call/effect/restoration observations;
  matching still requires human review and never sets final_complete.

Profiles ending in `.profile.json` import the adjacent structured export.
They never execute commands, call APIs, or read an actual application database.
