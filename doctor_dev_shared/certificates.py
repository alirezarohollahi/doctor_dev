from __future__ import annotations

import re
import ssl
import tempfile
from pathlib import Path
from typing import Any

from .models import CertificateMode, CertificateRef, CertificateValidationRequest, CertificateValidationResult

_CERT_RE = re.compile(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.S)
_KEY_MARKERS = ("-----BEGIN PRIVATE KEY-----", "-----BEGIN RSA PRIVATE KEY-----", "-----BEGIN EC PRIVATE KEY-----")


def _read_text(path: str | None) -> tuple[str | None, str | None]:
    if not path:
        return None, "path is empty"
    p = Path(path).expanduser()
    if not p.exists() or not p.is_file():
        return None, f"file not found: {p}"
    try:
        return p.read_text(encoding="utf-8"), None
    except UnicodeDecodeError:
        return p.read_text(encoding="utf-8", errors="replace"), None


def _has_cert_pem(value: str | None) -> bool:
    return bool(value and _CERT_RE.search(value))


def _has_key_pem(value: str | None) -> bool:
    return bool(value and any(marker in value for marker in _KEY_MARKERS))


def _try_ssl_chain(fullchain: str, privkey: str) -> tuple[bool, str | None]:
    with tempfile.TemporaryDirectory() as td:
        cert_path = Path(td) / "fullchain.pem"
        key_path = Path(td) / "privkey.pem"
        cert_path.write_text(fullchain, encoding="utf-8")
        key_path.write_text(privkey, encoding="utf-8")
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            ctx.load_cert_chain(str(cert_path), str(key_path))
            return True, None
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)


def certificate_ref_from_request(req: CertificateValidationRequest) -> CertificateRef:
    return CertificateRef(
        enabled=True,
        mode=req.mode,
        domain=req.domain,
        fullchain_path=req.fullchain_path,
        privkey_path=req.privkey_path,
        fullchain_content=req.fullchain_content,
        privkey_content=req.privkey_content,
    )


def validate_certificate_ref(ref: CertificateRef, *, panel_can_read_paths: bool = True) -> CertificateValidationResult:
    if not ref.enabled:
        return CertificateValidationResult(ok=True, mode=str(ref.mode), domain=ref.domain, message="TLS is disabled")

    # Pydantic validates required fields first.
    ref = CertificateRef.model_validate(ref.model_dump())
    warnings: list[str] = []
    details: dict[str, Any] = {}
    fullchain = ref.fullchain_content
    privkey = ref.privkey_content

    if ref.mode == CertificateMode.file_on_node:
        # The panel cannot safely prove a path exists on a remote node without calling the agent.
        warnings.append("file_on_node paths are syntactically valid, but existence is checked by the target agent during apply")
        return CertificateValidationResult(ok=True, mode=str(ref.mode), domain=ref.domain, message="node certificate paths accepted", warnings=warnings, details={"fullchain_path": ref.fullchain_path, "privkey_path": ref.privkey_path})

    if ref.mode in {CertificateMode.file_on_panel, CertificateMode.uploaded_from_host}:
        if panel_can_read_paths:
            fullchain, err1 = _read_text(ref.fullchain_path)
            privkey, err2 = _read_text(ref.privkey_path)
            if err1 or err2:
                return CertificateValidationResult(ok=False, mode=str(ref.mode), domain=ref.domain, message="certificate file validation failed", warnings=[err for err in [err1, err2] if err], details={"fullchain_path": ref.fullchain_path, "privkey_path": ref.privkey_path})
            details["fullchain_path"] = ref.fullchain_path
            details["privkey_path"] = ref.privkey_path

    if not _has_cert_pem(fullchain):
        return CertificateValidationResult(ok=False, mode=str(ref.mode), domain=ref.domain, message="fullchain does not contain a certificate PEM block", warnings=warnings, details=details)
    if not _has_key_pem(privkey):
        return CertificateValidationResult(ok=False, mode=str(ref.mode), domain=ref.domain, message="privkey does not contain a private key PEM block", warnings=warnings, details=details)

    loaded, error = _try_ssl_chain(fullchain or "", privkey or "")
    details["pem_blocks_present"] = True
    details["ssl_chain_loaded"] = loaded
    if error:
        warnings.append(f"cryptographic load_cert_chain check failed: {error}")

    return CertificateValidationResult(ok=True, mode=str(ref.mode), domain=ref.domain, message="certificate material is present and readable", warnings=warnings, details=details)
