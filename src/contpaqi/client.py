class ContpaqiClient:
    def __init__(self, base_url: str, subscription_key: str, license_code: str):
        self.base_url = base_url.rstrip("/")
        self.subscription_key = subscription_key
        self.license_code = license_code

    def _headers(self) -> dict:
        return {
            "Ocp-Apim-Subscription-Key": self.subscription_key,  # Subscription-Key
            "License-Code": self.license_code,                   # License-Code
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # --- Descargas ISV ---
    def get_public_key(self) -> dict:
        """Obtiene llave pública RSA (para cifrado híbrido FIEL)."""

    def create_isv_request(self, payload: dict) -> dict:
        """POST: crea solicitud de descarga -> operationID."""

    def get_isv_status(self, operation_id: str) -> dict:
        """GET: estado de la solicitud (Pendiente/Error/Rechazada/Terminado)."""

    def get_isv_urls(self, operation_id: str) -> dict:
        """GET: URLs de descarga (ZIPs XML + JSON metadata; expiran ~2h)."""

    # --- Timbrado (asíncrono) ---
    def timbrado_reserve(self, payload: dict) -> dict:
        """POST: reserva -> retorna fileID + presignedUrl (PUT binario)."""

    def timbrado_upload_put(self, presigned_url: str, content: bytes) -> int:
        """PUT binario a la URL presignada (204 en éxito)."""

    def timbrado_get_result(self, file_id: str) -> dict:
        """GET: resultado por fileID (TFD, estados, etc.)."""
