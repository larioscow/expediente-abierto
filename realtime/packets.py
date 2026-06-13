"""Verification packets — the action loop.

An alert in a JSONL file nobody reads is a retrospective with extra steps.
This module turns each alert into a self-contained markdown packet with the
evidence a human needs to verify (or kill) the case the same day: what fired
and why, the flagged awards with their list matches, the provenance of every
source file (sha256 + retrieval date), and an explicit verification checklist.

Run standalone to (re)generate packets for findings/alerts.jsonl:
    python -m realtime.packets
"""
from __future__ import annotations

import json
from pathlib import Path

from shared.manifiesto import read_manifest, safe_filename  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
ALERTS = ROOT / "findings" / "alerts.jsonl"
PACKETS = ROOT / "findings" / "packets"
MANIFEST = ROOT / "data" / "raw" / "MANIFEST.tsv"

SOURCE_FILES = {
    "69-B": "sat_69b_completo.csv",
    "SFP": "sfp_sancionados.json",
}

CHECKLIST = """\
## Lista de verificación (obligatoria antes de citar)

- [ ] Abrir el procedimiento en el portal (liga arriba) y confirmar que sigue
      publicado con los mismos datos.
- [ ] Confirmar la identidad del proveedor por RFC en el acta de fallo /
      anexos del procedimiento (el cruce en vivo es por NOMBRE — homónimos
      posibles).
- [ ] Verificar el registro en la fuente oficial: 69-B en el listado del SAT
      (DOF) / sanción en directoriosancionados.buengobierno.gob.mx.
- [ ] Buscar aclaraciones posteriores (Desvirtuado / Sentencia Favorable /
      fin de inhabilitación) más recientes que la descarga de datos.
- [ ] Pedir versión pública del expediente a la unidad compradora si el caso
      avanza.
"""


def _award_block(aw: dict) -> str:
    lines = [f"### {aw.get('licitante', '?')}",
             "",
             f"- lista: **{aw.get('lista', '?')}** — registro coincidente: "
             f"{aw.get('match', '?')} (RFC {aw.get('rfc', '?')})"]
    if aw.get("situacion"):
        lines.append(f"- situación 69-B: **{aw['situacion']}**")
    if aw.get("durante_inhabilitacion") is not None:
        lines.append(f"- inhabilitación: {aw.get('inhabilitado_desde')} → "
                     f"{aw.get('inhabilitado_hasta')} — contrato DURANTE "
                     f"inhabilitación: **{aw['durante_inhabilitacion']}**")
    if aw.get("importe_max") is not None:
        lines.append(f"- importe (máx): ${aw['importe_max']:,.2f} {aw.get('moneda', '')}")
    lines.append(f"- institución: {aw.get('institucion', '?')} · contrato {aw.get('cod_drc', '?')}")
    lines.append("- ⚠️ coincidencia por **cruce por NOMBRE** — requiere "
                 "confirmación por RFC antes de citar")
    return "\n".join(lines)


def packet_markdown(alert: dict, manifest: dict) -> str:
    a = alert
    head = [
        f"# Paquete de verificación — {a.get('numero', 'sin número')}",
        "",
        f"> Generado automáticamente el {a.get('ts', '?')}. Este documento es un "
        "**filtro estadístico**, no es una acusación; toda señal requiere la "
        "verificación humana de la lista al final.",
        "",
        f"- procedimiento: **{a.get('nombre', '?')}**",
        f"- dependencia: {a.get('dependencia', '?')} · entidad: {a.get('entidad', '?')}",
        f"- tipo: {a.get('tipo', '?')} · estatus: {a.get('estatus', '?')} "
        f"({a.get('change', '?')})",
        f"- score: {a.get('score', '?')}",
        f"- portal: <{a.get('url', '')}>",
        "",
        "## Por qué surgió",
        "",
    ]
    head += [f"- {r}" for r in a.get("reasons", [])]

    awards = a.get("awards_flagged") or []
    if awards:
        head += ["", "## Adjudicaciones señaladas", ""]
        head += [_award_block(aw) + "\n" for aw in awards]

    head += ["", "## Cadena de evidencia (fuentes oficiales descargadas)", ""]
    listed = {aw.get("lista") for aw in awards} or set(SOURCE_FILES)
    for lista, fname in SOURCE_FILES.items():
        if lista in listed and fname in manifest:
            m = manifest[fname]
            head.append(f"- `{fname}` — descargado {m['retrieved_at']}, "
                        f"sha256 `{m['sha256']}`")
    head += ["", CHECKLIST]
    return "\n".join(head)


def write_packets(alerts: list[dict], manifest: dict | None = None,
                  out_dir: Path = PACKETS) -> list[Path]:
    manifest = read_manifest() if manifest is None else manifest
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for a in alerts:
        p = out_dir / f"{safe_filename(a.get('numero') or a.get('uuid'))}.md"
        p.write_text(packet_markdown(a, manifest), encoding="utf-8")
        paths.append(p)
    return paths


def load_alerts(path: Path = ALERTS, limit: int | None = None) -> list[dict]:
    """Alertas de alerts.jsonl deduplicadas por uuid (mayor score gana),
    ordenadas por score desc. Único parser de alerts.jsonl del proyecto."""
    if not Path(path).exists():
        return []
    rows = [json.loads(ln) for ln in Path(path).read_text().splitlines() if ln.strip()]
    best: dict[str, dict] = {}
    for a in rows:
        u = a.get("uuid")
        if u not in best or a["score"] > best[u]["score"]:
            best[u] = a
    out = sorted(best.values(), key=lambda x: -x["score"])
    return out[:limit] if limit else out


def main():
    alerts = load_alerts()
    if not alerts:
        print("no alerts file; nothing to do")
        return
    paths = write_packets(alerts)
    print(f"wrote {len(paths)} packets -> {PACKETS}")


if __name__ == "__main__":
    main()
