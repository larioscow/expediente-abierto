"""Verification packets: every alert becomes a self-contained, evidence-cited
markdown file a journalist can act on the same day."""
from realtime.packets import packet_markdown, safe_filename, write_packets

ALERT = {
    "ts": "2026-06-11T14:00:00+00:00",
    "uuid": "abc123", "numero": "LA-07-110-007000999-N-504-2026",
    "nombre": "Adquisición de medicamentos", "dependencia": "IMSS",
    "estatus": "VIGENTE", "tipo": "ADJUDICACIÓN DIRECTA", "entidad": "CDMX",
    "score": 8,
    "reasons": ["DIRECTA (+2): adjudicación directa",
                "EFOS_69B (+6): PROVEEDORA FANTASMA en lista 69-B (Definitivo, RFC PFA101010AB1)"],
    "awards_flagged": [{
        "licitante": "PROVEEDORA FANTASMA SA DE CV", "lista": "69-B",
        "match": "PROVEEDORA FANTASMA, S.A. DE C.V.", "rfc": "PFA101010AB1",
        "situacion": "Definitivo", "importe_max": 1500000.0, "moneda": "MXN",
        "institucion": "IMSS", "cod_drc": "X1",
        "match_method": "name", "needs_verification": True,
    }],
    "url": "https://example.org/detalle/abc123/procedimiento",
    "change": "new",
}

MANIFEST = {"sat_69b_completo.csv": {"retrieved_at": "2026-06-10", "sha256": "deadbeef"}}


def test_packet_contains_case_evidence_and_checklist():
    md = packet_markdown(ALERT, MANIFEST)
    for needle in [
        "LA-07-110-007000999-N-504-2026",          # procedure id
        "score: 8",
        "EFOS_69B (+6)",                            # why it fired
        "PROVEEDORA FANTASMA SA DE CV",             # flagged award
        "PFA101010AB1",                             # matched RFC
        "https://example.org/detalle/abc123/procedimiento",
        "sat_69b_completo.csv",                     # evidence chain
        "deadbeef",
        "cruce por NOMBRE",                         # name-match warning
        "- [ ]",                                    # verification checklist
        "no es una acusación",                      # screens-not-verdicts
    ]:
        assert needle in md, needle


def test_safe_filename_strips_path_hazards():
    assert "/" not in safe_filename("LA-07/110\\007 999*2026")
    assert safe_filename("a b") == "a_b"


def test_write_packets_creates_one_file_per_alert(tmp_path):
    paths = write_packets([ALERT], MANIFEST, out_dir=tmp_path)
    assert len(paths) == 1
    assert paths[0].exists() and paths[0].suffix == ".md"
    assert "score: 8" in paths[0].read_text()
