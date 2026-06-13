#!/usr/bin/env bash
# One-command refresh: download sources -> run detectors -> rebuild web data.
set -euo pipefail
cd "$(dirname "$0")/.."

# una fuente caída no congela el lote: se corre con lo descargado y la
# alarma de frescura reporta el envejecimiento, nunca en silencio
scripts/download_data.sh || echo "WARN: alguna fuente falló; se sigue con datos en disco"
PY=.venv/bin/python
"$PY" scripts/fetch_sfp.py || echo "WARN: SFP refresh failed, using cached"
# circulares de inhabilitación del DOF: alerta temprana para el monitoreo
"$PY" -m realtime.dof_index --dias 14 || echo "WARN: refresh DOF falló; se sigue con el índice en disco"
# PNT estatal: incremental gracias al manifiesto (solo baja lo que creció);
# si la PNT está caída se corre con los CSV en disco
"$PY" -m scripts.pnt_contratos || echo "WARN: refresh PNT falló; se sigue con datos en disco"
# alarma de frescura: nunca correr detectores sobre fuentes viejas en silencio
"$PY" scripts/check_freshness.py || echo "ALERTA: fuentes atrasadas o ausentes (findings/freshness.json)"
for d in d01_efos_contracts d01h_efos_historico d02_direct_award_concentration \
         d03_benford d04_young_winners d05_sfp_sancionados d06_colusion \
         d07_convenios d08_cfe d09_riesgo_proveedor d10_pnt_estatal \
         d11_umbrales d12_benford_estatal backtest; do
  echo "== $d"
  "$PY" -m "detectors.$d"
done
# triaje de hallazgos -> libro de casos (federal + estados); coteja contra lo
# ya presentado y conserva el estado humano. No presenta nada: deja la cola
# lista para revisar en el dashboard / con el skill mx-triage.
"$PY" -m casework.triage scan || echo "WARN: triaje falló; el libro queda como estaba"
"$PY" scripts/export_web_data.py
echo "datos del sitio actualizados: web/src/data/ + web/public/datos/"
echo "para construir el sitio: (cd web && npm run build) -> web/out/"
