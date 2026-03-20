from pathlib import Path
from dataclasses import dataclass
from satcfdi.models import Signer

# NUEVO: leer vigencia directo del .cer con cryptography
from cryptography import x509
from cryptography.hazmat.backends import default_backend

@dataclass
class CertInfo:
    subject: str
    rfc: str
    not_before: str
    not_after: str

class SignerService:
    def __init__(self, cer_path: Path, key_path: Path, pwd_path: Path):
        self.cer_path = Path(cer_path)
        self.key_path = Path(key_path)
        self.pwd_path = Path(pwd_path)

    def load_signer(self) -> Signer:
        password = self.pwd_path.read_text(encoding="utf-8").strip()
        signer = Signer.load(
            certificate=self.cer_path.read_bytes(),
            key=self.key_path.read_bytes(),
            password=password,
        )
        return signer

    def _leer_vigencia_desde_cer(self):
        # El .cer del SAT suele venir en DER
        raw = self.cer_path.read_bytes()
        cert = x509.load_der_x509_certificate(raw, default_backend())
        # Si alguna vez tuvieras PEM, usarías: x509.load_pem_x509_certificate(...)
        nb = cert.not_valid_before
        na = cert.not_valid_after
        # Normalizamos a string ISO
        return nb.isoformat(), na.isoformat()

    def get_info(self) -> CertInfo:
        signer = self.load_signer()

        # RFC (satcfdi lo expone normalmente en signer.rfc)
        rfc = getattr(signer, "rfc", "N/A")

        # Subject (no siempre viene estructurado igual en satcfdi)
        try:
            subject = signer.certificate.subject.rfc  # puede no existir
        except Exception:
            # Como alternativa, usamos el propio RFC
            subject = rfc

        # Vigencia real desde .cer
        try:
            not_before, not_after = self._leer_vigencia_desde_cer()
        except Exception:
            # Fallback si algo raro pasa
            not_before = "N/A"
            not_after = "N/A"

        return CertInfo(subject=subject, rfc=rfc, not_before=not_before, not_after=not_after)
