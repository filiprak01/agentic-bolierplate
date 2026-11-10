import json
import sys
from pathlib import Path

from agentic_boilerplate.runtime import CodexAppServerLiveStatusReader, summarize_codex_subscription_auth


def test_live_status_reader_reads_account_before_rate_limits(tmp_path: Path) -> None:
    calls_path = tmp_path / "calls.json"
    fixture = _write_live_protocol_fixture(tmp_path)
    reader = CodexAppServerLiveStatusReader(
        command=[sys.executable, str(fixture), str(calls_path)],
        timeout_seconds=3,
        initialization_timeout_seconds=1,
        read_timeout_seconds=1,
    )

    payload = reader.read()

    assert payload.account["authMode"] == "chatgpt"
    assert payload.rate_limits["rateLimits"]["primary"]["usedPercent"] == 22
    calls = json.loads(calls_path.read_text(encoding="utf-8"))
    assert calls == ["initialize", "initialized", "account/read", "account/rateLimits/read"]


def test_subscription_auth_summary_fails_closed_for_api_key_payload() -> None:
    summary = summarize_codex_subscription_auth(
        {"authentication": {"mode": "API key", "apiKey": "sk-secret"}, "status": "authenticated"},
        rate_limits_payload={"planType": "prolite"},
    )

    assert summary.authenticated is False
    assert summary.subscription_auth is False
    assert "API key" in summary.reason
    assert "sk-secret" not in summary.reason


def _write_live_protocol_fixture(tmp_path: Path) -> Path:
    script = tmp_path / "live_protocol_fixture.py"
    script.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "calls_path = sys.argv[1]",
                "calls = []",
                "def record(method):",
                "    calls.append(method)",
                "    with open(calls_path, 'w', encoding='utf-8') as calls_file:",
                "        json.dump(calls, calls_file)",
                "for line in sys.stdin:",
                "    message = json.loads(line)",
                "    method = message.get('method')",
                "    record(method)",
                "    if method == 'initialize':",
                "        print(json.dumps({'id': message['id'], 'result': {}}), flush=True)",
                "    elif method == 'account/read':",
                "        print(json.dumps({'id': message['id'], 'result': {'authMode': 'chatgpt', 'accountType': 'subscription', 'planType': 'prolite', 'status': 'authenticated'}}), flush=True)",
                "    elif method == 'account/rateLimits/read':",
                "        result = {'rateLimits': {'limitId': 'codex', 'planType': 'prolite', 'primary': {'usedPercent': 22, 'resetsAt': '2026-09-19T12:00:00Z'}}}",
                "        print(json.dumps({'id': message['id'], 'result': result}), flush=True)",
            ]
        ),
        encoding="utf-8",
    )
    return script
