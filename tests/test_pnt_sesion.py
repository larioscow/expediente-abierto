"""SesionPNT.get reintenta ante caídas de red transitorias (corte de
internet) en vez de abandonar a la primera, y re-resuelve Turnstile en 403."""
import types

import pytest

import scripts.pnt_muestra_rfc as P
from scripts.pnt_muestra_rfc import MAX_FALLOS_RED, SesionPNT


class RespFalsa:
    def __init__(self, status, ctype="application/json", text="{}"):
        self.status_code = status
        self.headers = {"content-type": ctype}
        self.text = text


def sesion_sin_init():
    """SesionPNT sin tocar la red (salta __init__)."""
    s = SesionPNT.__new__(SesionPNT)
    s._gastado = 0.0
    return s


@pytest.fixture(autouse=True)
def sin_dormir(monkeypatch):
    monkeypatch.setattr(P.time, "sleep", lambda *_: None)
    monkeypatch.setattr(P.random, "uniform", lambda *_: 0)


def test_reintenta_y_se_recupera(monkeypatch):
    s = sesion_sin_init()
    intentos = {"n": 0}

    def get(url, timeout):
        intentos["n"] += 1
        if intentos["n"] < 3:      # 2 caídas y a la tercera responde
            raise OSError("Could not resolve host")
        return RespFalsa(200, "application/json", '{"ok":1}')

    s._sesion = types.SimpleNamespace(get=get)
    status, ctype, body = s.get("/x")
    assert status == 200 and intentos["n"] == 3


def test_se_rinde_tras_max_fallos(monkeypatch):
    s = sesion_sin_init()
    n = {"n": 0}

    def get(url, timeout):
        n["n"] += 1
        raise OSError("timed out")

    s._sesion = types.SimpleNamespace(get=get)
    with pytest.raises(OSError):
        s.get("/x")
    assert n["n"] == MAX_FALLOS_RED + 1   # intentos hasta rendirse


def test_403_reresuelve_una_vez(monkeypatch):
    s = sesion_sin_init()
    llamadas = {"get": 0, "resolver": 0}

    def get(url, timeout):
        llamadas["get"] += 1
        return RespFalsa(403 if llamadas["get"] == 1 else 200)

    s._sesion = types.SimpleNamespace(get=get)
    monkeypatch.setattr(s, "_resolver",
                        lambda: llamadas.__setitem__("resolver",
                                                     llamadas["resolver"] + 1))
    status, _, _ = s.get("/x")
    assert status == 200 and llamadas["resolver"] == 1
