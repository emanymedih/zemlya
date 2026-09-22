# Task 3 evidence — execution environment

- Checked: 2026-09-22.
- Docker: client/server 29.8.0, context desktop-linux.
- C: free bytes: 744912535552; total bytes: 999008440320.
- Windows Schannel HTTPS: Geofabrik, Rosstat and GitHub returned HTTP 200.
- Container DNS/HTTPS: Geofabrik and GitHub returned HTTP 200.
- Container Rosstat direct TLS failed with CERTIFICATE_VERIFY_FAILED.
- Host-TLS-to-Docker-parse fallback works for Task 2.
- Preflight was repeated successfully with the same status class.
- Repository smoke suite after schema fix: 9/9 PASS.
- Machine report: geofabrik-worker-data/task03/task03-preflight-report.json
- Task 3 status: PARTIAL / BLOCKED until direct container TLS is fixed.
