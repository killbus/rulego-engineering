"""Bounded two-viewer same-program diagnostic collector; never an AC5 verdict."""

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


MEDIA_SECONDS = 360
PROGRESS_TOLERANCE_SECONDS = 1
MIN_PROGRESS_SECONDS = MEDIA_SECONDS - PROGRESS_TOLERANCE_SECONDS
MIN_OVERLAP_SECONDS = MIN_PROGRESS_SECONDS
PLAYBACK_RATE_ASSUMPTION = "approximately_1x"
WALL_SECONDS = 540
POLL_SECONDS = 1.0
HTTP_TIMEOUT = 3.0
MAX_RESPONSE = 8 * 1024 * 1024
RESOURCE_ORIGIN_VERSION = "0.2.1"
CHILD_TTL_MS = 120000
PARENT_TTL_MS = 21600000
MAX_RETAINED_BYTES = 536870912
VIEWER_LABELS = ("viewer-a", "viewer-b")
START_POSITIONS = (0, 600)
LAUNCH_WINDOW_SECONDS = 2.0
CLEANUP_RESERVE_SECONDS = 12.0
SCOPE = "two_viewer_same_program_different_positions_not_AC5"
NODES = (
    "manifest-request", "source-resolver", "source-resolver-retry", "inspect",
    "parent-origin", "parent-lookup", "initial-resolve", "parent-missing",
    "segment-request", "child-acquire-request", "child-origin",
    "segment-source-switch", "produce", "stale-switch", "refresh-resolver",
    "refresh-resolver-retry", "refresh-inspect", "refresh-produce", "commit",
    "production-fail-request", "production-fail", "request-error",
)
KINDS = (
    "storage_limit", "wait_timeout", "production_timeout", "parent_unavailable",
    "source_stale", "source_unavailable", "invalid_publication", "stale_generation",
    "invalid_request", "not_found", "publish_failed", "persistence_failed",
    "production_failed", "canceled", "cancelled", "internal_error",
)
LOG_LINE = re.compile(r"^\[\s*(\d+(?:\.\d+)?)\]\[([a-z])\]\[([^\]]+)\] (.*)$")


def utc(epoch=None):
    return datetime.fromtimestamp(time.time() if epoch is None else epoch, timezone.utc).isoformat()


def number(value):
    try:
        result = float(value)
        return result if not isinstance(value, bool) and math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        return None
    if value in (os.environ.get("RULEGO_USER"), os.environ.get("RULEGO_PASSWORD")):
        return None
    return value


def timestamp(value):
    if isinstance(value, (int, float)):
        return number(value)
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT[\d:.]+(?:Z|[+-]\d\d:\d\d)", value):
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value
        except ValueError:
            pass
    return None


def category(value):
    text = str(value).lower()
    for kind in KINDS:
        if re.search(r"\b" + kind + r"\b", text):
            return kind
    if "timed out" in text or "timeout" in text or "deadline exceeded" in text:
        return "timeout"
    if "context canceled" in text or "context cancelled" in text:
        return "canceled"
    match = re.search(r"\bhttp(?: error)?[: ]+(\d{3})\b", text)
    if match:
        return "http_" + match[1]
    return "unclassified_error" if value else None


def fetch_error(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return "http_" + str(exc.code)
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
        return "timeout"
    if isinstance(exc, (ValueError, json.JSONDecodeError)):
        return "invalid_response"
    return "network_error" if isinstance(exc, OSError) else "collector_error"


def object_value(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return {}
    return value if isinstance(value, dict) else {}


def descriptor(value):
    """Never traverse source/configuration/body/member URLs or arbitrary strings."""
    result = {}
    for key in ("resourceId", "generation", "parentId", "parentResourceId", "videoId", "revision"):
        cleaned = safe_id(value.get(key))
        if cleaned is not None:
            result[key] = cleaned
    for key in ("index", "segment", "byteSize", "bytes", "size"):
        cleaned = number(value.get(key))
        if cleaned is not None and cleaned >= 0:
            result[key] = cleaned
    for key in ("publishBy", "publishedAt", "expiresAt"):
        cleaned = timestamp(value.get(key))
        if cleaned is not None:
            result[key] = cleaned
    state = value.get("state", value.get("resourceOriginState"))
    if state in ("ready", "pending", "failed"):
        result["state"] = state
    for key in ("kind", "failureKind"):
        if value.get(key):
            result[key] = value[key] if value[key] in KINDS else "unclassified_kind"
    return result


def sanitize_event(row, node):
    msg = object_value(row.get("msg"))
    data = object_value(msg.get("data"))
    metadata = object_value(msg.get("metadata"))
    error = row.get("err") or metadata.get("errorMsg")
    # Error bodies may contain credentials/URLs; only classify in memory.
    if not error and (data.get("kind") in KINDS or data.get("state") == "failed"):
        error = data.get("message") or data.get("kind") or data.get("failureKind")
    resolver_failed = (node in ("source-resolver", "source-resolver-retry", "refresh-resolver", "refresh-resolver-retry")
                       and row.get("flowType") == "OUT" and number(data.get("exit_code")) not in (None, 0))
    clean = {
        "nodeId": node, "msgId": safe_id(row.get("msgId")),
        "messageId": safe_id(msg.get("id")), "serverTsMs": number(row.get("ts")),
        "flowType": row.get("flowType") if row.get("flowType") in ("IN", "OUT") else "unknown",
        "relation": row.get("relationType") if row.get("relationType") in
        ("Success", "Failure", "Produce", "True", "False", "Other") else "other",
        "data": descriptor(data), "metadata": descriptor(metadata),
        "errorCategory": "resolver_exit_failure" if resolver_failed and not error else category(error),
        "messageParsed": bool(msg),
    }
    clean["failureSignal"] = bool(error or resolver_failed or clean["data"].get("state") == "failed" or
                                  clean["metadata"].get("state") == "failed" or
                                  (clean["flowType"] == "OUT" and clean["relation"] == "Failure"))
    # Raw fields are used only for dedup, never written. IN and OUT remain distinct.
    clean["eventId"] = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    return clean


class JsonLines:
    def __init__(self, path):
        self.file = path.open("x", encoding="utf-8", buffering=1)
        self.lock = threading.Lock()

    def write(self, value):
        with self.lock:
            self.file.write(json.dumps(value, ensure_ascii=True, allow_nan=False) + "\n")
            self.file.flush()

    def close(self):
        with self.lock:
            self.file.close()


class IncrementalText:
    """Read complete appended lines once, preserving a partial final line."""

    def __init__(self, path):
        self.path = Path(path)
        self.offset = 0
        self.pending = ""

    def read_lines(self, final=False):
        if not self.path.exists():
            return []
        with self.path.open("rb") as file:
            file.seek(self.offset)
            chunk = file.read()
            self.offset = file.tell()
        self.pending += chunk.decode("utf-8", errors="replace")
        lines = []
        start = 0
        for match in re.finditer(r"\r\n|\r|\n", self.pending):
            lines.append(self.pending[start:match.start()])
            start = match.end()
        self.pending = self.pending[start:]
        if final and self.pending:
            lines.append(self.pending)
            self.pending = ""
        return [line for line in lines if line]


class TailTracker:
    def __init__(self):
        self.seen = set()
        self.previous = None
        self.last_ok = None
        self.failed_since_ok = False

    def accept(self, events, total, elapsed, error=None):
        flags = []
        if error:
            self.failed_since_ok = True
            return [], {"errorCategory": error, "continuity": "uncertain_fetch_failure",
                        "flags": ["fetch_failed"], "newEvents": 0}
        keys = {event["eventId"] for event in events}
        fresh = []
        for event in events:
            if event["eventId"] not in self.seen:
                fresh.append(event)
                self.seen.add(event["eventId"])
        if total > len(events):
            flags.append("unfetched_retained_rows")
        if len(keys) < len(events):
            flags.append("identical_rows_indistinguishable")
        if any(event["serverTsMs"] is None or not event["messageParsed"] for event in events):
            flags.append("missing_event_fields")
        overlap = len(keys & (self.previous or set()))
        if self.previous and not overlap:
            flags.append("possible_overwrite_or_reset" if keys else "tail_cleared")
        if self.failed_since_ok:
            flags.append("recovering_after_fetch_failure")
        gap = None if self.last_ok is None else elapsed - self.last_ok
        if gap is not None and gap > POLL_SECONDS + HTTP_TIMEOUT + 0.5:
            flags.append("long_poll_gap")
        times = [event["serverTsMs"] for event in events if event["serverTsMs"] is not None]
        diagnostic = {
            "returnedRows": len(events), "reportedTotal": total, "newEvents": len(fresh),
            "overlapRows": overlap, "previousRowsDisappeared": len((self.previous or set()) - keys),
            "secondsSinceSuccessfulPoll": gap, "oldestServerTsMs": min(times, default=None),
            "newestServerTsMs": max(times, default=None), "flags": flags,
            "continuity": "uncertain" if flags else ("baseline_only" if self.previous is None else "tail_overlap_only"),
            "ledgerComplete": False,
        }
        self.previous, self.last_ok, self.failed_since_ok = keys, elapsed, False
        return fresh, diagnostic


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_tail(base, chain, node, auth):
    query = urllib.parse.urlencode({"chainId": chain, "nodeId": node, "page": 1, "size": 200})
    req = urllib.request.Request(base + "/api/v1/logs/debug?" + query,
                                 headers={"Authorization": auth, "Accept": "application/json"})
    # Never forward Basic credentials to a redirect or environment-configured proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(req, timeout=HTTP_TIMEOUT) as response:
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError("response_too_large")
    body = json.loads(raw)
    if isinstance(body, dict) and body.get("items") is None and body.get("total") == 0:
        body["items"] = []
    if not isinstance(body, dict) or not isinstance(body.get("items"), list):
        raise ValueError("invalid_items")
    if not all(isinstance(row, dict) for row in body["items"]):
        raise ValueError("invalid_row")
    total = number(body.get("total"))
    if total is None or total < len(body["items"]):
        raise ValueError("invalid_total")
    return [sanitize_event(row, node) for row in body["items"]], total


def fetch_json(url, auth):
    req = urllib.request.Request(url, headers={"Authorization": auth, "Accept": "application/json"})
    # Same no-redirect/no-proxy contract as telemetry; raw bodies are hashed only.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(req, timeout=HTTP_TIMEOUT) as response:
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError("response_too_large")
    body = json.loads(raw)
    if not isinstance(body, (dict, list)):
        raise ValueError("invalid_response")
    return body


def sanitize_text(value):
    return value if isinstance(value, str) and re.fullmatch(r"[\x20-\x7e]{1,256}", value) else None


def parse_component_policy(body):
    candidates = body if isinstance(body, list) else []
    if not candidates:
        root = object_value(body)
        for key in ("nodes", "items", "components"):
            if isinstance(root.get(key), list):
                candidates = root[key]
                break
        if not candidates:
            candidates = [root.get("component", root)]
    components = [object_value(value) for value in candidates]
    component = next((value for value in components
                      if value.get("type") == "resourceOrigin"), {})
    if not component and components:
        component = components[0]
    policy = object_value(component.get("configuration"))
    version = component.get("version")
    return component.get("type"), version, policy


def parse_shared_node_policy(body):
    """Select the unique resourceOrigin instance from the shared-nodes list."""
    root = object_value(body)
    nodes = root.get("items")
    if not isinstance(nodes, list):
        return "invalid_shared_nodes_envelope", None, {}
    matches = [object_value(node) for node in nodes
               if object_value(node).get("type") == "resourceOrigin"]
    if len(matches) != 1:
        return "ambiguous_shared_nodes_envelope", None, {}
    instance = matches[0]
    instance_id = safe_id(instance.get("id"))
    if instance_id != "resource-origin":
        return "ambiguous_shared_nodes_envelope", None, {}
    return instance.get("type"), instance_id, object_value(instance.get("configuration"))


def readback_policy(body):
    root = object_value(body)
    chain = object_value(root.get("ruleChain"))
    metadata = object_value(root.get("metadata"))
    nodes = metadata.get("nodes")
    if not isinstance(nodes, list):
        nodes = chain.get("nodes")
    connections = metadata.get("connections")
    if not isinstance(connections, list):
        connections = chain.get("connections")
    policy = {"nodeCount": len(nodes) if isinstance(nodes, list) else None,
              "connectionCount": len(connections) if isinstance(connections, list) else None,
              "acquire": [], "resourceOriginRoots": []}
    for node in nodes if isinstance(nodes, list) else []:
        item = object_value(node)
        node_id = item.get("id")
        configuration = object_value(item.get("configuration"))
        if item.get("type") == "resourceOrigin":
            policy["resourceOriginRoots"].append({
                "id": safe_id(node_id),
                "root": sanitize_text(configuration.get("root")),
            })
        script = configuration.get("jsScript")
        if node_id in ("child-acquire-request", "parent-acquire-request") and isinstance(script, str):
            ttls = tuple(sorted({int(match) for match in re.findall(r"'ttlMs':(\d+)", script)}))
            timeouts = tuple(sorted({int(match) for match in re.findall(r"'productionTimeoutMs':(\d+)", script)}))
            maxes = tuple(sorted({int(match) for match in re.findall(r"'maxBytes':(\d+)", script)}))
            if len(ttls) == 1:
                policy["acquire"].append({"id": node_id, "ttlMs": ttls[0],
                                          "productionTimeoutMs": timeouts[0] if len(timeouts) == 1 else None,
                                          "maxBytes": maxes[0] if len(maxes) == 1 else None})
    roots = policy["resourceOriginRoots"]
    policy["rootConfiguration"] = {
        "expected": "ref://resource-origin",
        "allMatch": bool(roots) and all(row.get("root") == "ref://resource-origin" for row in roots),
    }
    return policy


def preflight(out, args, auth):
    started = utc()
    component = fetch_json(args.base_url + "/api/v1/components", auth)
    shared_nodes = fetch_json(args.base_url + "/api/v1/shared-nodes?page=1&size=100", auth)
    chain = fetch_json(args.base_url + "/api/v1/rules/" + args.chain, auth)
    component_type, version, policy = parse_component_policy(component)
    shared_node_type, shared_node_id, shared_policy = parse_shared_node_policy(shared_nodes)
    chain_policy = readback_policy(chain)
    checks = {
        "resourceOriginVersion": version == RESOURCE_ORIGIN_VERSION,
        "componentType": component_type == "resourceOrigin",
        "sharedNodeInstance": shared_node_type == "resourceOrigin",
        "sharedNodeId": shared_node_id == "resource-origin",
        "maxRetainedBytes": number(shared_policy.get("maxRetainedBytes")) == MAX_RETAINED_BYTES,
        "rootConfiguration": chain_policy["rootConfiguration"]["allMatch"],
        "childTtlMs": any(row.get("id") == "child-acquire-request" and
                          row.get("ttlMs") == CHILD_TTL_MS for row in chain_policy["acquire"]),
        "parentTtlMs": any(row.get("id") == "parent-acquire-request" and
                           row.get("ttlMs") == PARENT_TTL_MS for row in chain_policy["acquire"]),
    }
    record = {
        "capturedUtc": started,
        "status": "accepted" if all(checks.values()) else "mismatch",
        "checks": checks,
        "accepted": all(checks.values()),
        "resourceOriginVersion": version if isinstance(version, str) else None,
        "resourceOriginPolicy": {"maxRetainedBytes": number(shared_policy.get("maxRetainedBytes")),
                                 "maxResourceBytes": number(shared_policy.get("maxResourceBytes")),
                                 "maxProductionMs": number(shared_policy.get("maxProductionMs")),
                                 "maxTtlMs": number(shared_policy.get("maxTtlMs"))},
        "resourceOriginInstanceId": shared_node_id,
        "chainPolicy": chain_policy,
        "chainSha256": hashlib.sha256(json.dumps(chain, sort_keys=True, ensure_ascii=True).encode()).hexdigest(),
        "componentsSha256": hashlib.sha256(json.dumps(component, sort_keys=True, ensure_ascii=True).encode()).hexdigest(),
        "sharedNodesSha256": hashlib.sha256(json.dumps(shared_nodes, sort_keys=True, ensure_ascii=True).encode()).hexdigest(),
        "knownInventory": None, "diskHeadroom": None,
        "baselineLabel": "not-certified-cold; no cache cleared",
        "existingTraffic": {
            "knownLocalMpvProcesses": None,
            "knownLocalMpvProcessesState": "not_measured",
            "otherHosts": "unknown",
        },
    }
    with (out / "preflight.json").open("x", encoding="utf-8") as file:
        json.dump(record, file, indent=2, ensure_ascii=True, allow_nan=False)
    return record


def poll_worker(args):
    """Isolate socket/DNS calls so parent can bound even an uninterruptible fetch."""
    out = Path(args.out)
    events, polls = JsonLines(out / "server-events.jsonl"), JsonLines(out / "polls.jsonl")
    stop = threading.Event()
    baseline_done = {node: threading.Event() for node in NODES}
    baseline_ok = {}
    auth = "Basic " + base64.b64encode((os.environ["RULEGO_USER"] + ":" +
                                     os.environ["RULEGO_PASSWORD"]).encode()).decode()

    def monitor(node):
        tracker = TailTracker()
        phase = "baseline"
        while True:
            started = time.time()
            try:
                rows, total = fetch_tail(args.base_url, args.chain, node, auth)
                fresh, diagnostic = tracker.accept(rows, total, time.monotonic())
            except Exception as exc:
                fresh, diagnostic = tracker.accept([], 0, time.monotonic(), fetch_error(exc))
                if isinstance(exc, urllib.error.HTTPError):
                    exc.close()
            ended = time.time()
            for event in fresh:
                events.write(dict(event, observedUtc=utc(ended), capturePhase=phase))
            polls.write(dict(diagnostic, nodeId=node, phase=phase, startedUtc=utc(started),
                             endedUtc=utc(ended), durationSeconds=ended - started))
            if phase == "baseline":
                baseline_ok[node] = "errorCategory" not in diagnostic
                baseline_done[node].set()
            if phase == "final":
                break
            stop.wait(max(0, POLL_SECONDS - (ended - started)))
            phase = "final" if stop.is_set() else "monitor"

    threads = [threading.Thread(target=monitor, args=(node,), daemon=True) for node in NODES]
    for thread in threads:
        thread.start()

    def baseline_receipt():
        for done in baseline_done.values():
            done.wait()
        with (out / "baseline.json").open("x", encoding="utf-8") as file:
            json.dump({"nodes": baseline_ok, "allSucceeded": all(baseline_ok.values())}, file)

    threading.Thread(target=baseline_receipt, daemon=True).start()
    try:
        sys.stdin.readline()
    finally:
        stop.set()
        deadline = time.monotonic() + 7
        for thread in threads:
            thread.join(max(0, deadline - time.monotonic()))
        # Daemon threads cannot outlive this isolated process. Parent also enforces a timeout.
        for node, thread in zip(NODES, threads):
            if thread.is_alive():
                polls.write({"nodeId": node, "phase": "shutdown", "flags": ["fetch_thread_cut_off"],
                             "continuity": "uncertain", "endedUtc": utc()})
    return 0


def media_progress(line):
    match = re.search(r"(?:VIEWER-[AB]|BASELINE) pos=(\S+)", line)
    if match:
        token = match[1]
        duration = re.fullmatch(r"(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)", token)
        if duration:
            hours = int(duration[1] or 0)
            return hours * 3600 + int(duration[2]) * 60 + float(duration[3])
        return number(token)
    match = re.search(r"\b(?:AV|V|A):\s*(\d+):(\d+):(\d+(?:\.\d+)?)", line)
    if match:
        return int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])
    return None


class PlayerEvidence:
    def __init__(self, emit, spawn_epoch, start=0):
        self.emit = emit
        self.spawn_epoch, self.start = spawn_epoch, start
        self.max_position = None
        self.max_position_source = None
        self.explicit_marker_non_progressing = False
        self.first_advance = None
        self.advance_source = None
        self.buffer_enter = None
        self.buffer_durations = []
        self.counts = Counter()
        self.phase_counts = Counter()
        self.success = False
        self.resolution = None
        self.log_lines = 0
        self.verbose_cplayer = False
        self.open_counts = Counter()
        self.lock = threading.RLock()

    def record(self, kind, elapsed, **fields):
        self.counts[kind] += 1
        phase = ("midplay" if self.first_advance is not None and elapsed >= self.first_advance
                 else "startup_or_unconfirmed")
        self.phase_counts[phase] += 1
        self.emit(dict(kind=kind, playerElapsedSeconds=elapsed,
                       estimatedUtc=utc(self.spawn_epoch + elapsed), observedUtc=utc(),
                       phase=phase,
                       **fields))

    def progress(self, line, elapsed):
        position = media_progress(line)
        if position is None:
            return
        marker = re.search(r"(?:VIEWER-[AB]|BASELINE) pos=(\S+)", line)
        source = "termStatus" if marker else "playerClock"
        with self.lock:
            # mpv can emit either duration or numeric time-pos; retain the source
            # and let a higher direct reading supersede an earlier zero.
            if self.max_position is None or position > self.max_position:
                self.max_position = position
                self.max_position_source = source
            elif source == "termStatus" and position == 0 and self.max_position > 0:
                self.explicit_marker_non_progressing = True
            if self.first_advance is None and position > self.start + 0.25:
                self.first_advance = elapsed
                self.advance_source = source
            self.record("progress", elapsed, positionSeconds=position,
                        positionSource=source,
                        relativeSeconds=max(0, position - self.start))

    def log(self, line):
        match = LOG_LINE.match(line)
        if not match:
            return
        elapsed, level, module, text = float(match[1]), match[2], match[3], match[4]
        with self.lock:
            self.log_lines += 1
            self.verbose_cplayer |= module == "cplayer" and level in ("v", "d", "t")
            if "Enter buffering" in text:
                if self.buffer_enter is not None:
                    self.record("buffer_unpaired_enter", elapsed)
                self.buffer_enter = elapsed
                self.record("buffer_enter", elapsed)
            end = re.search(r"End buffering \(waited ([\d.]+) secs\)", text)
            if end:
                duration = float(end[1])
                self.buffer_durations.append(duration)
                interval_start = self.buffer_enter if self.buffer_enter is not None else elapsed - duration
                self.record("buffer_end", elapsed, durationSeconds=duration,
                            pairedEnter=self.buffer_enter is not None,
                            intervalStartElapsed=interval_start,
                            intervalPhase="midplay" if self.first_advance is not None and interval_start >= self.first_advance else "startup_or_unconfirmed")
                self.buffer_enter = None
            if "Still buffering" in text:
                self.record("buffer_still", elapsed)
            status = re.search(r"HTTP error (\d{3})", text)
            if status:
                self.record("http_error", elapsed, status=int(status[1]))
            failure = re.search(r"Failed to open segment (\d+)", text)
            if failure:
                self.record("segment_open_failed", elapsed, index=int(failure[1]))
            urls = re.findall(r"https?://[^\s'\"]+", text)
            index = None
            if urls:
                segment = re.search(r"/(\d+)\.ts$", urllib.parse.urlsplit(urls[0]).path)
                index = int(segment[1]) if segment else None
            if "Opening" in text and urls and "Opening done" not in text:
                # Repeated opens are not automatically retries (probe/seek/redirect also reopen).
                repeated = False
                if index is not None:
                    repeated = self.open_counts[index] > 0
                    self.open_counts[index] += 1
                self.record("http_open", elapsed, index=index, repeatedIndex=repeated)
            if "retrying with new connection" in text or "keepalive request failed" in text:
                self.record("http_retry", elapsed, index=index, errorCategory=category(text))
            if "Opening done:" in text:
                self.record("open_complete", elapsed)
            if "finished playback, success" in text:
                self.success = True
                self.record("playback_success", elapsed)
            elif "finished playback," in text or "Opening failed or was aborted" in text:
                self.record("playback_failure", elapsed)
            resolution = re.search(r"VO: \[null\] (\d+)x(\d+)", text)
            if resolution:
                self.resolution = [int(resolution[1]), int(resolution[2])]
                self.record("video_output", elapsed, width=self.resolution[0], height=self.resolution[1])
            if "Audio device underrun detected" in text:
                self.record("null_audio_underrun", elapsed)
            elif level in ("e", "f") and not (status or failure):
                self.record("player_error", elapsed, errorCategory=category(text))

    def summary(self, exit_code):
        relative = None if self.max_position is None else max(0, self.max_position - self.start)
        errors = sum(self.counts[k] for k in ("http_error", "segment_open_failed", "playback_failure", "player_error"))
        return {
            "exitCode": exit_code, "finishedPlaybackSuccess": self.success,
            "maxPositionSeconds": self.max_position,
            "maxPositionSource": self.max_position_source,
            "explicitMarkerNonProgressing": self.explicit_marker_non_progressing,
            "relativeProgressSeconds": relative,
            "targetMediaSeconds": MEDIA_SECONDS, "progressToleranceSeconds": 1,
            "reachedTargetWithinTolerance": relative is not None and relative >= MEDIA_SECONDS - 1,
            "resolution": self.resolution, "observed1080p": self.resolution == [1920, 1080],
            "counts": dict(self.counts), "phaseCounts": dict(self.phase_counts),
            "capturedErrorSignals": errors,
            "maxCompletedBufferingSeconds": max(self.buffer_durations, default=None),
            "openBufferIntervalStart": self.buffer_enter,
            "bufferTelemetry": "verbose_log_observed" if self.verbose_cplayer else "unknown",
            "continuity": "interruptions_observed" if errors or self.buffer_durations or self.buffer_enter is not None else "not_proven",
            "firstObservedAdvanceElapsed": self.first_advance,
            "firstObservedAdvanceSource": self.advance_source,
            "httpCompletions": "not_available_per_segment_from_this_log",
        }


def read_progress(pipe, player, spawn_mono):
    pending = b""
    while True:
        chunk = pipe.read1(8192)
        if not chunk:
            break
        pending += chunk
        lines = re.split(b"[\r\n]", pending)
        pending = lines.pop()
        for line in lines:
            player.progress(line.decode("utf-8", errors="replace"), time.monotonic() - spawn_mono)
        if len(pending) > 65536:
            pending = b""
    if pending:
        player.progress(pending.decode("utf-8", errors="replace"), time.monotonic() - spawn_mono)


def stop_owned(process):
    if process is None or process.poll() is not None:
        return False
    # PID is exclusively the still-live Popen child, never a process-name match.
    try:
        subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=2)
    return True


def load_jsonl(path):
    rows, bad = [], 0
    if not path.exists():
        return rows, 1
    with path.open(encoding="utf-8") as file:
        for line in file:
            try:
                rows.append(json.loads(line))
            except ValueError:
                bad += 1
    return rows, bad


def write_json_exclusive(path, value):
    with Path(path).open("x", encoding="utf-8") as file:
        json.dump(value, file, indent=2, ensure_ascii=True, allow_nan=False)


def sanitized_command(command):
    result = []
    for index, argument in enumerate(command):
        if index == 0:
            result.append(Path(argument).name)
        elif argument.startswith("--log-file="):
            result.append("--log-file=<temporary-per-viewer-log>")
        elif argument.startswith(("http://", "https://")):
            result.append("<media-url>")
        else:
            result.append(argument)
    return result


def launch_window_ok(timestamps):
    return len(timestamps) == 2 and max(timestamps) - min(timestamps) <= LAUNCH_WINDOW_SECONDS


def server_summary(out, spawn_epoch, end_epoch):
    events, bad_events = load_jsonl(out / "server-events.jsonl")
    polls, bad_polls = load_jsonl(out / "polls.jsonl")
    failures = [event for event in events if event.get("failureSignal")]
    in_window = [event for event in failures if spawn_epoch is not None and
                 event.get("serverTsMs") is not None and spawn_epoch * 1000 <= event["serverTsMs"] <= end_epoch * 1000]
    return {
        "capturedEvents": len(events), "capturedFailureSignalsAllSnapshots": len(failures),
        "failureSignalsInClientClockWindow": len(in_window),
        "windowFailureCategories": dict(Counter(event.get("errorCategory") or
                                                 event.get("data", {}).get("failureKind") or "unclassified_failure" for event in in_window)),
        "fetchFailures": sum(bool(row.get("errorCategory")) for row in polls),
        "coverageFlags": dict(Counter(flag for row in polls for flag in row.get("flags", []))),
        "missingFinalNodes": sorted(set(NODES) - {row.get("nodeId") for row in polls if row.get("phase") == "final"}),
        "invalidOrMissingJsonlRows": bad_events + bad_polls,
        "ledgerComplete": False, "inventory": "unknown_not_collected", "retainedBytes": None,
        "attribution": "node signals, not unique incidents; may include other clients; server clock offset unknown",
    }


def cross_viewer_summary(out, viewer_evidence):
    events, bad = load_jsonl(out / "server-events.jsonl")

    def stable_values(key):
        values = set()
        for event in events:
            for container in (event, object_value(event.get("data")), object_value(event.get("metadata"))):
                value = safe_id(container.get(key))
                if value is not None:
                    values.add(value)
        return sorted(values)

    observed_indices = {}
    for label, evidence in zip(VIEWER_LABELS, viewer_evidence):
        observed_indices[label] = sorted(evidence.open_counts) if evidence is not None else []
    return {
        "requestedRegions": [
            {"viewer": "viewer-a", "mediaStartSeconds": 0, "requestedIndex": 0},
            {"viewer": "viewer-b", "mediaStartSeconds": 600,
             "requestedIndex": "derived from runtime segment timeline"},
        ],
        "viewerObservedOpenIndices": observed_indices,
        "stableIdentifiers": {
            "msgIds": stable_values("msgId")[:100],
            "resourceIds": stable_values("resourceId")[:100],
            "generations": stable_values("generation")[:100],
        },
        "readyCommitEvents": sum(
            event.get("nodeId") == "commit" and
            object_value(event.get("data")).get("state") == "ready"
            for event in events
        ),
        "serverEventsAssignedToViewer": False,
        "associationRule": "stable identifiers only; temporal containment is not ownership proof",
        "serverClientClockOffset": "unknown",
        "invalidOrMissingJsonlRows": bad,
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="New evidence directory; existing path is refused")
    parser.add_argument("--base-url", default="http://rulego.docker.pve")
    parser.add_argument("--chain", default="sxYw0hmQDtSX")
    parser.add_argument("--video", default="3UJp1qfvL90")
    parser.add_argument("--labels", default=",".join(VIEWER_LABELS))
    parser.add_argument("--starts", default=",".join(str(value) for value in START_POSITIONS))
    parser.add_argument("--mpv", help="mpv.exe or mpv.com; prefer sibling mpv.exe for direct ownership")
    parser.add_argument("--_poll-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    url = urllib.parse.urlsplit(args.base_url)
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
        parser.error("base URL must be a plain HTTP(S) origin without credentials, path, query or fragment")
    args.base_url = args.base_url.rstrip("/")
    if not safe_id(args.chain) or not safe_id(args.video):
        parser.error("chain and video must be plain identifiers")
    labels = [value.strip() for value in args.labels.split(",")]
    starts = [number(value) for value in args.starts.split(",")]
    if len(labels) != 2 or len(set(labels)) != 2:
        parser.error("exactly two distinct viewer labels are required")
    if len(starts) != 2 or len(set(starts)) != 2 or any(value is None or value < 0 or not float(value).is_integer() for value in starts):
        parser.error("exactly two distinct non-negative integer start positions are required")
    if tuple(labels) != VIEWER_LABELS:
        parser.error("labels are fixed for this bounded gate")
    if tuple(int(value) for value in starts) != START_POSITIONS:
        parser.error("start positions are fixed for this bounded gate")
    if not os.environ.get("RULEGO_USER") or not os.environ.get("RULEGO_PASSWORD"):
        parser.error("set RULEGO_USER and RULEGO_PASSWORD in the environment")
    if os.name != "nt":
        parser.error("execution is Windows-only; offline parser tests are portable")
    return args


def run(args):
    executable = shutil.which(args.mpv) if args.mpv else (shutil.which("mpv.exe") or shutil.which("mpv.com"))
    if not executable:
        raise ValueError("mpv_not_found")
    executable = Path(executable).resolve()
    if executable.name.lower() not in ("mpv.exe", "mpv.com"):
        raise ValueError("unsupported_player")
    if executable.suffix.lower() == ".com" and executable.with_suffix(".exe").exists():
        executable = executable.with_suffix(".exe")
    if executable.suffix.lower() != ".exe":
        raise ValueError("direct_mpv_exe_required_to_avoid_detached_wrapper")
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    started, deadline = time.time(), time.monotonic() + WALL_SECONDS
    auth = "Basic " + base64.b64encode((os.environ["RULEGO_USER"] + ":" +
                                        os.environ["RULEGO_PASSWORD"]).encode()).decode()
    lifecycle = consumer = None
    helper = None
    viewer_processes = []
    viewer_evidence = []
    viewer_meta = []
    readers = []
    spawn_epochs = []
    spawn_return_epochs = []
    launch_records = []
    exit_code, stop_reason, helper_forced = None, "collector_error", False
    scratch = tempfile.TemporaryDirectory(prefix="two-viewer-hls-")
    cleanup_errors = []
    preflight_record = None
    preflight_failure = None
    abort_stage = None
    event_tail = None
    log_tails = [IncrementalText(Path(scratch.name) / f"{label}.log") for label in VIEWER_LABELS]

    def cleanup(action, label):
        try:
            return action()
        except Exception:
            cleanup_errors.append(label)
            return None

    def record_lifecycle(value):
        if lifecycle is not None:
            lifecycle.write(value)

    def abort(reason, stage):
        nonlocal stop_reason, abort_stage
        stop_reason, abort_stage = reason, stage

    def drain_log(final=False):
        for index, tail in enumerate(log_tails):
            if index < len(viewer_evidence) and viewer_evidence[index] is not None:
                for line in tail.read_lines(final=final):
                    viewer_evidence[index].log(line)

    try:
        lifecycle = JsonLines(out / "lifecycle.jsonl")
        consumer = JsonLines(out / "consumer-events.jsonl")
        try:
            preflight_record = preflight(out, args, auth)
        except Exception as exc:
            category = fetch_error(exc)
            if isinstance(exc, urllib.error.HTTPError):
                exc.close()
            preflight_failure = {
                "status": "failed",
                "accepted": False,
                "errorCategory": category,
                "checks": {},
            }
            abort("preflight_mismatch" if isinstance(exc, ValueError) and str(exc) == "preflight_mismatch"
                  else "preflight_unavailable", "preflight")
            record_lifecycle({"kind": "preflight_failed", "utc": utc(),
                              "errorCategory": category,
                              "collectorExceptionType": type(exc).__name__})
            return 2
        if not preflight_record["accepted"]:
            abort("preflight_mismatch", "preflight")
            record_lifecycle({"kind": "preflight_failed", "utc": utc(),
                              "errorCategory": "policy_mismatch"})
            return 2

        record_lifecycle({
            "kind": "run_start", "utc": utc(started), "videoId": args.video,
            "chainId": args.chain, "mediaSeconds": MEDIA_SECONDS, "wallLimitSeconds": WALL_SECONDS,
            "nodes": NODES, "pollSeconds": POLL_SECONDS, "httpSocketTimeoutSeconds": HTTP_TIMEOUT,
            "targetDebugRequestsPerSecond": len(NODES) / POLL_SECONDS,
            "instrumentationAffectsPerformance": True,
            "playbackRateAssumption": PLAYBACK_RATE_ASSUMPTION,
        })
        try:
            helper = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--_poll-worker",
                                       "--out", str(out), "--base-url", args.base_url,
                                       "--chain", args.chain, "--video", args.video], stdin=subprocess.PIPE,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as exc:
            record_lifecycle({"kind": "initial_telemetry_failed", "utc": utc(),
                              "errorCategory": fetch_error(exc),
                              "collectorExceptionType": type(exc).__name__})
            abort("initial_telemetry_unavailable", "initial_telemetry")
            return 2
        baseline_deadline = time.monotonic() + 10
        receipt = None
        while time.monotonic() < baseline_deadline and helper.poll() is None:
            try:
                receipt = json.loads((out / "baseline.json").read_text(encoding="utf-8"))
                break
            except (FileNotFoundError, ValueError):
                time.sleep(0.1)
        if not receipt or not receipt.get("allSucceeded"):
            record_lifecycle({"kind": "initial_telemetry_failed", "utc": utc(),
                              "errorCategory": "baseline_unavailable"})
            abort("initial_telemetry_unavailable", "initial_telemetry")
            return 2
        if helper.poll() is not None:
            record_lifecycle({"kind": "initial_telemetry_failed", "utc": utc(),
                              "errorCategory": "poll_helper_exited"})
            abort("initial_telemetry_unavailable", "initial_telemetry")
            return 2
        env = {key: value for key, value in os.environ.items() if key not in ("RULEGO_USER", "RULEGO_PASSWORD")}
        spawn_monos = []
        abort_stage = "launch"
        for label, position in zip(VIEWER_LABELS, START_POSITIONS):
            command = [str(executable), "--no-ytdl", f"--start={position}", f"--end={position + MEDIA_SECONDS}",
                       "--vo=null", "--ao=null", "--force-window=no", "--no-border", "--terminal=yes",
                       "--input-terminal=no", f"--term-status-msg={label.upper()} pos=${{=time-pos}}",
                       "--msg-level=all=v", "--log-file=" + str(Path(scratch.name) / f"{label}.log"),
                       args.base_url + "/youtube/" + args.video + "/index.m3u8"]
            spawn_epoch, spawn_mono = time.time(), time.monotonic()
            try:
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           stdin=subprocess.DEVNULL, env=env,
                                           creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception as exc:
                record_lifecycle({"kind": "player_launch_failed", "label": label, "utc": utc(),
                                  "errorCategory": fetch_error(exc),
                                  "collectorExceptionType": type(exc).__name__})
                abort("player_launch_failed", "launch")
                return 2
            spawn_returned = time.time()
            player = PlayerEvidence(consumer.write, spawn_epoch, start=position)
            viewer_processes.append(process)
            viewer_evidence.append(player)
            spawn_epochs.append(spawn_epoch)
            spawn_return_epochs.append(spawn_returned)
            spawn_monos.append(spawn_mono)
            command_record = sanitized_command(command)
            meta = {
                "label": label, "startPositionSeconds": position, "ownedPid": process.pid,
                "spawnRequestedUtc": utc(spawn_epoch), "spawnReturnedUtc": utc(spawn_returned),
                "command": command_record,
            }
            viewer_meta.append(meta)
            launch_records.append({"label": label, "positionSeconds": position,
                                   "spawnRequestedUtc": meta["spawnRequestedUtc"],
                                   "spawnReturnedUtc": meta["spawnReturnedUtc"],
                                   "pid": process.pid, "command": command_record})
            record_lifecycle({"kind": "player_spawn", "label": label, "positionSeconds": position,
                              "spawnRequestedUtc": meta["spawnRequestedUtc"],
                              "spawnReturnedUtc": meta["spawnReturnedUtc"],
                              "pid": process.pid, "player": executable.name,
                              "clockAlignment": "mpv log seconds plus spawn-request UTC; approximate"})
            reader = threading.Thread(target=read_progress,
                                      args=(process.stdout, player, spawn_mono), daemon=True)
            reader.start()
            readers.append(reader)
        if not launch_window_ok(spawn_return_epochs):
            abort("launch_window_exceeded", "launch")
            return 2
        if any(process.poll() is not None for process in viewer_processes):
            abort("launch_barrier_failed", "launch")
            return 2
        abort_stage = None
        stop_reason = "player_exited"
        event_tail = IncrementalText(out / "server-events.jsonl")
        while True:
            try:
                drain_log()
            except Exception as exc:
                abort("collector_error", "collection")
                record_lifecycle({"kind": "collector_error", "errorCategory": fetch_error(exc), "utc": utc(),
                                  "collectorExceptionType": type(exc).__name__})
                break
            try:
                capacity_category = None
                for line in event_tail.read_lines():
                    try:
                        event = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    candidate = event.get("errorCategory") or object_value(event.get("data")).get("failureKind")
                    if candidate in ("storage_limit", "wait_timeout"):
                        capacity_category = candidate
                        break
                if capacity_category:
                    abort("captured_" + capacity_category, "capacity")
                    break
            except Exception as exc:
                abort("collector_error", "collection")
                record_lifecycle({"kind": "collector_error", "errorCategory": fetch_error(exc), "utc": utc(),
                                  "collectorExceptionType": type(exc).__name__})
                break
            statuses = [process.poll() for process in viewer_processes]
            if all(code is not None for code in statuses):
                consumer_failure = any(
                    sum(player.counts[kind] for kind in
                        ("http_error", "segment_open_failed", "playback_failure", "player_error"))
                    for player in viewer_evidence
                )
                if any(code not in (0, None) for code in statuses) or consumer_failure:
                    abort("player_exit_failure", "collection")
                else:
                    stop_reason = "player_exited"
                break
            failed = [index for index, code in enumerate(statuses)
                      if code is not None and
                      (code != 0 or sum(viewer_evidence[index].counts[kind] for kind in
                                        ("http_error", "segment_open_failed", "playback_failure", "player_error")))]
            if failed:
                abort("viewer_failure", "collection")
                break
            if helper.poll() is not None:
                abort("server_collector_exited", "server_collection")
                break
            if time.monotonic() >= deadline - CLEANUP_RESERVE_SECONDS:
                abort("wall_deadline", "deadline")
                break
            time.sleep(0.1)
    except KeyboardInterrupt:
        abort("interrupted", "interruption")
    except Exception as exc:
        abort("collector_error", abort_stage or "collection")
        record_lifecycle({"kind": "collector_error", "errorCategory": fetch_error(exc), "utc": utc(),
                          "collectorExceptionType": type(exc).__name__})
    finally:
        try:
            viewer_exit_codes = [None] * len(viewer_processes)
            for index, process in enumerate(viewer_processes):
                stopped = cleanup(lambda p=process: stop_owned(p), f"viewer_{index}_stop_failed")
                try:
                    exit_code = process.poll()
                except StopIteration:
                    exit_code = None
                viewer_exit_codes[index] = exit_code
                record_lifecycle({"kind": "player_stop", "viewerIndex": index, "utc": utc(),
                                  "reason": stop_reason, "forced": stopped, "exitCode": exit_code})
                if len(readers) > index and readers[index] is not None:
                    readers[index].join(timeout=1)
                    if readers[index].is_alive():
                        record_lifecycle({"kind": "progress_reader_incomplete", "viewerIndex": index, "utc": utc()})
            cleanup(lambda: drain_log(final=True), "final_player_log_read_failed")
        finally:
            if helper is not None and helper.poll() is None:
                try:
                    helper.stdin.write(b"stop\n")
                    helper.stdin.flush()
                    helper.wait(timeout=max(0.1, min(8, deadline - time.monotonic())))
                except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                    helper_forced = cleanup(lambda: stop_owned(helper), "helper_stop_failed")
            for index, process in enumerate(viewer_processes):
                if len(readers) > index and (readers[index] is None or not readers[index].is_alive()):
                    cleanup(process.stdout.close, f"viewer_{index}_stdout_close_failed")
            if helper is not None:
                cleanup(helper.stdin.close, "helper_stdin_close_failed")
            cleanup(scratch.cleanup, "raw_player_log_removal_failed")
            cleanup(lifecycle.close, "lifecycle_close_failed") if lifecycle is not None else None
            cleanup(consumer.close, "consumer_close_failed") if consumer is not None else None
            ended = time.time()
            if abort_stage in ("preflight", "initial_telemetry", "launch"):
                collection_state = "aborted"
            elif stop_reason == "player_exited":
                collection_state = "completed"
            else:
                collection_state = "partial"
            viewers = {}
            for index, label in enumerate(VIEWER_LABELS):
                if index < len(viewer_evidence):
                    viewers[label] = viewer_evidence[index].summary(viewer_exit_codes[index])
                    viewers[label].update(viewer_meta[index])
                    viewers[label]["stopReason"] = stop_reason
                else:
                    viewers[label] = {
                        "label": label, "startPositionSeconds": START_POSITIONS[index],
                        "status": "not_started", "stopReason": stop_reason,
                    }
            summary = {
                "scope": SCOPE,
                "preflight": preflight_record or preflight_failure or
                             {"status": "not_run", "accepted": False, "errorCategory": "not_run"},
                "launch": {
                    "viewerCount": len(viewer_processes),
                    "windowSeconds": LAUNCH_WINDOW_SECONDS,
                    "observedSpawnReturnSpreadSeconds":
                        max(spawn_return_epochs) - min(spawn_return_epochs) if spawn_return_epochs else None,
                    "barrierPassed": len(viewer_processes) == 2 and abort_stage != "launch",
                    "viewers": launch_records,
                },
                "viewers": viewers,
                "server": server_summary(out, min(spawn_epochs) if spawn_epochs else None, ended),
                "crossViewer": cross_viewer_summary(out, viewer_evidence),
                "limits": {
                    "mediaSecondsTarget": MEDIA_SECONDS,
                    "progressToleranceSeconds": PROGRESS_TOLERANCE_SECONDS,
                    "progressFloorSeconds": MIN_PROGRESS_SECONDS,
                    "minimumOverlapSeconds": MIN_OVERLAP_SECONDS,
                    "nominalOverlapSeconds": MEDIA_SECONDS,
                    "playbackRateAssumption": PLAYBACK_RATE_ASSUMPTION,
                    "wallLimitSeconds": WALL_SECONDS,
                    "cleanupReserveSeconds": CLEANUP_RESERVE_SECONDS,
                    "launchWindowSeconds": LAUNCH_WINDOW_SECONDS,
                    "pollSeconds": POLL_SECONDS,
                    "debugNodeCount": len(NODES),
                    "targetDebugRequestsPerSecond": len(NODES) / POLL_SECONDS,
                    "httpSocketTimeoutSeconds": HTTP_TIMEOUT,
                    "maxResponseBytes": MAX_RESPONSE,
                    "serverLedgerComplete": False,
                    "inventory": "unknown",
                    "serverClientClockOffset": "unknown",
                    "instrumentationAffectsPerformance": True,
                },
                "collectionStatus": {
                    "status": collection_state,
                    "stopReason": stop_reason,
                    "abortStage": abort_stage,
                    "startedUtc": utc(started),
                    "endedUtc": utc(ended),
                    "playersSpawned": len(viewer_processes),
                    "helperForcedStop": helper_forced,
                    "cleanupErrors": cleanup_errors,
                    "progressReaderStopped": [
                        not reader.is_alive() if reader else None for reader in readers
                    ],
                    "rawPlayerLog": "removal_failed" if "raw_player_log_removal_failed" in cleanup_errors
                                    else "temporary_only_removed",
                    "completeLedger": False,
                    "completionAloneIsConformance": False,
                },
            }
            write_json_exclusive(out / "summary.json", summary)
            if collection_state == "aborted":
                write_json_exclusive(out / "aborted.json", {
                    "scope": SCOPE,
                    "abortedUtc": utc(ended),
                    "stage": abort_stage,
                    "reason": stop_reason,
                    "playersSpawned": len(viewer_processes),
                    "preflightAccepted": bool(preflight_record and preflight_record.get("accepted")),
                    "message": "Collection stopped without claiming a conformance verdict.",
                })
    return 0 if stop_reason == "player_exited" else 2


if __name__ == "__main__":
    try:
        options = parse_args()
        sys.exit(poll_worker(options) if options._poll_worker else run(options))
    except (OSError, ValueError):
        # No traceback/exception text: URL and auth material can appear there.
        print("Collector setup/cleanup failed; inspect partial sanitized evidence if created.", file=sys.stderr)
        sys.exit(2)
