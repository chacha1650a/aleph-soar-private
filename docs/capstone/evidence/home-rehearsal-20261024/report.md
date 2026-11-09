# Home synthetic integration rehearsal

Synthetic only; actual device calls: 0; live n8n: unverified.

- PASS normal: two cycles, stable replay, explicit close/new ticket, synthetic final release
- PASS overlap: different grouping owners: release held; claim relinquishment policy unresolved
- PASS after_target: pending survives restart; record-only repair; target receipts unchanged during repair
- PASS after_record: pending survives restart; record-only repair; target receipts unchanged during repair
- PASS record_unavailable: pending survives restart; record-only repair; target receipts unchanged during repair
- PASS ack_loss: pending survives restart; record-only repair; target receipts unchanged during repair
