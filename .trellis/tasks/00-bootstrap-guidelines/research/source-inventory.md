# Current authority inventory

Inspected on 2026-08-30 from sibling working trees and their current committed
documentation. Re-inspect the source repository before relying on a volatile
value.

| Concern | Repository | Current authoritative paths |
| --- | --- | --- |
| RuleGo plugin host, ABI lock, SDK/runtime production | `killbus/rulego-server-docker` | `plugin-abi.lock`, `plugin-abi-release.json` workflow artifact, `README.md`, `scripts/plugin-abi*.sh`, `scripts/rulego-plugin-build`, Plugin ABI workflows |
| Generic ffmpeg-over-ip invocation | `killbus/rulego-ffmpeg-over-ip` | `README.md`, `COMPATIBILITY.md`, `compatibility.json`, `plugin-abi-release.json`, client and plugin packages, CI/release workflows |
| Stable resource identity and publication lifecycle | `killbus/rulego-resource-origin` | `README.md`, node tests, `compatibility.json`, `plugin-abi-release.json`, CI/release workflows |
| Indexed fragmented-MP4 VOD segment production | `killbus/rulego-indexed-vod` | `README.md`, producer/source tests, `examples/youtube-hls/chain.json`, `tests/e2e-hls-seek.sh`, compatibility and Plugin ABI records |
| Rule engine/component/endpoint behavior | `rulego/rulego` | Source and documentation at the host-selected release |
| Provider resolution | Deployed yt-dlp HTTP wrapper and rule chain | HTTP request/response contract and deployed rule read-back |
| Consumer behavior | Operator-controlled clients | Actual HTTP traces and playback observations |

## Stable observations

- Go dynamic plugins are loaded by the compiled RuleGo host; compatibility is
  a build-contract property, not a promise implied by the `.so` suffix.
- The host distributor owns one ABI lock and publishes matching immutable SDK
  and runtime images. Plugin repositories consume those digests and prove their
  own artifacts.
- Rule graphs own workflow and provider policy. Plugins own reusable missing
  capabilities. Independent processes keep their service boundary.
- `resourceOrigin` owns stable publication identity/lifecycle while RuleGo's
  static mapping owns byte transfer.
- `indexedVod` begins after source normalization and produces one bounded
  member; provider resolution and manifest presentation remain outside it.
- Relevant multi-plugin smoke tests are required because co-loaded Go plugins
  may share package identities even when their node contracts are independent.
