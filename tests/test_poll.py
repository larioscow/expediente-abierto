"""Realtime poll resilience: one failed fetch must not lose the run, and the
seen-store must not grow forever."""
from datetime import datetime, timedelta, timezone

from realtime.comprasmx_client import Procedure
from realtime.efos_index import EfosIndex
from realtime.poll import poll_once, prune_seen
from realtime.sfp_index import SfpIndex
from tests.fixtures import write_efos_csv


def proc(uuid, estatus="VIGENTE", tipo="ADJUDICACIÓN DIRECTA"):
    return Procedure(uuid=uuid, numero=f"N-{uuid}", nombre="x", siglas="IMSS",
                     estatus=estatus, tipo_procedimiento=tipo, tipo_contratacion="",
                     caracter="", entidad="", unidad_compradora="",
                     fecha_apertura=None, cod_expediente="")


class FakeClient:
    def __init__(self, procedures, fail_uuids=()):
        self.procedures = procedures
        self.fail_uuids = set(fail_uuids)
        self.detail_calls = []

    def fetch_recent(self, pages: int = 1):
        return self.procedures

    def fetch_detail(self, uuid):
        self.detail_calls.append(uuid)
        if uuid in self.fail_uuids:
            raise RuntimeError("portal timeout")
        return {}, []


def empty_indexes(tmp_path):
    efos = EfosIndex(write_efos_csv(tmp_path / "efos.csv", []))
    sfp = SfpIndex(tmp_path / "missing.json")
    return efos, sfp


NOW = datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc).isoformat()


def test_one_failed_detail_fetch_does_not_lose_the_others(tmp_path):
    efos, sfp = empty_indexes(tmp_path)
    client = FakeClient([proc("a"), proc("b"), proc("c")], fail_uuids=["b"])
    seen = {}
    alerts, stats = poll_once(client, efos, sfp, seen, NOW, threshold=2)
    # all three procedures were processed and recorded despite b failing
    assert set(seen) == {"a", "b", "c"}
    assert stats["errors"] == 1 and stats["new"] == 3
    # direct awards score 2 -> all three still alert on list-level data
    assert {a["uuid"] for a in alerts} == {"a", "b", "c"}


def test_unchanged_procedures_are_skipped(tmp_path):
    efos, sfp = empty_indexes(tmp_path)
    seen = {"a": {"estatus": "VIGENTE", "first_seen": NOW, "last_seen": NOW}}
    client = FakeClient([proc("a")])
    alerts, stats = poll_once(client, efos, sfp, seen, NOW, threshold=2)
    assert stats["new"] == 0 and stats["changed"] == 0
    assert client.detail_calls == [] and alerts == []


def test_status_change_reassesses(tmp_path):
    efos, sfp = empty_indexes(tmp_path)
    seen = {"a": {"estatus": "VIGENTE", "first_seen": "2026-01-01T00:00:00+00:00",
                  "last_seen": "2026-01-01T00:00:00+00:00"}}
    client = FakeClient([proc("a", estatus="ADJUDICADO")])
    alerts, stats = poll_once(client, efos, sfp, seen, NOW, threshold=2)
    assert stats["changed"] == 1
    assert seen["a"]["estatus"] == "ADJUDICADO"
    assert seen["a"]["first_seen"] == "2026-01-01T00:00:00+00:00"  # preserved
    assert alerts and alerts[0]["change"] == "status_change"


def test_prune_seen_drops_stale_entries():
    old = (datetime.fromisoformat(NOW) - timedelta(days=120)).isoformat()
    recent = (datetime.fromisoformat(NOW) - timedelta(days=5)).isoformat()
    seen = {"old": {"last_seen": old}, "recent": {"last_seen": recent},
            "no_ts": {}}
    pruned = prune_seen(seen, NOW, max_age_days=90)
    assert set(pruned) == {"recent", "no_ts"}


def test_save_seen_is_atomic(tmp_path, monkeypatch):
    """Un crash a mitad de escritura no debe dejar seen.json corrupto: se
    escribe a archivo temporal y se renombra."""
    import realtime.poll as poll
    monkeypatch.setattr(poll, "STATE", tmp_path / "seen.json")
    poll.save_seen({"a": {"estatus": "X"}})
    assert poll.load_seen() == {"a": {"estatus": "X"}}
    # no quedan temporales y el archivo es JSON válido
    assert list(tmp_path.glob("*.tmp")) == []
