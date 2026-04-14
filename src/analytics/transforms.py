from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class TransformResult:
    cfdi_rows: list[dict[str, Any]]
    pagos_rows: list[dict[str, Any]]


CFDI_COLUMN_ALIASES: dict[str, list[str]] = {
    "uuid": ["UUID", "Uuid", "uuid"],
    "tipo_cfdi": ["TIPO_COMPROB", "TIPO_COMPROBANTE", "TipoDeComprobante", "tipo_cfdi"],
    "fecha_emision": ["FECHA", "Fecha", "fecha_emision", "Fecha_Emision"],
    "rfc_emisor": ["EMISOR_RFC", "RFC_EMISOR", "rfc_emisor"],
    "nombre_emisor": ["EMISOR_NOMBRE", "NOMBRE_EMISOR", "nombre_emisor"],
    "rfc_receptor": ["RECEPTOR_RFC", "RFC_RECEPTOR", "rfc_receptor"],
    "nombre_receptor": ["RECEPTOR_NOMBRE", "NOMBRE_RECEPTOR", "nombre_receptor"],
    "subtotal": ["SUBTOTAL", "Subtotal", "subtotal"],
    "descuento": ["DESCUENTO", "Descuento", "descuento"],
    "total": ["TOTAL", "Total", "total"],
    "moneda": ["MONEDA", "Moneda", "moneda"],
    "tipo_cambio": ["TIPO_CAMBIO", "TipoCambio", "tipo_cambio"],
    "metodo_pago": ["METODO_PAGO", "MetodoPago", "metodo_pago"],
    "forma_pago": ["FORMA_PAGO", "FormaPago", "forma_pago"],
    "uso_cfdi": ["USO_CFDI", "UsoCFDI", "uso_cfdi"],
    "estatus_cancelado": ["ESTATUS_CANCELADO", "STATUS_CANCELADO", "estatus_cancelado"],
    "uuid_factura_relacionada": [
        "UUID_FACTURA_RELACIONADA",
        "UUID_RELACIONADO",
        "DoctoRelacionado_UUID",
        "uuid_factura_relacionada",
    ],
}


def read_excel_safe(path: Path) -> pd.DataFrame:
    """
    Lee un Excel y devuelve DataFrame.
    """
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo Excel: {path}")

    df = pd.read_excel(path)
    if df is None:
        return pd.DataFrame()

    return df.copy()


def transform_company_period_context(context: dict[str, Any]) -> TransformResult:
    """
    Transforma un contexto empresa-periodo en listas de filas normalizadas
    para tablas cfdi y pagos.
    """
    cfdi_rows: list[dict[str, Any]] = []
    pagos_rows: list[dict[str, Any]] = []

    rfc_empresa = str(context["rfc"]).strip().upper()
    periodo = str(context["periodo"]).strip()

    emitidas_path = context.get("emitidas_excel")
    recibidas_path = context.get("recibidas_excel")

    if emitidas_path:
        df_emitidas = read_excel_safe(Path(emitidas_path))
        result_emitidas = transform_excel_to_rows(
            df=df_emitidas,
            rfc_empresa=rfc_empresa,
            periodo=periodo,
            rol="EMITIDA",
            source_file=str(emitidas_path),
        )
        cfdi_rows.extend(result_emitidas.cfdi_rows)
        pagos_rows.extend(result_emitidas.pagos_rows)

    if recibidas_path:
        df_recibidas = read_excel_safe(Path(recibidas_path))
        result_recibidas = transform_excel_to_rows(
            df=df_recibidas,
            rfc_empresa=rfc_empresa,
            periodo=periodo,
            rol="RECIBIDA",
            source_file=str(recibidas_path),
        )
        cfdi_rows.extend(result_recibidas.cfdi_rows)
        pagos_rows.extend(result_recibidas.pagos_rows)

    return TransformResult(cfdi_rows=cfdi_rows, pagos_rows=pagos_rows)


def transform_excel_to_rows(
    df: pd.DataFrame,
    rfc_empresa: str,
    periodo: str,
    rol: str,
    source_file: str,
) -> TransformResult:
    """
    Convierte un DataFrame de Excel a filas normalizadas para cfdi y pagos.
    """
    if df.empty:
        return TransformResult(cfdi_rows=[], pagos_rows=[])

    column_map = resolve_column_aliases(df.columns.tolist(), CFDI_COLUMN_ALIASES)

    cfdi_rows: list[dict[str, Any]] = []
    pagos_rows: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        uuid = normalize_text(get_value(row, column_map, "uuid"))
        if not uuid:
            continue

        tipo_cfdi = normalize_text(get_value(row, column_map, "tipo_cfdi"))
        fecha_emision = normalize_date(get_value(row, column_map, "fecha_emision"))

        subtotal = to_float(get_value(row, column_map, "subtotal"))
        descuento = to_float(get_value(row, column_map, "descuento"))
        total = to_float(get_value(row, column_map, "total"))

        moneda = normalize_text(get_value(row, column_map, "moneda")) or "MXN"
        tipo_cambio = to_float(get_value(row, column_map, "tipo_cambio"), default=1.0)
        total_mxn = calculate_total_mxn(total=total, moneda=moneda, tipo_cambio=tipo_cambio)

        cfdi_record = {
            "uuid": uuid,
            "rfc_empresa": rfc_empresa,
            "periodo": periodo,
            "rol": rol,
            "tipo_cfdi": tipo_cfdi,
            "fecha_emision": fecha_emision,
            "rfc_emisor": normalize_rfc(get_value(row, column_map, "rfc_emisor")),
            "nombre_emisor": normalize_text(get_value(row, column_map, "nombre_emisor")),
            "rfc_receptor": normalize_rfc(get_value(row, column_map, "rfc_receptor")),
            "nombre_receptor": normalize_text(get_value(row, column_map, "nombre_receptor")),
            "subtotal": subtotal,
            "descuento": descuento,
            "total": total,
            "moneda": moneda,
            "tipo_cambio": tipo_cambio,
            "total_mxn": total_mxn,
            "metodo_pago": normalize_text(get_value(row, column_map, "metodo_pago")),
            "forma_pago": normalize_text(get_value(row, column_map, "forma_pago")),
            "uso_cfdi": normalize_text(get_value(row, column_map, "uso_cfdi")),
            "estatus_cancelado": normalize_text(get_value(row, column_map, "estatus_cancelado")),
            "source_file": source_file,
        }
        cfdi_rows.append(cfdi_record)

        if tipo_cfdi == "P":
            pagos_rows.append(
                {
                    "uuid_pago": uuid,
                    "uuid_factura_relacionada": normalize_text(
                        get_value(row, column_map, "uuid_factura_relacionada")
                    ),
                    "rfc_empresa": rfc_empresa,
                    "periodo": periodo,
                    "fecha_pago": fecha_emision,
                    "monto_pago": total,
                    "moneda": moneda,
                    "tipo_cambio": tipo_cambio,
                    "monto_pago_mxn": total_mxn,
                    "rfc_emisor_pago": normalize_rfc(get_value(row, column_map, "rfc_emisor")),
                    "rfc_receptor_pago": normalize_rfc(get_value(row, column_map, "rfc_receptor")),
                }
            )

    return TransformResult(cfdi_rows=cfdi_rows, pagos_rows=pagos_rows)


def resolve_column_aliases(
    columns: list[str],
    aliases: dict[str, list[str]],
) -> dict[str, str | None]:
    """
    Mapea nombres lógicos a columnas reales encontradas en el DataFrame.
    """
    normalized_lookup = {normalize_col_name(col): col for col in columns}
    resolved: dict[str, str | None] = {}

    for logical_name, options in aliases.items():
        found = None
        for option in options:
            normalized_option = normalize_col_name(option)
            if normalized_option in normalized_lookup:
                found = normalized_lookup[normalized_option]
                break
        resolved[logical_name] = found

    return resolved


def get_value(row: pd.Series, column_map: dict[str, str | None], logical_name: str) -> Any:
    real_col = column_map.get(logical_name)
    if not real_col:
        return None
    return row.get(real_col)


def normalize_col_name(value: str) -> str:
    return str(value).strip().lower().replace(" ", "_")


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def normalize_rfc(value: Any) -> str | None:
    text = normalize_text(value)
    return text.upper() if text else None


def normalize_date(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None

    try:
        ts = pd.to_datetime(value, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.strftime("%Y-%m-%d")
    except Exception:
        return None


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None or pd.isna(value):
        return default

    try:
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        return float(value)
    except Exception:
        return default


def calculate_total_mxn(total: float, moneda: str, tipo_cambio: float) -> float:
    # R8 ya exporta la columna TOTAL con el importe final normalizado
    # como se muestra en el Excel. Si se vuelve a aplicar tipo de cambio
    # aqui, los montos en moneda extranjera se inflan en analytics.
    return total


if __name__ == "__main__":
    try:
        from src.analytics.loader import build_company_period_context
    except ModuleNotFoundError:
        import sys

        project_root = Path(__file__).resolve().parents[2]
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from src.analytics.loader import build_company_period_context

    periodo_demo = "2026-03"
    contexts = build_company_period_context(periodo_demo)

    if not contexts:
        print(f"No se encontraron contextos para {periodo_demo}")
    else:
        first = contexts[0]
        result = transform_company_period_context(first)
        print(f"RFC: {first['rfc']}")
        print(f"Periodo: {first['periodo']}")
        print(f"CFDI rows: {len(result.cfdi_rows)}")
        print(f"Pagos rows: {len(result.pagos_rows)}")

        if result.cfdi_rows:
            print("Primer CFDI:")
            print(result.cfdi_rows[0])

        if result.pagos_rows:
            print("Primer pago:")
            print(result.pagos_rows[0])
