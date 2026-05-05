from __future__ import annotations

from benchmark.runner.adapter import convert_event


def test_cli_event_context_cwd_is_copied_to_payload() -> None:
    """Benchmark CLI events expose cwd in payload so script paths normalize correctly."""
    event = convert_event(
        {
            "event_id": "e1",
            "timestamp": "2026-01-01T00:00:00",
            "source": "cli",
            "speaker": "u_1",
            "content": "python tools/demo.py --env prod",
            "context": {
                "cwd": "/workspace/demo",
                "project": "Demo",
            },
            "exit_code": 0,
            "duration": 100,
        }
    )

    assert event.payload["cwd"] == "/workspace/demo"
    assert event.payload["exit_code"] == 0
    assert event.payload["duration"] == 100
