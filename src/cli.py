# src/cli.py
import sys

USO = """
Uso:
  python -m src.cli r0      # Bootstrap (valida archivos base)
  python -m src.cli r1      # Verificación de certificados
  python -m src.cli r3      # Solicitar descarga masiva (SAT)
  python -m src.cli r4      # Verificar estado (todas) con reintentos
  python -m src.cli r4s     # Verificar SOLO la última solicitud con reintentos
  python -m src.cli r4id <IdSolicitud>  # Verificar una solicitud específica
  python -m src.cli r5      # Descargar paquetes listos
  python -m src.cli r6      # Descomprimir paquetes (ZIP) y registrar en BD
  python -m src.cli r7      # Parsear XML a BD (CFDI/Conceptos/Impuestos)
  python -m src.cli r8      # Exportar Excel (CFDI + CFDI_PUE + Resumen)
"""

def main():
    if len(sys.argv) < 2:
        print(USO)
        return

    cmd = sys.argv[1].lower()

    if cmd == "r0":
        from src.robots import r0_bootstrap
        r0_bootstrap.run()

    elif cmd == "r1":
        from src.robots import r1_carga_certs
        r1_carga_certs.run()

    elif cmd == "r3":
        from src.robots import r3_solicitar
        r3_solicitar.run()

    elif cmd == "r4":
        from src.robots import r4_verificar
        r4_verificar.run()

    elif cmd == "r4s":
        from src.robots import r4s_verificar_ultimo
        r4s_verificar_ultimo.run()

    elif cmd == "r4id":
        from src.robots import r4id_verificar
        if len(sys.argv) < 3:
            print("Uso: python -m src.cli r4id <IdSolicitud>")
            return
        r4id_verificar.run(sys.argv[2])

    elif cmd == "r5":
        from src.robots import r5_descargar
        r5_descargar.run()

    elif cmd == "r6":
        from src.robots import r6_descomprimir
        r6_descomprimir.run()
    elif cmd == "r6fix":
        from src.robots import r6_fix_reorganizar
        r6_fix_reorganizar.run()
    elif cmd == "r7org":
        from src.robots import r7_organizar
        r7_organizar.run()
    elif cmd == "r8":
        from src.robots import r8_export_excel
        r8_export_excel.run()
    elif cmd == "r9":
        from src.robots import r9_export_resumen
        r9_export_resumen.run()  
    
    else:
        print(USO)

if __name__ == "__main__":
    main()
