from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd

from .catalog import nombre_cliente
from .models import Alert, ClientPeriodData
from .settings import PATHS


def crear_alerta_consolidada(
    rfc: str,
    nombre: str,
    periodo: str,
    tipo_alerta: str,
    severidad: str,
    resumen: str,
    detalle: str,
    cantidad: int = 1,
    monto_total: float = 0.0,
    uuids: list[str] | None = None,
) -> Alert:
    return Alert(
        rfc=rfc,
        nombre=nombre,
        periodo=periodo,
        tipo_alerta=tipo_alerta,
        severidad=severidad,
        resumen=resumen,
        detalle=detalle,
        cantidad=cantidad,
        monto_total=monto_total,
        uuids=uuids or [],
    )


def regla_ingresos_altos(datos: ClientPeriodData, cfg: dict[str, Any], clientes: dict[str, Any]) -> list[Alert]:
    alertas: list[Alert] = []
    rcfg = cfg["reglas"].get("ingreso_alto", {})
    if not rcfg.get("habilitado", True):
        return alertas

    df = datos.df_e
    if df.empty:
        return alertas

    umbral = rcfg.get("umbral_mxn", 200000)
    ingresos = df[df["TIPO_COMPROB"] == "I"]
    altos = ingresos[ingresos["SUBTOTAL_MXN"] > umbral]
    if altos.empty:
        return alertas

    uuids = altos["UUID"].tolist()
    monto = round(altos["SUBTOTAL_MXN"].sum(), 2)
    clientes_involucrados = altos["RECEPTOR_NOMBRE"].unique().tolist()

    alertas.append(
        crear_alerta_consolidada(
            rfc=datos.rfc,
            nombre=nombre_cliente(datos.rfc, clientes),
            periodo=datos.periodo,
            tipo_alerta="INGRESO_ALTO",
            severidad=rcfg.get("severidad", "ALTA"),
            resumen=f"{len(altos)} ingreso(s) superior(es) a ${umbral:,.0f} MXN - Total: ${monto:,.2f} MXN",
            detalle=(
                f"Se detectaron {len(altos)} CFDIs de ingreso que superan el umbral de ${umbral:,.0f} MXN. "
                f"Clientes: {', '.join(clientes_involucrados[:3])}{'...' if len(clientes_involucrados) > 3 else ''}. "
                "Verificar que el origen de cada ingreso este correctamente clasificado ante el SAT."
            ),
            cantidad=len(altos),
            monto_total=monto,
            uuids=uuids,
        )
    )
    return alertas


def regla_concentracion_cliente(datos: ClientPeriodData, cfg: dict[str, Any], clientes: dict[str, Any]) -> list[Alert]:
    alertas: list[Alert] = []
    rcfg = cfg["reglas"].get("concentracion_cliente", {})
    if not rcfg.get("habilitado", True):
        return alertas

    df = datos.df_e
    if df.empty:
        return alertas

    ingresos = df[df["TIPO_COMPROB"] == "I"]
    total_mes = ingresos["SUBTOTAL_MXN"].sum()
    if total_mes == 0:
        return alertas

    porcentaje_maximo = rcfg.get("porcentaje_maximo", 70)
    nombre = nombre_cliente(datos.rfc, clientes)
    for cliente_nom, monto in ingresos.groupby("RECEPTOR_NOMBRE")["SUBTOTAL_MXN"].sum().items():
        porcentaje = (monto / total_mes) * 100
        if porcentaje > porcentaje_maximo:
            alertas.append(
                crear_alerta_consolidada(
                    rfc=datos.rfc,
                    nombre=nombre,
                    periodo=datos.periodo,
                    tipo_alerta="CONCENTRACION_CLIENTE",
                    severidad=rcfg.get("severidad", "BAJA"),
                    resumen=f"{cliente_nom} representa el {porcentaje:.1f}% del ingreso del periodo",
                    detalle=(
                        f"Alta dependencia de un solo cliente: {cliente_nom} "
                        f"(${monto:,.2f} de ${total_mes:,.2f} MXN total). "
                        "Riesgo de liquidez si este cliente reduce o cancela operaciones."
                    ),
                    monto_total=round(monto, 2),
                )
            )
    return alertas


def regla_tipo_cambio_anomalo(datos: ClientPeriodData, cfg: dict[str, Any], clientes: dict[str, Any]) -> list[Alert]:
    alertas: list[Alert] = []
    rcfg = cfg["reglas"].get("tipo_cambio_anomalo", {})
    if not rcfg.get("habilitado", True):
        return alertas

    df = datos.df_e
    if df.empty:
        return alertas

    tc_min = rcfg.get("rango_minimo", 16.0)
    tc_max = rcfg.get("rango_maximo", 22.0)
    usd = df[(df["MONEDA"] == "USD") & (df["TIPO_CAMBIO"] > 0)]
    anomalos = usd[(usd["TIPO_CAMBIO"] < tc_min) | (usd["TIPO_CAMBIO"] > tc_max)]
    if anomalos.empty:
        return alertas

    alertas.append(
        crear_alerta_consolidada(
            rfc=datos.rfc,
            nombre=nombre_cliente(datos.rfc, clientes),
            periodo=datos.periodo,
            tipo_alerta="TIPO_CAMBIO_ANOMALO",
            severidad=rcfg.get("severidad", "MEDIA"),
            resumen=f"{len(anomalos)} CFDI(s) en USD con tipo de cambio fuera del rango ${tc_min:.2f}-${tc_max:.2f}",
            detalle=(
                f"Se detectaron {len(anomalos)} CFDIs en USD con tipo de cambio atipico. "
                f"Rango esperado: ${tc_min:.2f}-${tc_max:.2f}. "
                "Verificar contra tipo de cambio publicado por Banco de Mexico."
            ),
            cantidad=len(anomalos),
            monto_total=round(anomalos["SUBTOTAL_MXN"].sum(), 2),
            uuids=anomalos["UUID"].tolist(),
        )
    )
    return alertas


def regla_pagos_sin_match(
    datos: ClientPeriodData,
    cfg: dict[str, Any],
    clientes: dict[str, Any],
    logger: logging.Logger,
) -> list[Alert]:
    alertas: list[Alert] = []
    rcfg = cfg["reglas"].get("pago_sin_ingreso", {})
    if not rcfg.get("habilitado", True):
        return alertas

    if datos.df_r.empty:
        return alertas

    pagos = datos.df_r[datos.df_r["TIPO_COMPROB"] == "P"]
    if pagos.empty:
        return alertas

    path_recibidas = PATHS.exports_dir / datos.rfc / datos.periodo / f"{datos.rfc}_{datos.periodo}_RECIBIDAS_Facturas.xlsx"
    df_pagos = pd.DataFrame()
    if path_recibidas.exists():
        try:
            df_pagos = pd.read_excel(path_recibidas, sheet_name="PAGOS")
        except Exception as exc:
            logger.debug("No se pudo leer hoja PAGOS de %s: %s", path_recibidas.name, exc)

    if df_pagos.empty or "UUID_FACTURA_RELACIONADA" not in df_pagos.columns:
        logger.debug(
            "Se omite regla pago_sin_ingreso para %s %s: hoja PAGOS sin UUID_FACTURA_RELACIONADA disponible.",
            datos.rfc,
            datos.periodo,
        )
        return alertas

    df_pagos = df_pagos.copy()
    df_pagos["UUID_FACTURA_RELACIONADA"] = (
        df_pagos["UUID_FACTURA_RELACIONADA"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .replace({"NAN": "", "NONE": ""})
    )

    pagos_sin_uuid_rel = df_pagos[df_pagos["UUID_FACTURA_RELACIONADA"] == ""]
    pagos_con_uuid_rel = df_pagos[df_pagos["UUID_FACTURA_RELACIONADA"] != ""]

    if not pagos_con_uuid_rel.empty:
        logger.debug(
            "Se ignoran %s complemento(s) de pago con UUID relacionado informado en %s %s aunque la factura sea de otro periodo.",
            len(pagos_con_uuid_rel),
            datos.rfc,
            datos.periodo,
        )

    if pagos_sin_uuid_rel.empty:
        return alertas

    uuids = pagos_sin_uuid_rel["UUID_PAGO"].dropna().unique().tolist() if "UUID_PAGO" in pagos_sin_uuid_rel.columns else []
    monto = (
        round(pd.to_numeric(pagos_sin_uuid_rel["IMPORTE_PAGADO"], errors="coerce").fillna(0.0).sum(), 2)
        if "IMPORTE_PAGADO" in pagos_sin_uuid_rel.columns
        else 0.0
    )

    alertas.append(
        crear_alerta_consolidada(
            rfc=datos.rfc,
            nombre=nombre_cliente(datos.rfc, clientes),
            periodo=datos.periodo,
            tipo_alerta="PAGO_SIN_FACTURA_RELACIONADA",
            severidad=rcfg.get("severidad", "MEDIA"),
            resumen=f"{len(pagos_sin_uuid_rel)} complemento(s) de pago sin UUID de factura relacionada en el periodo",
            detalle=(
                f"Se recibieron {len(pagos_sin_uuid_rel)} complementos de pago cuyo campo "
                "UUID_FACTURA_RELACIONADA viene vacio en la hoja PAGOS. "
                "Solo estos casos se consideran alerta, porque un UUID informado puede corresponder "
                "normalmente a una factura emitida en un periodo anterior."
            ),
            cantidad=len(pagos_sin_uuid_rel),
            monto_total=monto,
            uuids=uuids[:10],
        )
    )
    return alertas


def regla_vencimientos_sat(cfg: dict[str, Any], periodo: str) -> list[Alert]:
    alertas: list[Alert] = []
    rcfg = cfg["reglas"].get("vencimientos_sat", {})
    if not rcfg.get("habilitado", True):
        return alertas

    hoy = date.today()
    dias_anticipacion = rcfg.get("dias_anticipacion", 5)
    year, month = map(int, periodo.split("-"))
    month_next = month + 1 if month < 12 else 1
    year_next = year if month < 12 else year + 1
    fecha_vencimiento = date(year_next, month_next, 17)
    dias_restantes = (fecha_vencimiento - hoy).days

    if 0 <= dias_restantes <= dias_anticipacion:
        alertas.append(
            crear_alerta_consolidada(
                rfc="DESPACHO",
                nombre="Sis Rodriguez",
                periodo=periodo,
                tipo_alerta="VENCIMIENTO_SAT",
                severidad="ALTA" if dias_restantes <= 2 else "MEDIA",
                resumen=f"Declaracion mensual ISR/IVA vence en {dias_restantes} dia(s) - {fecha_vencimiento.strftime('%d/%m/%Y')}",
                detalle=(
                    f"La declaracion mensual de ISR e IVA correspondiente a {periodo} "
                    f"vence el {fecha_vencimiento.strftime('%d/%m/%Y')}. "
                    "Asegurarse de que todos los clientes esten al corriente para presentar en tiempo."
                ),
            )
        )
    return alertas


def evaluar_cliente_periodo(
    datos: ClientPeriodData,
    cfg: dict[str, Any],
    clientes: dict[str, Any],
    logger: logging.Logger,
) -> list[Alert]:
    alertas: list[Alert] = []
    alertas.extend(regla_ingresos_altos(datos, cfg, clientes))
    alertas.extend(regla_concentracion_cliente(datos, cfg, clientes))
    alertas.extend(regla_tipo_cambio_anomalo(datos, cfg, clientes))
    alertas.extend(regla_pagos_sin_match(datos, cfg, clientes, logger))
    return alertas


def evaluar_todos(
    periodo: str,
    cfg: dict[str, Any],
    clientes: dict[str, Any],
    logger: logging.Logger,
    discover_rfcs,
    load_client_data,
) -> list[Alert]:
    rfcs = discover_rfcs(periodo)
    if not rfcs:
        logger.warning("No se encontraron Excel para el periodo %s", periodo)
        return []

    logger.info("RFCs con datos para %s: %s", periodo, rfcs)
    alertas: list[Alert] = []
    for rfc in rfcs:
        datos = load_client_data(rfc, periodo, logger)
        alerta_cliente = evaluar_cliente_periodo(datos, cfg, clientes, logger)
        alertas.extend(alerta_cliente)
        logger.info("  %s: %s alerta(s)", rfc, len(alerta_cliente))

    alertas.extend(regla_vencimientos_sat(cfg, periodo))

    orden = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
    alertas.sort(key=lambda alerta: (orden.get(alerta.severidad, 9), alerta.rfc))
    logger.info("Total alertas generadas: %s", len(alertas))
    return alertas
