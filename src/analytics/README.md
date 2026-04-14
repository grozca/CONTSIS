# Analytics

Que hace cada modulo:

- `schema.py`: crea tablas SQLite de la capa analitica.
- `loader.py`: descubre archivos por RFC y periodo.
- `transforms.py`: normaliza filas para `cfdi` y `pagos`.
- `kpis.py`: calcula KPIs mensuales base.
- `build_monthly.py`: carga un periodo completo a la base analitica.
- `queries.py`: consulta KPIs, top contrapartes y variaciones.
- `insights.py`: arma un resumen ejecutivo listo para alertas.
- `alert_payloads.py`: convierte insights en asunto, texto y HTML para correo.
- `dashboard_queries.py`: prepara datasets para visualizacion.
- `bi_exports.py`: exporta tablas planas para Power BI u otras herramientas BI.

Comandos utiles:

```powershell
python src/analytics/build_monthly.py --yyyy_mm 2026-03
python src/analytics/queries.py --query kpis --yyyy_mm 2026-03
python src/analytics/queries.py --query top --yyyy_mm 2026-03 --rfc PNO9901289A7 --rol RECIBIDA
python src/analytics/queries.py --query variation --yyyy_mm 2026-03 --previous-yyyy_mm 2026-02
python src/analytics/insights.py --yyyy_mm 2026-03 --rfc PNO9901289A7
python src/analytics/alert_payloads.py --yyyy_mm 2026-03 --rfc PNO9901289A7 --format text
python src/analytics/alert_payloads.py --yyyy_mm 2026-03 --rfc PNO9901289A7 --format html
python src/analytics/dashboard_queries.py --query dataset --yyyy_mm 2026-03 --rfc PNO9901289A7
python src/analytics/bi_exports.py --yyyy_mm 2026-03
streamlit run app.py
```

Flujo recomendado:

1. Ejecuta `build_monthly.py` para cargar el periodo.
2. Valida KPIs y contrapartes con `queries.py`.
3. Usa `insights.py` para generar el resumen ejecutivo que despues alimentara alertas.
4. Usa `alert_payloads.py` para previsualizar el correo en texto o HTML.
5. Usa `dashboard_queries.py` y `app.py` para explorar visualmente la informacion.
6. Usa `bi_exports.py` para generar CSVs limpios y conectarlos a Power BI.

Datasets BI generados:

- `dim_empresas.csv`
- `dim_periodos.csv`
- `fact_kpis_mensuales_empresa.csv`
- `fact_variaciones_mensuales.csv`
- `fact_contrapartes_mensuales.csv`
- `fact_riesgo_mensual.csv`

Salida por defecto:

- `data/bi_exports/<periodo>/` si usas `--yyyy_mm`
- `data/bi_exports/all_periods/` si exportas todo
