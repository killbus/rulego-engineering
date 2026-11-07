"""Offline-only tests; no HTTP, player invocation or production mutation."""

import importlib.util
import io
import threading
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error
from types import SimpleNamespace
from contextlib import redirect_stderr


SPEC = importlib.util.spec_from_file_location("two_viewer", Path(__file__).with_name("run-two-viewer.py"))
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


def row(ts=1000, relation="Success", flow="OUT", error="", data=None, metadata=None):
    return {"ts": ts, "nodeId": "commit", "msgId": "request-1", "flowType": flow,
            "relationType": relation, "err": error,
            "msg": json.dumps({"id": "request-1", "data": json.dumps(data or {}),
                               "metadata": metadata or {}})}


def component_body(version="0.2.1", retained=collector.MAX_RETAINED_BYTES):
    return {"type": "resourceOrigin", "version": version,
            "configuration": {"maxRetainedBytes": retained,
                              "maxResourceBytes": 33554432,
                              "maxProductionMs": 300000,
                              "maxTtlMs": 86400000}}


def chain_body(root="ref://resource-origin", child_ttl=120000, parent_ttl=21600000):
    return {
        "ruleChain": {"id": "chain"},
        "metadata": {
            "nodes": [
                {"id": "child-origin", "type": "resourceOrigin",
                 "configuration": {"root": root}},
                {"id": "parent-origin", "type": "resourceOrigin",
                 "configuration": {"root": root}},
                {"id": "child-acquire-request",
                 "configuration": {"jsScript":
                     f"return {{'ttlMs':{child_ttl},'maxBytes':33554432,'productionTimeoutMs':300000}};"}},
                {"id": "parent-acquire-request",
                 "configuration": {"jsScript":
                     f"return {{'ttlMs':{parent_ttl},'maxBytes':33554432,'productionTimeoutMs':300000}};"}},
            ],
            "connections": [],
        },
    }


def shared_nodes_body(node_id="resource-origin", retained=collector.MAX_RETAINED_BYTES):
    return {
        "items": [
            {"id": node_id, "type": "resourceOrigin",
             "configuration": {"maxProductionMs": 300000,
                               "maxResourceBytes": 33554432,
                               "maxRetainedBytes": retained,
                               "maxTtlMs": 86400000,
                               "root": "./data/resource-origin"}},
            {"id": "endpoint", "type": "endpoint/http", "configuration": {}},
            {"id": "indexed-media", "type": "indexedMedia", "configuration": {}},
        ],
        "page": 1, "size": 100, "total": 3,
    }


def args_for(out, mpv=None):
    return SimpleNamespace(mpv=mpv, out=str(out), base_url="http://offline.invalid",
                           chain="chain", video="video")


class SanitizationTests(unittest.TestCase):
    def test_ready_success_and_pending_identity_preserved_without_source(self):
        raw = row(data={"state": "ready", "size": 3909272, "bytes": 4, "byteSize": 5,
                        "resourceId": "resource-1", "generation": "generation-1",
                        "parentResourceId": "parent-1", "index": 7,
                        "publishedAt": "2026-11-05T18:17:59.123Z", "expiresAt": "2026-11-05T18:19:59.123Z",
                        "url": "https://secret.invalid/?token=forbidden", "source": {"secret": "forbidden"}},
                  metadata={"segment": "7", "generation": "generation-1", "source": "forbidden"})
        event = collector.sanitize_event(raw, "commit")
        self.assertFalse(event["failureSignal"])
        self.assertEqual(event["data"]["size"], 3909272)
        self.assertEqual(event["metadata"]["segment"], 7)
        self.assertEqual(event["data"]["parentResourceId"], "parent-1")
        self.assertNotIn("forbidden", json.dumps(event))
        self.assertNotIn("https", json.dumps(event))
        pending = collector.sanitize_event(row(data={"state": "pending", "resourceId": "r1", "generation": "g1",
                                                     "publishBy": "2026-11-05T18:22:59Z"}), "child-origin")
        self.assertEqual(pending["data"]["state"], "pending")
        self.assertIn("publishBy", pending["data"])

    def test_failure_classified_without_raw_body_or_credentials(self):
        with patch.dict(os.environ, {"RULEGO_USER": "private-user", "RULEGO_PASSWORD": "secret-password"}):
            raw = row(error="storage_limit: https://secret.invalid/?token=private-user secret-password",
                      relation="Failure", data={"state": "failed", "failureKind": "storage_limit",
                                               "resourceId": "secret-password"})
            event = collector.sanitize_event(raw, "commit")
        serialized = json.dumps(event)
        self.assertTrue(event["failureSignal"])
        self.assertEqual(event["errorCategory"], "storage_limit")
        self.assertNotIn("private-user", serialized)
        self.assertNotIn("secret-password", serialized)
        self.assertNotIn("https", serialized)

    def test_invalid_fields_are_not_copied(self):
        event = collector.sanitize_event(row(data={"size": float("nan"), "publishedAt": "secret",
                                                   "resourceId": "https://host/secret", "kind": "secret"}), "commit")
        self.assertEqual(event["data"], {"kind": "unclassified_kind"})
        self.assertIsNone(collector.number(True))
        self.assertIsNone(collector.timestamp("2026-99-99T18:22:59Z"))

    def test_resolver_nonzero_exit_is_failure_without_copying_stdout(self):
        event = collector.sanitize_event(row(data={"exit_code": 1, "stdout": "private", "stderr": "secret"}), "source-resolver")
        self.assertTrue(event["failureSignal"])
        self.assertEqual(event["errorCategory"], "resolver_exit_failure")
        self.assertNotIn("secret", json.dumps(event))

    def test_timeout_categories(self):
        self.assertEqual(collector.fetch_error(TimeoutError("timed out")), "timeout")
        self.assertEqual(collector.fetch_error(urllib.error.URLError(TimeoutError())), "timeout")
        self.assertEqual(collector.fetch_error(urllib.error.URLError("timed out")), "timeout")
        error = urllib.error.HTTPError("secret", 503, "secret", {}, None)
        try:
            self.assertEqual(collector.fetch_error(error), "http_503")
        finally:
            error.close()
        self.assertEqual(collector.category("wait_timeout: context canceled"), "wait_timeout")
        self.assertEqual(collector.category("context deadline exceeded"), "timeout")
        self.assertEqual(collector.fetch_error(ValueError("secret")), "invalid_response")

    def test_fetch_never_follows_redirect_and_never_persists_error_body(self):
        self.assertIsNone(collector.NoRedirect().redirect_request(None, None, 302, None, None, "https://elsewhere.invalid"))
        response = Mock()
        response.read.return_value = json.dumps({"items": [row()], "total": 1}).encode()
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        with patch.object(collector.urllib.request, "build_opener", return_value=opener):
            events, total = collector.fetch_tail("http://offline.invalid", "chain", "commit", "Basic not-real")
        self.assertEqual(total, 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], collector.HTTP_TIMEOUT)
        response.read.return_value = b'{"items": null, "total": 0}'
        with patch.object(collector.urllib.request, "build_opener", return_value=opener):
            self.assertEqual(collector.fetch_tail("http://offline.invalid", "chain", "commit", "Basic not-real"), ([], 0))


class TailTests(unittest.TestCase):
    def event(self, ts=1000, **kwargs):
        return collector.sanitize_event(row(ts, **kwargs), "commit")

    def test_dedup_retains_success_and_failure_in_out(self):
        tracker = collector.TailTracker()
        failure = self.event(error="storage_limit: sensitive body", relation="Failure")
        success = self.event(1001, data={"state": "ready", "size": 42})
        incoming = self.event(flow="IN")
        outgoing = self.event(flow="OUT")
        events = [failure, success, incoming, outgoing]
        fresh, diagnostic = tracker.accept(events, 4, 0)
        self.assertEqual(len(fresh), 4)
        self.assertEqual(sum(event["failureSignal"] for event in fresh), 1)
        self.assertFalse(diagnostic["ledgerComplete"])
        fresh, diagnostic = tracker.accept(events, 4, 1)
        self.assertEqual(fresh, [])
        self.assertEqual(diagnostic["overlapRows"], 4)

    def test_no_overlap_gap_timeout_recovery_and_retained_overflow(self):
        tracker = collector.TailTracker()
        tracker.accept([self.event()], 1, 0)
        _, diagnostic = tracker.accept([], 0, 2, "timeout")
        self.assertEqual(diagnostic["continuity"], "uncertain_fetch_failure")
        fresh, diagnostic = tracker.accept([self.event(9000)], 40, 9)
        self.assertEqual(len(fresh), 1)
        for flag in ("possible_overwrite_or_reset", "recovering_after_fetch_failure", "long_poll_gap", "unfetched_retained_rows"):
            self.assertIn(flag, diagnostic["flags"])

    def test_empty_tail_reset_and_duplicates_stay_uncertain(self):
        tracker = collector.TailTracker()
        event = self.event()
        fresh, diagnostic = tracker.accept([event, event], 2, 0)
        self.assertEqual(len(fresh), 1)
        self.assertIn("identical_rows_indistinguishable", diagnostic["flags"])
        _, diagnostic = tracker.accept([], 0, 1)
        self.assertIn("tail_cleared", diagnostic["flags"])


class ContractTests(unittest.TestCase):
    def test_bound_uses_progress_floor_for_overlap_and_assumes_one_x(self):
        self.assertEqual(collector.MEDIA_SECONDS, 360)
        self.assertEqual(collector.MIN_PROGRESS_SECONDS, 359)
        self.assertEqual(collector.MIN_OVERLAP_SECONDS, collector.MIN_PROGRESS_SECONDS)
        self.assertEqual(collector.PLAYBACK_RATE_ASSUMPTION, "approximately_1x")

    def test_launch_window_is_at_most_two_seconds(self):
        self.assertTrue(collector.launch_window_ok([10.0, 12.0]))
        self.assertFalse(collector.launch_window_ok([10.0, 12.001]))
        self.assertFalse(collector.launch_window_ok([10.0]))

    def test_node_set_is_the_same_22_node_single_viewer_set(self):
        single_path = (Path(__file__).resolve().parents[2] /
                       "11-05-hls-friendly-concurrency" / "research" / "run-single-baseline.py")
        spec = importlib.util.spec_from_file_location("single_viewer_nodes", single_path)
        single = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(single)
        self.assertEqual(len(collector.NODES), 22)
        self.assertEqual(collector.NODES, single.NODES)

    def test_frozen_single_viewer_source_and_tests_are_preserved(self):
        root = Path(__file__).resolve().parents[2] / "11-05-hls-friendly-concurrency" / "research"
        import hashlib
        expected = {
            "run-single-baseline.py": "BA6C23FBE69FB012211F0C31F615837738C3AD3F66E8B6B9F6B19A9E13A45A26",
            "test_single_baseline.py": "E8943DC330C2F2B8B2DF6363B2D82A3550C56FB76A90ADBBE5BAD4E83339206A",
        }
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest().upper(), digest)

    def test_incremental_text_never_replays_previous_lines(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "viewer.log"
            path.write_bytes(b"[ 1.0][v][cplayer] first\n[ 2.0][v][cplayer] par")
            tail = collector.IncrementalText(path)
            self.assertEqual(tail.read_lines(), ["[ 1.0][v][cplayer] first"])
            with path.open("ab") as file:
                file.write(b"tial\n[ 3.0][v][cplayer] third")
            self.assertEqual(tail.read_lines(), ["[ 2.0][v][cplayer] partial"])
            self.assertEqual(tail.read_lines(), [])
            self.assertEqual(tail.read_lines(final=True), ["[ 3.0][v][cplayer] third"])
            self.assertEqual(tail.read_lines(final=True), [])

    def test_real_catalog_and_instance_envelopes_supply_preflight_values(self):
        catalog = collector.parse_component_policy({
            "nodes": [{"type": "resourceOrigin", "version": "0.2.1"}]
        })
        self.assertEqual(catalog, ("resourceOrigin", "0.2.1", {}))
        instance = collector.parse_shared_node_policy(shared_nodes_body())
        self.assertEqual(instance[0], "resourceOrigin")
        self.assertEqual(instance[1], "resource-origin")
        self.assertEqual(instance[2]["maxRetainedBytes"], collector.MAX_RETAINED_BYTES)
        policy = collector.readback_policy(chain_body())
        self.assertTrue(policy["rootConfiguration"]["allMatch"])
        self.assertEqual(len(policy["resourceOriginRoots"]), 2)
        mismatch = collector.readback_policy(chain_body(root="ref://other-origin"))
        self.assertFalse(mismatch["rootConfiguration"]["allMatch"])

    def test_old_catalog_summary_still_fails_closed(self):
        self.assertEqual(collector.parse_component_policy({
            "resourceOriginVersion": "0.1.9", "configuration": {},
            "nodeCount": 52, "globalNames": []
        }), (None, None, {}))

    def test_shared_node_instance_must_be_unique_and_identified(self):
        valid = collector.parse_shared_node_policy(shared_nodes_body())
        self.assertEqual(valid[:2], ("resourceOrigin", "resource-origin"))
        for body in ({"items": []}, {"items": [shared_nodes_body()["items"][0],
                                              shared_nodes_body()["items"][0]]},
                     shared_nodes_body(node_id="other-origin")):
            self.assertEqual(collector.parse_shared_node_policy(body),
                             ("ambiguous_shared_nodes_envelope", None, {}))
        self.assertEqual(collector.parse_shared_node_policy({"unexpected": []}),
                         ("invalid_shared_nodes_envelope", None, {}))

    def test_duplicate_or_unsupported_viewer_configuration_is_rejected(self):
        base = ["collector", "--out", "unused", "--base-url", "http://offline.invalid",
                "--chain", "chain", "--video", "video"]
        cases = [
            ["--labels", "viewer-a,viewer-a", "--starts", "0,600"],
            ["--labels", "viewer-a,viewer-b,viewer-c", "--starts", "0,600"],
            ["--labels", "viewer-a,viewer-b", "--starts", "0,0"],
            ["--labels", "viewer-a,viewer-b", "--starts", "0,600,1200"],
            ["--labels", "viewer-a,viewer-c", "--starts", "0,600"],
        ]
        with patch.dict(os.environ, {"RULEGO_USER": "offline", "RULEGO_PASSWORD": "offline"}):
            for extra in cases:
                with self.subTest(extra=extra), patch("sys.argv", base + extra), \
                        redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    collector.parse_args()
            with patch("sys.argv", base):
                parsed = collector.parse_args()
        self.assertEqual(parsed.labels, "viewer-a,viewer-b")
        self.assertEqual(parsed.starts, "0,600")

    def test_two_viewers_do_not_cross_assign_progress_or_log_signals(self):
        events_a, events_b = [], []
        player_a = collector.PlayerEvidence(events_a.append, 1000, start=0)
        player_b = collector.PlayerEvidence(events_b.append, 1000, start=600)
        player_a.progress("VIEWER-A pos=360.0", 361)
        player_b.progress("VIEWER-B pos=960.0", 361)
        player_a.log("[ 10.0][w][ffmpeg] http: HTTP error 500 for A")
        player_b.log("[ 10.0][i][cplayer] VO: [null] 1920x1080 yuv420p")
        summary_a, summary_b = player_a.summary(0), player_b.summary(0)
        self.assertEqual(summary_a["relativeProgressSeconds"], 360)
        self.assertEqual(summary_b["relativeProgressSeconds"], 360)
        self.assertEqual(summary_a["counts"].get("http_error"), 1)
        self.assertNotIn("http_error", summary_b["counts"])
        self.assertIsNone(summary_a["resolution"])
        self.assertEqual(summary_b["resolution"], [1920, 1080])
        self.assertTrue(all(event["positionSeconds"] < 600 for event in events_a
                            if event["kind"] == "progress"))
        self.assertTrue(all(event["positionSeconds"] >= 600 for event in events_b
                            if event["kind"] == "progress"))


class PlayerTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.player = collector.PlayerEvidence(self.events.append, 1000)

    def test_prior_87_second_buffer_and_raw_http_502(self):
        self.player.progress("AV: 00:00:20 / 00:45:06", 30)
        for line in (
            "[  36.035][v][cplayer] Enter buffering (buffer went from 100% -> 0%) [0.000000s].",
            "[ 113.612][w][ffmpeg] http: HTTP error 502 Bad Gateway",
            "[ 113.614][w][ffmpeg/demuxer] hls: Failed to open segment 7 of playlist 0",
            "[ 123.444][v][cplayer] End buffering (waited 87.408639 secs) [2.832833s].",
            "[ 275.269][v][cplayer] finished playback, success (reason 0)",
        ):
            self.player.log(line)
        summary = self.player.summary(0)
        self.assertEqual(summary["maxCompletedBufferingSeconds"], 87.408639)
        self.assertTrue(summary["finishedPlaybackSuccess"])
        self.assertEqual(summary["continuity"], "interruptions_observed")
        end = next(event for event in self.events if event["kind"] == "buffer_end")
        self.assertTrue(end["pairedEnter"])
        self.assertEqual(end["phase"], "midplay")
        self.assertEqual(end["estimatedUtc"], collector.utc(1123.444))

    def test_prior_4_second_buffer_is_log_not_stdout_and_unpaired_observed(self):
        self.player.progress("End buffering (waited 99.9 secs)", 1)
        self.assertIsNone(self.player.summary(None)["maxCompletedBufferingSeconds"])
        self.player.log("[  12.096][v][cplayer] End buffering (waited 4.379011 secs) [2.438100s].")
        self.assertEqual(self.player.summary(0)["maxCompletedBufferingSeconds"], 4.379011)
        self.assertFalse(self.events[0]["pairedEnter"])
        self.assertEqual(self.events[0]["phase"], "startup_or_unconfirmed")

    def test_relative_progress_and_no_false_zero_or_completion_pass(self):
        self.player = collector.PlayerEvidence(self.events.append, 1000, start=1200)
        self.player.progress("AV: 00:19:59 / 00:45:06 (44%)", 1)
        self.player.progress("AV: 00:26:00 / 00:45:06 (57%)", 370)
        self.assertEqual(self.player.summary(0)["relativeProgressSeconds"], 360)
        self.assertTrue(self.player.summary(0)["reachedTargetWithinTolerance"])
        self.assertIsNone(self.player.summary(0)["maxCompletedBufferingSeconds"])
        self.assertEqual(self.player.summary(0)["bufferTelemetry"], "unknown")
        self.assertEqual(self.player.summary(0)["continuity"], "not_proven")
        self.assertEqual(collector.media_progress("BASELINE pos=360.052"), 360.052)

    def test_http_507_retry_and_open_strip_urls(self):
        for line in (
            "[ 121.528][v][ffmpeg] http: Opening 'http://origin.invalid/youtube/video/rev/276.ts?token=SECRET' for reading",
            "[ 123.981][w][ffmpeg] http: HTTP error 507 Insufficient Storage",
            "[ 123.982][w][ffmpeg/demuxer] hls: keepalive request failed for 'http://origin.invalid/youtube/video/rev/276.ts?token=SECRET' with error: 'Server returned 5XX Server Error reply' when opening url, retrying with new connection",
            "[ 123.982][v][ffmpeg/demuxer] hls: Opening 'http://origin.invalid/youtube/video/rev/276.ts?token=SECRET' for reading",
        ):
            self.player.log(line)
        self.assertNotIn("SECRET", json.dumps(self.events))
        self.assertNotIn("origin.invalid", json.dumps(self.events))
        self.assertEqual(self.player.counts["http_retry"], 1)
        opens = [event for event in self.events if event["kind"] == "http_open"]
        self.assertEqual(opens[0]["index"], 276)
        self.assertTrue(opens[1]["repeatedIndex"])

    def test_incomplete_buffer_and_1080p(self):
        self.player.log("[ 4.200][i][cplayer] VO: [null] 1920x1080 yuv420p")
        self.player.log("[ 36.035][v][cplayer] Enter buffering (buffer went from 100% -> 0%) [0.000000s].")
        summary = self.player.summary(None)
        self.assertIsNone(summary["maxCompletedBufferingSeconds"])
        self.assertEqual(summary["openBufferIntervalStart"], 36.035)
        self.assertTrue(summary["observed1080p"])

    def test_repeated_zero_term_status_does_not_hide_advancing_player_clock(self):
        lines = (
            "[ 1.000][v][cplayer] BASELINE pos=0.000",
            "[ 1.100][i][ffmpeg] AV: 00:00:01.500",
            "[ 2.000][v][cplayer] BASELINE pos=0.000",
            "[ 2.100][i][ffmpeg] AV: 00:00:02.500",
            "[ 3.000][v][cplayer] BASELINE pos=0.000",
            "[ 3.100][i][ffmpeg] AV: 00:00:03.500",
        )
        elapsed = (1.0, 1.1, 2.0, 2.1, 3.0, 3.1)
        for line, seconds in zip(lines, elapsed):
            self.player.progress(line, seconds)
        summary = self.player.summary(0)
        self.assertEqual(summary["maxPositionSeconds"], 3.5)
        self.assertEqual(summary["maxPositionSource"], "playerClock")
        self.assertEqual(summary["relativeProgressSeconds"], 3.5)
        self.assertEqual(summary["firstObservedAdvanceElapsed"], 1.1)
        self.assertEqual(summary["firstObservedAdvanceSource"], "playerClock")
        self.assertTrue(summary["explicitMarkerNonProgressing"])
        self.assertEqual(summary["phaseCounts"], {"startup_or_unconfirmed": 1, "midplay": 5})
        self.assertEqual([event["positionSource"] for event in self.events],
                         ["termStatus", "playerClock", "termStatus", "playerClock",
                          "termStatus", "playerClock"])

    def test_verbose_player_clock_is_only_when_marker_is_absent(self):
        self.player.progress("[ 2.100][i][ffmpeg] AV: 00:00:02.500", 2.1)
        self.assertEqual(self.events[0]["positionSource"], "playerClock")
        self.assertEqual(self.player.summary(0)["maxPositionSource"], "playerClock")

    def test_stdout_and_log_forms_are_term_status_marker(self):
        for line in ("BASELINE pos=0.000", "[ 1.000][v][cplayer] BASELINE pos=0.000"):
            self.player.progress(line, 1)
            self.assertEqual(self.events[-1]["positionSource"], "termStatus")

    def test_numeric_and_duration_term_status_are_supported(self):
        self.assertEqual(collector.media_progress("BASELINE pos=3.651697"), 3.651697)
        self.assertEqual(collector.media_progress("BASELINE pos=00:00:03"), 3.0)
        self.assertEqual(collector.media_progress("BASELINE pos=01:02:03.5"), 3723.5)
        self.assertIsNone(collector.media_progress("BASELINE pos=not-a-number"))

    def test_missing_and_true_zero_evidence_remain_unknown_not_advance(self):
        self.player.progress("[ 1.000][i][ffmpeg] Opening 'http://secret.invalid/video.ts'", 1)
        self.assertIsNone(self.player.summary(0)["maxPositionSeconds"])
        self.assertIsNone(self.player.summary(0)["relativeProgressSeconds"])
        self.assertFalse(self.player.summary(0)["reachedTargetWithinTolerance"])
        self.assertIsNone(self.player.summary(0)["firstObservedAdvanceElapsed"])
        self.player.progress("[ 2.000][v][cplayer] BASELINE pos=0.000", 2)
        summary = self.player.summary(0)
        self.assertEqual(summary["maxPositionSeconds"], 0.0)
        self.assertEqual(summary["maxPositionSource"], "termStatus")
        self.assertEqual(summary["relativeProgressSeconds"], 0.0)
        self.assertFalse(summary["reachedTargetWithinTolerance"])
        self.assertEqual(summary["firstObservedAdvanceElapsed"], None)
        self.assertIsNone(summary["firstObservedAdvanceSource"])
        self.assertFalse(summary["explicitMarkerNonProgressing"])

    def test_mixed_repeated_zero_then_numeric_term_status_advances(self):
        self.player.progress("BASELINE pos=0.000", 1.0)
        self.player.progress("BASELINE pos=00:00:03", 2.0)
        self.player.progress("BASELINE pos=3.651697", 3.0)
        summary = self.player.summary(0)
        self.assertEqual(summary["maxPositionSeconds"], 3.651697)
        self.assertEqual(summary["maxPositionSource"], "termStatus")
        self.assertEqual(summary["relativeProgressSeconds"], 3.651697)
        self.assertEqual(summary["firstObservedAdvanceElapsed"], 2.0)
        self.assertEqual(summary["firstObservedAdvanceSource"], "termStatus")
        self.assertFalse(summary["explicitMarkerNonProgressing"])


class LifecycleTests(unittest.TestCase):
    def _mocked_run(self, temp, player_polls, stdout_lines=("", ""), wall=None,
                    interrupt_after_launch=False, baseline_ok=True):
        out = Path(temp) / "new"
        executable = Path(temp) / "mpv.exe"
        helper = Mock(pid=9000)
        helper.poll.return_value = None
        players = []
        for index, position in enumerate(collector.START_POSITIONS):
            player = Mock(pid=9100 + index)
            player.poll.side_effect = list(player_polls[index])
            player.stdout = io.BytesIO(stdout_lines[index].encode())
            players.append(player)
        commands = []

        def spawn(command, **kwargs):
            commands.append(command)
            if "--_poll-worker" in command:
                (out / "baseline.json").write_text(json.dumps({"allSucceeded": baseline_ok}))
                for filename in ("server-events.jsonl", "polls.jsonl"):
                    (out / filename).write_text("")
                return helper
            index = 0 if "--start=0" in command else 1
            raw_path = Path(next(arg.split("=", 1)[1] for arg in command
                                 if arg.startswith("--log-file=")))
            raw_path.write_text("")
            return players[index]

        responses = iter([component_body(), shared_nodes_body(), chain_body()])
        stop_owned = Mock(return_value=True)
        patches = [
            patch.dict(os.environ, {"RULEGO_USER": "offline-user",
                                    "RULEGO_PASSWORD": "offline-password"}),
            patch.object(collector, "fetch_json", side_effect=lambda url, auth: next(responses)),
            patch.object(collector.shutil, "which", return_value=str(executable)),
            patch.object(collector.subprocess, "CREATE_NO_WINDOW", 0, create=True),
            patch.object(collector.subprocess, "Popen", side_effect=spawn),
            patch.object(collector, "stop_owned", stop_owned),
        ]
        if wall is not None:
            patches.append(patch.object(collector, "WALL_SECONDS", wall))
        if interrupt_after_launch:
            patches.append(patch.object(collector.time, "sleep", side_effect=KeyboardInterrupt))
        try:
            for item in patches:
                item.start()
            result = collector.run(args_for(out))
        finally:
            for item in reversed(patches):
                item.stop()
        return SimpleNamespace(out=out, result=result, commands=commands, players=players,
                               helper=helper, stop_owned=stop_owned)

    def test_mocked_run_two_players_no_cache_changes_and_finally_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "new"
            executable = Path(temp) / "mpv.exe"
            args = SimpleNamespace(mpv=None, out=str(out), base_url="http://offline.invalid", chain="chain", video="video")
            helper, player_a, player_b = Mock(), Mock(), Mock()
            helper.poll.return_value = None
            for player, position in ((player_a, 0), (player_b, 600)):
                player.poll.side_effect = [None, 0, 0]
                player.pid = 1234 + position // 600
                player.stdout = io.BytesIO(f"VIEWER-{'A' if position == 0 else 'B'} pos={position + 360.0}\r".encode())
            responses = iter([
                component_body(),
                shared_nodes_body(),
                chain_body(),
            ])

            def spawn(command, **kwargs):
                if "--_poll-worker" in command:
                    (out / "baseline.json").write_text('{"allSucceeded": true}')
                    for filename in ("server-events.jsonl", "polls.jsonl"):
                        (out / filename).write_text("")
                    return helper
                raw_path = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--log-file=")))
                raw_path.write_text("[ 1.0][i][cplayer] VO: [null] 1920x1080 yuv420p\n[ 361.0][v][cplayer] finished playback, success (reason 0)\n")
                self.assertFalse(any("cache" in arg or "readahead" in arg for arg in command))
                self.assertIn("--no-ytdl", command)
                self.assertIn("--end=360" if "--start=0" in command else "--end=960", command)
                status_tokens = [arg for arg in command if arg.startswith("--term-status-msg=")]
                self.assertEqual(len(status_tokens), 1)
                if "--start=0" in command:
                    self.assertEqual(status_tokens[0], "--term-status-msg=VIEWER-A pos=${=time-pos}")
                else:
                    self.assertEqual(status_tokens[0], "--term-status-msg=VIEWER-B pos=${=time-pos}")
                self.assertNotIn("RULEGO_PASSWORD", kwargs["env"])
                self.assertEqual(kwargs["creationflags"], 0)
                return player_a if "--start=0" in command else player_b

            with patch.dict(os.environ, {"RULEGO_USER": "offline-user", "RULEGO_PASSWORD": "offline-password"}), \
                    patch.object(collector, "fetch_json", side_effect=lambda url, auth: next(responses)), \
                    patch.object(collector.shutil, "which", return_value=str(executable)), \
                    patch.object(collector.subprocess, "CREATE_NO_WINDOW", 0, create=True), \
                    patch.object(collector.subprocess, "Popen", side_effect=spawn) as popen:
                self.assertEqual(collector.run(args), 0)
                self.assertEqual(popen.call_count, 3)  # one shared collector helper and exactly two viewers
                with self.assertRaises(FileExistsError):
                    collector.run(args)
            summary = json.loads((out / "summary.json").read_text())
            self.assertEqual(summary["scope"], "two_viewer_same_program_different_positions_not_AC5")
            self.assertEqual(set(summary), {
                "scope", "preflight", "launch", "viewers", "server", "crossViewer",
                "limits", "collectionStatus",
            })
            self.assertTrue(summary["preflight"]["accepted"])
            self.assertEqual(summary["preflight"]["resourceOriginVersion"], "0.2.1")
            self.assertEqual(summary["preflight"]["resourceOriginInstanceId"], "resource-origin")
            self.assertEqual(summary["preflight"]["resourceOriginPolicy"]["maxRetainedBytes"],
                             collector.MAX_RETAINED_BYTES)
            self.assertTrue(summary["preflight"]["checks"]["sharedNodeInstance"])
            self.assertTrue(summary["preflight"]["checks"]["sharedNodeId"])
            self.assertIsNotNone(summary["preflight"]["sharedNodesSha256"])
            self.assertEqual(summary["preflight"]["existingTraffic"]["knownLocalMpvProcesses"], None)
            self.assertEqual(summary["preflight"]["existingTraffic"]["knownLocalMpvProcessesState"],
                             "not_measured")
            self.assertEqual(summary["launch"]["viewerCount"], 2)
            self.assertTrue(summary["launch"]["barrierPassed"])
            self.assertEqual(summary["viewers"]["viewer-a"]["relativeProgressSeconds"], 360)
            self.assertEqual(summary["viewers"]["viewer-b"]["relativeProgressSeconds"], 360)
            self.assertFalse(summary["limits"]["serverLedgerComplete"])
            self.assertEqual(summary["limits"]["minimumOverlapSeconds"], 359)
            self.assertEqual(summary["limits"]["progressFloorSeconds"], 359)
            self.assertEqual(summary["limits"]["playbackRateAssumption"], "approximately_1x")
            self.assertEqual(summary["server"]["ledgerComplete"], False)
            self.assertFalse(summary["crossViewer"]["serverEventsAssignedToViewer"])
            self.assertEqual(summary["collectionStatus"]["status"], "completed")
            self.assertEqual(summary["collectionStatus"]["cleanupErrors"], [])
            self.assertNotIn("pass", summary)
            self.assertNotIn("ac5", summary)

    def test_preflight_mismatch_writes_aborted_evidence_before_any_spawn(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "new"
            executable = Path(temp) / "mpv.exe"
            with patch.dict(os.environ, {"RULEGO_USER": "offline", "RULEGO_PASSWORD": "offline"}), \
                    patch.object(collector, "fetch_json",
                                 side_effect=[component_body(version="0.1.9"),
                                              shared_nodes_body(), chain_body()]), \
                    patch.object(collector.shutil, "which", return_value=str(executable)), \
                    patch.object(collector.subprocess, "Popen") as popen:
                self.assertEqual(collector.run(args_for(out)), 2)
            popen.assert_not_called()
            summary = json.loads((out / "summary.json").read_text())
            aborted = json.loads((out / "aborted.json").read_text())
            preflight = json.loads((out / "preflight.json").read_text())
            self.assertEqual(summary["collectionStatus"]["status"], "aborted")
            self.assertEqual(summary["collectionStatus"]["playersSpawned"], 0)
            self.assertFalse(summary["preflight"]["accepted"])
            self.assertEqual(aborted["stage"], "preflight")
            self.assertEqual(aborted["reason"], "preflight_mismatch")
            self.assertFalse(preflight["checks"]["resourceOriginVersion"])
            self.assertFalse((out / "consumer-events.jsonl").read_text())

    def test_initial_tail_failure_writes_aborted_evidence_without_a_player(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = self._mocked_run(temp, [[None], [None]], baseline_ok=False)
            self.assertEqual(fixture.result, 2)
            summary = json.loads((fixture.out / "summary.json").read_text())
            aborted = json.loads((fixture.out / "aborted.json").read_text())
            self.assertEqual(summary["collectionStatus"]["status"], "aborted")
            self.assertEqual(summary["collectionStatus"]["playersSpawned"], 0)
            self.assertEqual(aborted["stage"], "initial_telemetry")
            self.assertEqual(sum(1 for command in fixture.commands if "--_poll-worker" in command), 1)
            self.assertFalse(any("--start=" in argument for command in fixture.commands
                                 for argument in command))

    def test_launch_barrier_failure_stops_only_the_live_owned_player(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = self._mocked_run(temp, [[None, None], [0, 0]])
            self.assertEqual(fixture.result, 2)
            summary = json.loads((fixture.out / "summary.json").read_text())
            aborted = json.loads((fixture.out / "aborted.json").read_text())
            self.assertEqual(summary["collectionStatus"]["status"], "aborted")
            self.assertEqual(summary["collectionStatus"]["stopReason"], "launch_barrier_failed")
            self.assertEqual(aborted["stage"], "launch")
            self.assertEqual([call.args[0].pid for call in fixture.stop_owned.call_args_list],
                             [player.pid for player in fixture.players])
            self.assertEqual(sum(1 for command in fixture.commands if "--_poll-worker" in command), 1)

    def test_wall_deadline_stops_both_owned_players_and_keeps_partial_status(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = self._mocked_run(temp, [[None, None, None], [None, None, None]], wall=0.0)
            self.assertEqual(fixture.result, 2)
            summary = json.loads((fixture.out / "summary.json").read_text())
            self.assertEqual(summary["collectionStatus"]["status"], "partial")
            self.assertEqual(summary["collectionStatus"]["stopReason"], "wall_deadline")
            self.assertEqual(summary["collectionStatus"]["playersSpawned"], 2)
            self.assertFalse((fixture.out / "aborted.json").exists())
            self.assertEqual(fixture.stop_owned.call_count, 2)

    def test_interruption_stops_owned_players_and_preserves_partial_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = self._mocked_run(temp, [[None, None, None], [None, None, None]],
                                       interrupt_after_launch=True)
            self.assertEqual(fixture.result, 2)
            summary = json.loads((fixture.out / "summary.json").read_text())
            self.assertEqual(summary["collectionStatus"]["status"], "partial")
            self.assertEqual(summary["collectionStatus"]["stopReason"], "interrupted")
            self.assertEqual(fixture.stop_owned.call_count, 2)
            self.assertTrue((fixture.out / "lifecycle.jsonl").exists())

    def test_jsonl_refuses_overwrite_and_flushes_each_event(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "events.jsonl"
            writer = collector.JsonLines(path)
            try:
                writer.write({"ready": True})
                self.assertEqual(json.loads(path.read_text()), {"ready": True})
                with self.assertRaises(FileExistsError):
                    collector.JsonLines(path)
            finally:
                writer.close()

    def test_stop_only_owned_live_pid(self):
        process = Mock(pid=1234567)
        process.poll.return_value = None
        with patch.object(collector.subprocess, "run") as run, patch.object(collector.subprocess, "CREATE_NO_WINDOW", 0, create=True):
            self.assertTrue(collector.stop_owned(process))
        self.assertEqual(run.call_args.args[0], ["taskkill.exe", "/PID", "1234567", "/T", "/F"])
        process.poll.return_value = 0
        with patch.object(collector.subprocess, "run") as run:
            self.assertFalse(collector.stop_owned(process))
            run.assert_not_called()

    def test_failure_summary_does_not_erase_previous_failure_or_claim_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            events = collector.JsonLines(out / "server-events.jsonl")
            events.write(collector.sanitize_event(row(ts=2000, error="storage_limit", relation="Failure"), "commit"))
            events.write(collector.sanitize_event(row(ts=3000, data={"state": "ready", "size": 20}), "commit"))
            events.close()
            polls = collector.JsonLines(out / "polls.jsonl")
            polls.write({"phase": "final", "nodeId": "commit", "flags": []})
            polls.close()
            summary = collector.server_summary(out, 1, 4)
            self.assertEqual(summary["failureSignalsInClientClockWindow"], 1)
            self.assertEqual(summary["windowFailureCategories"], {"storage_limit": 1})
            self.assertIsNone(summary["retainedBytes"])
            self.assertFalse(summary["ledgerComplete"])


if __name__ == "__main__":
    unittest.main()
