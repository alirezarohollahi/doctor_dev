from doctor_dev_agent import cli as node_cli


def test_runtime_cli_uses_api_runtime(monkeypatch, capsys):
    calls = []

    def fake_request_json(name, path):
        calls.append((name, path))
        return {"ok": True}

    monkeypatch.setattr(node_cli, "request_json", fake_request_json)
    args = type("Args", (), {"name": "edge-node-1"})()
    node_cli.cmd_runtime(args)
    assert calls == [("edge-node-1", "/api/runtime")]
    assert '"ok": true' in capsys.readouterr().out
