# Local control API candidate rehearsal

Synthetic only; actual device calls: 0; live n8n: unverified.

- PASS normal: two cycles, stable replay, explicit close/new ticket, synthetic final release
- PASS overlap: different grouping owners: release held; claim relinquishment policy unresolved
- PASS after_target: pending survives restart; record-only repair; target receipts unchanged during repair
- PASS after_record: pending survives restart; record-only repair; target receipts unchanged during repair
- PASS record_unavailable: pending survives restart; record-only repair; target receipts unchanged during repair
- PASS ack_loss: pending survives restart; record-only repair; target receipts unchanged during repair
- PASS shared_last_owner: candidate policy: logical withdrawal, one fake release, all C owner records verified; no target recall in repair
- PASS shared_new_owner: candidate policy: logical withdrawal, one fake release, all C owner records verified; no target recall in repair
- PASS shared_retained_owner: candidate policy: logical withdrawal, one fake release, all C owner records verified; no target recall in repair
- PASS shared_after_target: candidate policy: logical withdrawal, one fake release, all C owner records verified; no target recall in repair
- PASS shared_after_first_record: candidate policy: logical withdrawal, one fake release, all C owner records verified; no target recall in repair
- PASS shared_after_book_complete: candidate policy: logical withdrawal, one fake release, all C owner records verified; no target recall in repair
- PASS api_auth_and_idempotency: candidate auth/scope/idempotency/recovery checked against C test clients; no real target
- PASS api_cancel_before_target: candidate auth/scope/idempotency/recovery checked against C test clients; no real target
- PASS api_repair_after_target: candidate auth/scope/idempotency/recovery checked against C test clients; no real target
- PASS api_repair_after_first_record: candidate auth/scope/idempotency/recovery checked against C test clients; no real target
- PASS api_repair_after_book_complete: candidate auth/scope/idempotency/recovery checked against C test clients; no real target
