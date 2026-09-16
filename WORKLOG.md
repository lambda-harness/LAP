# Business Agent Expansion Worklog

## 2026-09-16 - Scope and protocol decisions

- Goal: deliver two external LAP Local 0.1 Agents and aggregate release ZIPs
  under `LAP/dist`; the Host remains free of business implementation code.
- Invoice Agent: Python, multiple JPEG/PNG/WebP/GIF/PDF inputs, PDF pages
  rendered locally, DeepSeek `deepseek-flash` vision extraction, validated
  invoice rows, and one downloadable XLSX artifact.
- AIBot Agent: Go, platform-specific binaries. Version 0.1 exposes general
  model chat, bounded log retrieval, and release-command planning.
- Security decision: release planning is read-only. Jenkins execution is not
  exposed until LAP/Harness can issue a run-scoped approval grant. Accepting a
  caller-supplied user ID would violate Host-owned identity and authorization.
- Credentials stay outside packages. The invoice Agent receives only the
  explicitly delegated `DEEPSEEK_API_KEY`; the AIBot Agent reads a package
  `config.yaml` supplied by the operator and never returns secret fields.

## Acceptance record

Status values: pending, passed, failed, blocked.

| Check | Status | Evidence |
| --- | --- | --- |
| Invoice manifest/package validation | passed | Harness package validator; sanitized ZIP SHA-256 `ea28fa38efc2507b32f6ae5bf36da723f76c240dc8249932185425b03689e1d5` |
| Invoice Local 0.1 exchange | passed | welcome, accepted, progress, artifact, succeeded, shutdown against the sample PDF |
| Multi-image/PDF input staging | passed | digest-checked multi-artifact regression test |
| Sample PDF extraction and XLSX round trip | passed | 20-digit invoice identifier matched the source; 159.25 + 9.55 = 168.80; XLSX reopened successfully |
| AIBot Windows amd64 build | passed | integrity SHA-256 `ff2918b5d8ebbd0ec2d98656955c742c4366e1302c8db1d10997eedd5f820725` |
| AIBot Linux amd64 build | passed | integrity SHA-256 `933c26b0250f5b871ffcdeee88185cca2ffd5d3b820fa9806da7f0bb3ff68263` |
| AIBot manifest/package validation | passed | both platform packages passed Harness validation |
| AIBot Local 0.1 conformance | passed | CORE-02, LOCAL-01/02/05/07; `release.plan` terminal succeeded with no side effect |
