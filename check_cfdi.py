import sqlite3, pandas as pd

con = sqlite3.connect("data/db/conta_sat.sqlite")
q = """
SELECT
  strftime('%Y-%m', date(fecha)) AS ym,
  emisor_rfc, receptor_rfc,
  CASE WHEN upper(emisor_rfc)=upper(?) THEN 'EMITIDAS'
       WHEN upper(receptor_rfc)=upper(?) THEN 'RECIBIDAS'
       ELSE 'OTRAS' END AS rol,
  COUNT(*) AS n
FROM cfdi
GROUP BY ym, emisor_rfc, receptor_rfc, rol
ORDER BY ym DESC, rol DESC, n DESC;
"""

rfc = input("RFC a revisar (ej. IIS891106AE6): ").strip().upper()
df = pd.read_sql_query(q, con, params=[rfc, rfc])
con.close()

print(df.to_string(index=False))