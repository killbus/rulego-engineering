# indexed-audio: measured evidence and design decisions

Session date: 2026-09-11. All live observations were made against the PVE
deployment (`rulego.docker.pve`, `ytdlp.docker.pve:8080`) and local ffmpeg on
the Windows workstation. Sample assets: `Z4tHPyZBC8g` (~42 min episode),
`J1z_eXpVD1w` (~21 min), `jNQXAC9IVRw` (19 s).

## 1. yt-dlp HTTP wrapper contract (observed)

`POST http://ytdlp.docker.pve:8080/run` with `{"args": [...]}` returns
`{"exit_code": 0, "stderr": "", "stdout": "<json line>"}` where `stdout`
parses as the `--print` template output.

- `--cookies /data/yt.txt` is mandatory for YouTube asset resolution.
- Audio-only selection that worked on both test assets:
  `-f 'ba[ext=m4a]/ba[ext=m4a]/ba' -S 'abr:1.0'`
  (prefer m4a audio, fall back to any audio; `J1z_eXpVD1w` resolved to
  `format_id 140-7`, `asr 44100`, `filesize 20210422`).
- `--print '%(.{id,title,duration,format_id,url,ext,protocol,vcodec,acodec,abr,asr,filesize,http_headers})j'`
  yields everything the chain and the Songloft ingest need in one call.

## 2. googlevideo itag-140 audio representation (measured)

For `Z4tHPyZBC8g` (format 140, AAC-LC 129.5 kbit/s, 44100 Hz, duration 2529):

| Property | Observation |
| --- | --- |
| Container | fragmented MP4: `ftyp@0 (24 B) → moov@24 (699 B) → sidx@723 (3080 B) → moof/mdat…`; first bytes `ftypdash` |
| Byte ranges | `Range: bytes=0-1023` → `206 Partial Content`, `Content-Range: bytes 0-1023/40930848`, `Accept-Ranges: bytes` |
| No Range header | returns `200` with the full body — always send an explicit Range when probing |
| SIDX timeline | 254 refs, timescale 44100, ~9.985 s each, all SAP type 1; summed duration 2529.047 s == resolver `duration` 2529 |
| Lease | `expire` URL param = +6 h from resolve; ytdlp does not refresh it |
| UA sensitivity | none (no-UA and browser-UA requests both got 206) |
| IP sensitivity | **locked** (`ip` param present) — Songloft cannot fetch the direct URL from a different host; the PVE side must transfer the bytes |

Consequence: the provider must proxy bytes. But per the design decision
below, it proxies them **streaming per request**, not by publishing a copy.

## 3. ffmpeg container-level forward to streamed fMP4 (measured)

```
ffmpeg -i <googlevideo_url> -map 0:a:0 -c copy \
       -movflags +empty_moov+frag_keyframe+default_base_moof+dash \
       -f mp4 pipe:1
```

Run against the real googlevideo URL (UA header forwarded from
`http_headers`), on `jNQXAC9IVRw`:

- exit 0, 309253 bytes for a 19 s track; wall time 2.35 s including the
  network fetch (the `-c copy` remux itself is container-level, near-zero CPU).
- Output box layout with `+empty_moov+frag_keyframe`:
  `ftyp(32 B) → moov(737 B, at head) → moof(3384 B) → mdat… → mfra(67 B, tail)`.
- Adding `+default_base_moof+dash` inserts a per-fragment `sidx(52 B)` after
  `moov` (`ftyp → moov → sidx → moof → mdat…`), which buffered-position
  seeking in players can use.
- ffprobe on the streamed output reports `format_name mov,mp4,m4a,3gp,3g2,mj2`
  and correct `duration 19.06 s`.
- ffprobe on a **head-only 5 KB slice** also reports the same duration —
  duration is derivable without reading the tail (no moov-at-tail problem).
- Songloft seek-stream simulation on the cached fMP4 file (this is
  `StreamSeekedMP3`'s actual argument shape: `-ss 5 -c:a libmp3lame -b:a 320k
  -write_xing 0 -f mp3 pipe:1`): exit 0, 564391 bytes, CBR estimate 14.11 s vs
  expected 14.06 s. The seek/transcode path accepts the fMP4 file unchanged.

Rejected variant: `resourceOrigin` per-track publication (`acquire → download
full track → commit → 307`). It stores ~40 MB per track for 24 h on the
RuleGo side next to Songloft's own LRU cache — a second cache whose data is
dead 90% of the time — and its only advantage (first-play Range seeking
against the 307 target) is worth less than the storage and lifecycle cost.

Rejected variant: extending `rulego-indexed-vod` with a `produceAudio`
operation. `writeInput` (init + refs sequential range copy) exists there, but
capability placement says composition belongs in the graph when existing
nodes express it: `ffmpegOverIp` already accepts arbitrary invocations and
the protocol's file operations run with the RuleGo process's filesystem
permissions, so a plain `ffmpeg -c copy` invocation covers the same need
without an ABI release cycle. Also "single-representation passthrough" does
not belong in a repository named indexed-**vod** (dual-representation TS).

## 4. Chain shape (from the measured facts)

```
GET /youtube/:videoId/audio.m4a
  → endpoint (wait:true, ffmpegOverIpResponse)
  → lease-check: ChainCache 'indexed-audio:youtube:{id}:lease'
       hit  → skip to ffmpegOverIp
       miss → restApiCall ytdlp /run (§1 args)
            → normalize: vcodec==='none', acodec!=='none', protocol==='https',
              id===videoId, duration>0
              fingerprint = 'indexed-audio-v1:' + format_id + ':' + duration + ':' + asr
              lease TTL = expire − 5 min (floor 10 min, cap 6 h)
  → ffmpegOverIp: ffmpeg -i <lease.url> -map 0:a:0 -c copy
       -movflags +empty_moov+frag_keyframe+default_base_moof+dash
       -f mp4 pipe:1        (UA forwarded from lease.http_headers)
  → 200 audio/mp4 chunked (ffmpegOverIpResponse writes/flushes stdout)
```

- No `resourceOrigin`, no 307/202/410 lifecycle, no storage on the RuleGo side.
- fingerprint intentionally derives from resolver metadata, not content
  hashes: hashing requires the full download the chain deliberately avoids.
- Songloft ingest: `Type=remote`, `url = http://rulego.docker.pve/youtube/{id}/audio.m4a`,
  `dedupKey = 'youtube:{id}'` (== sourceKey), `duration` from resolver (skips
  ffprobe probing), `sourceData` carries `{provider, format_id, asr}`.
- Songloft first play: existing `ServeRemoteResourceWithCache` 200-chunked
  path (tee into `music_cache`). Second play: served from cache with full
  Range/seek/transcode support (verified by the seek-stream simulation above).
- Uncached first play cannot serve Range (chunked, no Content-Length) — the
  same physics as every existing remote source; not a regression.

## 5. Deployment facts relied on

- `ffmpegOverIp` node v0.2.0 (`killbus/rulego-ffmpeg-over-ip`): accepts
  `{program, args, stdinBase64}`; stdout/stderr stream on the `Stream`
  relation; `ffmpegOverIpResponse` REST processor writes stdout to the HTTP
  response. Client-side file operations (`client/files.go`) use the RuleGo
  process's filesystem permissions — not needed for this chain (no files).
- `indexedVod` v0.2.0 and the `youtube-hls` example chain remain the video
  path; this audio chain is a separate, parallel chain (keys/URLs do not
  collide).
- RuleGo Server v0.37.0 static mappings return 405 for HEAD; irrelevant here
  because the endpoint serves bytes itself (no static mapping in this chain).

## 6. Open items

- e2e on the deployed host: remote ffmpeg inside the ffmpeg-over-ip container
  fetching googlevideo directly (radio transcode proves the form; this chain
  needs its own run).
- Whether `-movflags +dash` vs `+empty_moov+frag_keyframe` alone matters for
  the actual Songloft players (mpv/ExoPlayer/AVPlayer) — both produce
  moov-at-head; sidx presence is a bonus for buffered-position seeking.
- ytdlp resolve frequency: expected ≤2/day per asset with the 6 h lease;
  watch for rate-limit effects if a user seeks across many cold assets.
