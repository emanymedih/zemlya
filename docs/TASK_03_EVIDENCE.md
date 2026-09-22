# Task 3 evidence — execution environment

- Checked: 2026-09-22.
- Docker: client/server 29.8.0, context desktop-linux.
- C: free bytes: 744912535552; total bytes: 999008440320.
- Windows Schannel HTTPS: Geofabrik, Rosstat and GitHub returned HTTP 200.
- Container DNS/HTTPS: Geofabrik and GitHub returned HTTP 200.
- Container Rosstat TLS failed with CERTIFICATE_VERIFY_FAILED.
- Approved source-aware transport: Windows Schannel downloads Rosstat;
  Docker parses and normalizes local snapshots.
- Task 2 fallback was live-tested and returned 186532 records,
  including 15 Kaluga matches.
- Preflight was repeated successfully with the same status class.
- Repository smoke suite: 8/8 PASS.
- Machine report: geofabrik-worker-data/task03/task03-preflight-report.json
- Task 3 status: DONE with documented Rosstat transport constraint.
