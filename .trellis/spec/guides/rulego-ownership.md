# Ownership and authority

Use ownership to prevent copied facts and accidental coupling. This repository
routes work to an authority; it is not a registry of live ecosystem state.

## Sources of truth

| Concern | Authority |
| --- | --- |
| Rule engine, component registration, endpoint, and editor behavior | Upstream `rulego/rulego` source and documentation at the host-selected release |
| Host build, Plugin ABI lock, SDK/runtime production, and host image | `killbus/rulego-server-docker` source, release records, and published artifacts |
| Generic ffmpeg-over-ip node contract and client integration | `killbus/rulego-ffmpeg-over-ip` source, compatibility record, tests, and release |
| Stable resource identity and publication lifecycle | `killbus/rulego-resource-origin` source, node contract, tests, and release |
| Indexed fragmented-media production | `killbus/rulego-indexed-media` source, examples, tests, and release (renamed from `rulego-indexed-vod` at v0.3.0; no alias, forwarding module, old-artifact selector, or cache fallback) |
| Provider-specific resolution | The deployed yt-dlp HTTP wrapper (or other provider adapter), its observed HTTP contract, and the rule that invokes it |
| Deployed rule, component, mapping, and endpoint state | Server configuration plus authenticated API read-back from that deployment |
| External-service behavior | The service's own contract and observed response |
| Player or media-server compatibility | The actual downstream consumer and its request/playback traces |

Before using a current value, re-inspect the authority. Never copy a current
host version, ABI tuple, artifact digest, node schema, credential, route body,
or deployment setting into this knowledge base as a second source of truth.

## Producer and consumer contracts

Ownership follows the lifecycle of a fact:

- The RuleGo host distributor produces the ABI lock, matching SDK/runtime
  images, and the host capable of loading plugins built against that contract.
- A plugin repository consumes that build contract and produces its node API,
  compatibility metadata, checksummed artifact, and verification evidence.
- A rule graph consumes registered node contracts and owns workflow ordering,
  provider policy, transformations, routing, and presentation composition.
- An independent service owns its protocol, process lifecycle, and service-side
  execution. A RuleGo node is an adapter to that service, not its replacement.
- A deployment owns enabled plugins, configuration, rules, endpoints, resource
  mappings, and public reachability.
- A downstream consumer owns its interpretation and playback behavior.

## Stable practice and volatile facts

Stable practice explains how to decide, build, and prove. Volatile facts answer
which version, artifact, rule revision, URL, or runtime setting is active now.
Only stable practice belongs here.

When evidence conflicts, prefer the closest authoritative current state:

1. deployed read-back for deployment state;
2. immutable release metadata for a released artifact;
3. committed source and tests for implementation behavior;
4. documentation and examples for intended usage;
5. conversation or recollection only as a lead to inspect.

## Repository boundary

A change belongs in the repository that can define and verify it without
reaching through another component's private implementation. Cross-repository
work may require coordinated tasks, but each repository retains its own
contract, tests, release, and commit history.
