"""Case store: alert history accumulates, and human verification state
survives re-ingestion — work is never regenerated away."""
import pytest

from realtime.store import CaseStore, ESTADOS

ALERT = {"ts": "2026-06-11T14:00:00+00:00", "uuid": "u1", "numero": "LA-1",
         "nombre": "Compra X", "dependencia": "IMSS", "score": 8,
         "estatus": "VIGENTE", "reasons": ["EFOS_69B (+6): x"], "change": "new"}


@pytest.fixture
def store(tmp_path):
    return CaseStore(tmp_path / "cases.duckdb")


def test_ingest_creates_case_in_estado_nuevo(store):
    assert store.ingest_alerts([ALERT]) == 1
    df = store.cases()
    assert len(df) == 1
    row = df.iloc[0]
    assert row["uuid"] == "u1" and row["estado"] == "nuevo" and row["max_score"] == 8


def test_reingest_is_idempotent_and_preserves_state(store):
    store.ingest_alerts([ALERT])
    store.set_state("u1", "verificando", nota="llamé a la UC")
    assert store.ingest_alerts([ALERT]) == 0          # same ts+uuid -> no dup
    row = store.cases().iloc[0]
    assert row["estado"] == "verificando" and row["nota"] == "llamé a la UC"
    assert len(store.history("u1")) == 1


def test_new_alert_for_same_case_updates_score_not_state(store):
    store.ingest_alerts([ALERT])
    store.set_state("u1", "verificado")
    louder = dict(ALERT, ts="2026-06-12T10:00:00+00:00", score=11)
    assert store.ingest_alerts([louder]) == 1
    row = store.cases().iloc[0]
    assert row["max_score"] == 11 and row["estado"] == "verificado"
    assert len(store.history("u1")) == 2


def test_invalid_state_rejected(store):
    store.ingest_alerts([ALERT])
    with pytest.raises(ValueError):
        store.set_state("u1", "inventado")


def test_cases_filters_by_state(store):
    store.ingest_alerts([ALERT, dict(ALERT, uuid="u2", numero="LA-2")])
    store.set_state("u2", "descartado", nota="homónimo")
    assert set(store.cases("nuevo")["uuid"]) == {"u1"}
    assert set(store.cases("descartado")["uuid"]) == {"u2"}
    assert set(ESTADOS) >= {"nuevo", "verificando", "verificado",
                            "denunciado", "publicado", "descartado"}


def test_clearing_nota_with_empty_string(store):
    """Borrar la nota desde el dashboard (campo vacío) debe limpiar; None
    significa 'no tocar'."""
    store.ingest_alerts([ALERT])
    store.set_state("u1", "verificando", nota="folio 123")
    store.set_state("u1", "verificando", nota=None)      # no tocar
    assert store.cases().iloc[0]["nota"] == "folio 123"
    store.set_state("u1", "verificando", nota="")        # limpiar
    nota = store.cases().iloc[0]["nota"]
    assert nota is None or nota != nota or nota == ""    # NULL/NaN/""
