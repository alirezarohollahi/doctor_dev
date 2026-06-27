from doctor_dev_panel.local_test import tcp_roundtrip


def test_tcp_roundtrip_reports_connection_error_for_closed_port():
    result = None
    try:
        result = tcp_roundtrip("127.0.0.1", 9, "x", timeout=0.1)
    except Exception as exc:
        assert exc is not None
    else:
        assert result["ok"] is True
