from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Iterable, Union

_TRUE_VALUES = {"1", "true", "yes", "on", "debug", "enabled"}
_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "private_key",
    "ssl_key_file",
    "ssl_key_path",
    "key_file",
    "key_path",
    "certificate",
    "cert",
}


def env_flag(*names: str, default: bool = False) -> bool:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        return str(value).strip().lower() in _TRUE_VALUES
    return default


def is_debug_enabled() -> bool:
    return env_flag("DEBUG", "debug", "DOCTOR_DEV_DEBUG", "DOCTOR_DEV_NODE_DEBUG", default=False)


def effective_log_level(default: str = "INFO") -> str:
    if is_debug_enabled():
        return "DEBUG"
    return os.getenv("PYTHON_LOG_LEVEL", default).upper()


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or any(part in normalized for part in ("password", "secret", "token", "api_key", "private_key"))


def redact_debug_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): ("***REDACTED***" if _is_sensitive_key(str(k)) else redact_debug_value(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_debug_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_debug_value(item) for item in value)
    return value


def redact_headers(headers: Any) -> dict[str, str]:
    try:
        pairs = dict(headers)
    except Exception:
        pairs = {}
    result: dict[str, str] = {}
    for key, value in pairs.items():
        result[str(key)] = "***REDACTED***" if _is_sensitive_key(str(key)) else str(value)
    return result


def debug_json(value: Any, *, max_chars: int = 8000) -> str:
    import json
    try:
        text = json.dumps(redact_debug_value(value), ensure_ascii=False, default=str)
    except Exception:
        text = str(redact_debug_value(value))
    if len(text) > max_chars:
        return text[:max_chars] + f"... <truncated {len(text) - max_chars} chars>"
    return text


def body_preview(raw: bytes, *, max_chars: int = 8000) -> str:
    if not raw:
        return ""
    text = raw[:max_chars].decode("utf-8", errors="replace")
    try:
        import json
        parsed = json.loads(text)
        return debug_json(parsed, max_chars=max_chars)
    except Exception:
        if len(raw) > max_chars:
            return text + f"... <truncated {len(raw) - max_chars} bytes>"
        return text



def _writable_dir(preferred: Path, fallback_name: str) -> Path:
    candidates = [preferred]
    if str(preferred).startswith('/var/'):
        candidates.append(Path.cwd() / fallback_name)
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / '.write-test'
            probe.write_text('ok', encoding='utf-8')
            probe.unlink(missing_ok=True)
            return candidate
        except Exception:
            continue
    fallback = Path.cwd() / fallback_name
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def node_log_dir() -> Path:
    configured = os.getenv('DOCTOR_DEV_NODE_LOG_DIR', '').strip()
    if configured:
        return _writable_dir(Path(configured).expanduser(), 'logs')
    return _writable_dir(Path('/var/log/doctor-node'), 'logs')


def node_log_file() -> Path:
    configured = os.getenv('DOCTOR_DEV_NODE_LOG_FILE', '').strip()
    if configured:
        path = Path(configured).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return node_log_dir() / 'node.log'


def setup_node_logging() -> Path:
    path = node_log_file()
    root = logging.getLogger()
    root.setLevel(effective_log_level('INFO'))
    if is_debug_enabled():
        for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access', 'asyncio'):
            logging.getLogger(name).setLevel(logging.DEBUG)
    marker = str(path.resolve())
    for handler in root.handlers:
        if getattr(handler, '_doctor_dev_log_file', None) == marker:
            return path
    handler = logging.FileHandler(path, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)sZ | %(levelname)s | %(name)s | %(message)s', '%Y-%m-%dT%H:%M:%S'))
    handler._doctor_dev_log_file = marker  # type: ignore[attr-defined]
    root.addHandler(handler)
    logging.getLogger('doctor_dev_node').info('node logging ready: %s debug=%s level=%s', path, is_debug_enabled(), logging.getLevelName(root.level))
    return path


def tail_file(path: Union[str, os.PathLike[str]], limit: int = 200) -> list[str]:
    limit = max(1, min(int(limit or 200), 5000))
    file_path = Path(path).expanduser()
    if not file_path.exists() or not file_path.is_file():
        return []
    with file_path.open('rb') as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        block = 8192
        data = b''
        pos = size
        while pos > 0 and data.count(b'\n') <= limit:
            read_size = min(block, pos)
            pos -= read_size
            handle.seek(pos)
            data = handle.read(read_size) + data
    lines = data.decode('utf-8', errors='replace').splitlines()
    return lines[-limit:]


def filter_lines(lines: Iterable[str], *, level: str = 'all', query: str = '') -> list[str]:
    level = (level or 'all').lower().strip()
    query = (query or '').lower().strip()
    result: list[str] = []
    for line in lines:
        text = line.lower()
        if level != 'all' and f'| {level.upper()} |'.lower() not in text and f' {level} ' not in text:
            continue
        if query and query not in text:
            continue
        result.append(line)
    return result




