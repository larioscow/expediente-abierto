"""Alarma de frescura de fuentes: MANIFEST.tsv -> edad por fuente vs umbral."""
from datetime import datetime, timezone

from scripts.check_freshness import evaluate, parse_manifest, thresholds

MANIFEST = """retrieved_at\tsha256\tbytes\tfile\turl
2026-06-10T23:32:51-06:00\taaa\t100\tsat_69b_completo.csv\thttps://x/69b.csv
2026-06-11T07:30:45-06:00\te3b0\t0\tsfp_sancionados.csv\thttps://x/muerto.csv
2026-04-01T09:04:21-06:00\tbbb\t200\tcontratos_2025.csv\thttps://x/2025.csv
2026-06-11T09:04:21-06:00\tccc\t300\tcontratos_2025.csv\thttps://x/2025.csv
2026-05-01T15:05:08+00:00\tddd\t400\tsfp_sancionados.json\thttps://x/sfp (API capture)
"""

NOW = datetime(2026, 6, 12, 0, 0, tzinfo=timezone.utc)


def test_parse_manifest_keeps_last_nonempty_row_per_file():
    latest = parse_manifest(MANIFEST)
    # dos filas de contratos_2025: gana la más reciente
    assert latest["contratos_2025.csv"].sha == "ccc"
    # las descargas de 0 bytes (endpoint muerto) no cuentan como retrieval
    assert "sfp_sancionados.csv" not in latest


def test_evaluate_flags_stale_and_fresh():
    rows = evaluate(parse_manifest(MANIFEST), NOW)
    por_archivo = {r["archivo"]: r for r in rows}
    # 69-B bajado ayer, umbral 35 días -> vigente
    assert por_archivo["sat_69b_completo.csv"]["vigente"] is True
    # SFP bajado hace 41 días, umbral 7 -> atrasado
    assert por_archivo["sfp_sancionados.json"]["vigente"] is False
    assert por_archivo["sfp_sancionados.json"]["edad_dias"] == 41


def test_evaluate_reports_missing_expected_sources():
    """El CSV anual del año en curso aún no existe en el portal: debe
    aparecer como ausente (no vigente), nunca desaparecer en silencio."""
    rows = evaluate(parse_manifest(MANIFEST), NOW)
    por_archivo = {r["archivo"]: r for r in rows}
    assert "contratos_2026.csv" in por_archivo
    assert por_archivo["contratos_2026.csv"]["vigente"] is False
    assert por_archivo["contratos_2026.csv"]["descargado"] is None


def test_thresholds_track_current_year():
    t = thresholds(NOW)
    assert "contratos_2026.csv" in t
    # los años cerrados no tienen umbral: el archivo anual se congela
    assert "contratos_2024.csv" not in t


def test_files_without_threshold_are_always_vigente():
    rows = evaluate(parse_manifest(MANIFEST), NOW)
    por_archivo = {r["archivo"]: r for r in rows}
    # contratos_2025 (año cerrado) no tiene umbral -> vigente aunque viejo
    assert por_archivo["contratos_2025.csv"]["vigente"] is True
    assert por_archivo["contratos_2025.csv"]["limite_dias"] is None
