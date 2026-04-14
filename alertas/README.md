# Alertas

Motor de alertas para CFDI con dos modos de salida:

- `director`: resumen ejecutivo consolidado.
- `cliente`: reporte mensual por RFC.

## Etapa 1

Esta etapa deja una base mas profesional sin cambiar el flujo principal:

- `app/cli.py`: punto de entrada del motor.
- `app/use_cases.py`: orquestacion de los modos.
- `app/rules.py`: reglas de negocio.
- `app/data_access.py`: lectura de Excel y descubrimiento de periodos.
- `app/storage.py`: historial SQLite.
- `app/rendering.py`: HTML y hash de duplicados.
- `app/emailing.py`: envio de correo.
- `app/console_view.py`: resumen en consola.

## Ejecucion

```powershell
.\.venv\Scripts\python.exe alertas/alertas_v2.py --yyyy_mm 2026-03 --piloto
.\.venv\Scripts\python.exe alertas/alertas_v2.py --yyyy_mm 2026-03 --modo cliente --rfc PNO9901289A7 --piloto
```

## Etapa 2

Quedo implementado:

- validacion formal de `config.yaml`
- scheduler funcional con modo `--once` y loop continuo
- pruebas automatizadas en `tests/`

## Scheduler

```powershell
.\.venv\Scripts\python.exe alertas/scheduler.py --once
.\.venv\Scripts\python.exe alertas/scheduler.py --once --force --periodo 2026-03
.\.venv\Scripts\python.exe alertas/scheduler.py
```

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest alertas/tests -q
```

## Dependencias

Antes de ejecutar el motor o las pruebas, instala:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r alertas/requirements.txt
```
