from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable

_DEFAULT_MAX_BYTES = 5 * 1024 * 1024
_DEFAULT_BACKUPS = 5


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


def panel_log_dir() -> Path:
    configured = os.getenv('DOCTOR_DEV_LOG_DIR', '').strip()
    if configured:
        return _writable_dir(Path(configured).expanduser(), 'logs')
    return _writable_dir(Path('/var/log/doctor-dev-panel'), 'logs')


def panel_log_file() -> Path:
    configured = os.getenv('DOCTOR_DEV_PANEL_LOG_FILE', '').strip()
    if configured:
        path = Path(configured).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return panel_log_dir() / 'panel.log'


def setup_panel_logging() -> Path:
    path = panel_log_file()
    root = logging.getLogger()
    root.setLevel(os.getenv('PYTHON_LOG_LEVEL', 'INFO').upper())
    marker = str(path.resolve())
    for handler in root.handlers:
        if getattr(handler, '_doctor_dev_log_file', None) == marker:
            return path
    handler = RotatingFileHandler(path, maxBytes=int(os.getenv('DOCTOR_DEV_LOG_MAX_BYTES', str(_DEFAULT_MAX_BYTES))), backupCount=int(os.getenv('DOCTOR_DEV_LOG_BACKUPS', str(_DEFAULT_BACKUPS))), encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)sZ | %(levelname)s | %(name)s | %(message)s', '%Y-%m-%dT%H:%M:%S'))
    handler._doctor_dev_log_file = marker  # type: ignore[attr-defined]
    root.addHandler(handler)
    logging.getLogger('doctor_dev_panel').info('panel logging ready: %s', path)
    return path


def tail_file(path: str | os.PathLike[str], limit: int = 200) -> list[str]:
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
