"""Borradores de denuncia formal a partir de los hallazgos.

Tres formatos, cada uno dirigido a la autoridad competente:

  inhabilitados — un borrador POR CASO para el SIDEC y el OIC de la
                  institución contratante (LGRA art. 59, contratación
                  indebida; LAASSP art. 50 fr. IV).
  convenios     — un expediente CONSOLIDADO para la Auditoría Superior de
                  la Federación (LAASSP art. 52 / LOPSRM art. 59).
  colusión      — un expediente para la Comisión Nacional Antimonopolio
                  (LFCE art. 53, prácticas monopólicas absolutas).

Cada borrador es una SOLICITUD DE INVESTIGACIÓN sobre hechos publicados en
fuentes oficiales — nunca una afirmación de culpabilidad. Un humano debe
verificar el caso (checklist del paquete de verificación) y revisar el texto
antes de presentarlo.

Uso:
    python -m casework.denuncias        # escribe findings/denuncias/
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from shared.manifiesto import read_manifest, safe_filename

from realtime.comprasmx_client import DETAIL_SPA as PORTAL_VIVO

# Los CSV históricos traen ligas al dominio anterior del portal
# (funcionpublica.gob.mx, hoy muerto); se reconstruyen sobre el vigente
# usando la única plantilla canónica (realtime.comprasmx_client.DETAIL_SPA).
_UUID_ANUNCIO = re.compile(r"detalle/([0-9a-f]{32})")


def extract_uuid(direccion_anuncio) -> str | None:
    """UUID del procedimiento a partir de cualquier liga de anuncio."""
    m = _UUID_ANUNCIO.search(str(direccion_anuncio or ""))
    return m.group(1) if m else None


def portal_url(direccion_anuncio) -> str:
    """Liga al procedimiento sobre el portal vigente. Sin UUID reconocible
    devuelve "" — nunca una liga cruda al dominio muerto."""
    u = extract_uuid(direccion_anuncio)
    return PORTAL_VIVO.format(uuid=u) if u else ""


def nombres_f05(rows) -> list[str]:
    """Nombre de archivo por caso de f05, con sufijo -N cuando el mismo RFC
    firma más de un contrato la misma fecha. Único punto de verdad para el
    generador y el dashboard."""
    usados: dict[str, int] = {}
    out = []
    for r in rows:
        name = safe_filename(f"inhabilitado_{r['rfc']}_{r['fecha_contrato']}")
        usados[name] = usados.get(name, 0) + 1
        out.append(name + (f"-{usados[name]}" if usados[name] > 1 else ""))
    return out

ROOT = Path(__file__).resolve().parent.parent
FINDINGS = ROOT / "findings"
OUT = FINDINGS / "denuncias"

AVISO = ("> Borrador pendiente de verificación humana. Describe hechos de fuentes "
         "oficiales y solicita su investigación; **no constituye una acusación**.")

AVISO_VERIFICADO = ("> Hechos verificados el {fecha} contra las fuentes oficiales "
                    "citadas. Este documento solicita su investigación; "
                    "**no constituye una acusación**.")


_CONTRATOS_RE = re.compile(r"^contratos_(\d{4})\.csv$")


def _contratos_files(manifest: dict) -> list[str]:
    """CSV de contratos anuales realmente descargados (del manifiesto), en
    orden. Derivado, no fijo: la descarga baja contratos_<año>.csv hasta el
    año en curso, así que un hecho de 2026 debe citar contratos_2026.csv —
    la cadena de evidencia jamás debe omitir el archivo fuente del hecho."""
    return sorted(f for f in manifest if _CONTRATOS_RE.match(f))


def _rango_contratos(manifest: dict) -> str:
    """'2023–2026' a partir de los años de contratos en el manifiesto."""
    años = sorted(int(_CONTRATOS_RE.match(f).group(1))
                  for f in _contratos_files(manifest))
    if not años:
        return ""
    return str(años[0]) if años[0] == años[-1] else f"{años[0]}–{años[-1]}"


def _evidencia(manifest: dict, files: list[str]) -> str:
    lines = ["## Evidencia documental (fuentes oficiales descargadas)", ""]
    for f in files:
        m = manifest.get(f)
        if m:
            lines.append(f"- `{f}` — descargado {m['retrieved_at']}, "
                         f"sha256 `{m['sha256']}`")
    return "\n".join(lines)


def _importe(c: dict) -> float:
    """Importe numérico seguro: NaN/None -> 0.0 (nunca '$nan' en un documento)."""
    imp = c.get("importe")
    return float(imp) if imp is not None and not pd.isna(imp) else 0.0


def _monto(c: dict) -> str:
    """Cantidad exacta cuando existe; el redondeo a millones es el respaldo."""
    imp = c.get("importe")
    if imp is not None and not pd.isna(imp):
        return f"${float(imp):,.2f} MXN"
    return f"${c.get('monto_mxn_millones', '?')}M MXN"


def denuncia_inhabilitado(caso: dict, manifest: dict,
                          verificado: str | None = None) -> str:
    """Denuncia de un solo contrato = grupo de uno; una sola plantilla.
    verificado: fecha (YYYY-MM-DD) en que un humano cotejó el caso."""
    c = caso
    grupo = {"proveedor": c["proveedor"], "rfc": c["rfc"],
             "institucion": c["institucion"],
             "inhabilitado_desde": c["inhabilitado_desde"],
             "hasta": c.get("hasta"), "contratos": [c]}
    return denuncia_inhabilitado_multi(grupo, manifest, verificado=verificado)


def denuncia_inhabilitado_multi(grupo: dict, manifest: dict,
                                verificado: str | None = None) -> str:
    """Una denuncia para todos los contratos de un proveedor ante UNA
    institución, firmados durante la misma inhabilitación."""
    g = grupo
    titulo = "Denuncia" if verificado else "Borrador de denuncia"
    aviso = AVISO_VERIFICADO.format(fecha=verificado) if verificado else AVISO
    cs = sorted(g["contratos"], key=lambda c: -_importe(c))
    total = sum(_importe(c) for c in cs)
    fin = g.get("hasta")
    if fin is None or (isinstance(fin, float) and pd.isna(fin)) or not str(fin).strip():
        fin = "sin fecha de término registrada"
    items = "\n".join(
        f"{i}. Contrato con fecha efectiva **{c['fecha_contrato']}**, monto "
        f"**{_monto(c)}**, procedimiento "
        f"*{c.get('tipo_procedimiento', 'no especificado')}*. "
        f"Anuncio: <{portal_url(c.get('direccion_anuncio'))}>"
        for i, c in enumerate(cs, 1))
    plural = "los contratos" if len(cs) > 1 else "el contrato"
    return f"""# {titulo} — contratación con proveedor inhabilitado

{aviso}

## Hechos

1. El Directorio de Proveedores y Contratistas Sancionados de la SFP registra a
   **{g['proveedor']}** (RFC **{g['rfc']}**) con inhabilitación del
   **{g['inhabilitado_desde']}** al **{fin}**.
2. No obstante dicha inhabilitación, los datos abiertos de ComprasMX registran
   que **{g['institucion']}** celebró con dicho proveedor
   {plural} siguientes, con fecha dentro del periodo de inhabilitación, por un
   monto conjunto de **${total:,.2f} MXN**:

{items}

## Posibles infracciones a investigar

- **Ley General de Responsabilidades Administrativas, artículo 59**
  (contratación indebida): autorizar contratación con quien se encuentre
  inhabilitado — falta administrativa grave del servidor público.
- **Ley General de Responsabilidades Administrativas, artículo 67**
  (participación ilícita): participación del particular estando inhabilitado.
- **LAASSP, artículo 50, fracción IV** (y su correlativo de la LOPSRM):
  prohibición de adjudicar contratos a inhabilitados.

## Petición

Se solicita investigar las contrataciones descritas, deslindar las
responsabilidades administrativas que en su caso procedan, e informar el
número de expediente asignado para seguimiento.

{_evidencia(manifest, ["sfp_sancionados.json", *_contratos_files(manifest)])}
"""


def build_inhabilitado(findings_dir: Path = FINDINGS,
                       solo_acotadas: bool = True,
                       excluir_uuids: set[str] | None = None) -> list[dict]:
    """Agrupa f05 por (rfc, institución) -> un grupo por denuncia."""
    f05 = Path(findings_dir) / "f05_durante_inhabilitacion.csv"
    if not f05.exists():
        return []
    df = pd.read_csv(f05)
    excluir = excluir_uuids or set()
    grupos: dict[tuple, dict] = {}
    for _, r in df.iterrows():
        if solo_acotadas and pd.isna(r.get("hasta")):
            continue
        uuid_m = _UUID_ANUNCIO.search(str(r.get("direccion_anuncio") or ""))
        if uuid_m and uuid_m.group(1) in excluir:
            continue
        key = (r["rfc"], r["institucion"])
        g = grupos.setdefault(key, {
            "proveedor": r["proveedor"], "rfc": r["rfc"],
            "institucion": r["institucion"],
            "inhabilitado_desde": r["inhabilitado_desde"],
            "hasta": None if pd.isna(r.get("hasta")) else r["hasta"],
            "contratos": [],
        })
        g["contratos"].append({
            "fecha_contrato": r["fecha_contrato"],
            "importe": float(r["importe"]) if pd.notna(r.get("importe")) else 0.0,
            "tipo_procedimiento": r.get("tipo_procedimiento"),
            "direccion_anuncio": r.get("direccion_anuncio"),
        })
    return sorted(grupos.values(),
                  key=lambda g: -sum(c["importe"] for c in g["contratos"]))


def denuncia_asf_convenios(df: pd.DataFrame, manifest: dict) -> str:
    n = len(df)
    top = df.sort_values("monto_ultimo_convenio", ascending=False).head(10)
    filas = "\n".join(
        f"| {r.proveedor} | {r.institucion} | {r.pct_incremento}% | "
        f"{r.tope_legal_pct}% | ${r.monto_original:,.0f} | "
        f"${r.monto_ultimo_convenio:,.0f} |"
        for r in top.itertuples())
    return f"""# Borrador de denuncia — convenios modificatorios sobre el tope legal

{AVISO}

## Hechos

Los datos abiertos de ComprasMX registran **{n} caso{"s" if n != 1 else ""}**
({_rango_contratos(manifest)}) en que el monto final de un contrato, tras
convenios modificatorios, supera el tope que la ley fija sobre el monto original:
**artículo 52 de la LAASSP** (+20 %) o artículo 59 de la LOPSRM (+25 % en
obra). Los 10 de mayor monto final:

| proveedor | institución | incremento | tope | original (MXN) | final (MXN) |
|---|---|---|---|---|---|
{filas}

El listado completo, con fechas y códigos de contrato, acompaña como anexo:
`f07_convenios_inflados.csv`.

## Petición

Se solicita a la **Auditoría Superior de la Federación** auditar los convenios
modificatorios descritos, determinar si los incrementos cuentan con el soporte
de excepción que la ley exige y, en su caso, fincar las responsabilidades
resarcitorias que procedan.

{_evidencia(manifest, _contratos_files(manifest))}
"""


def denuncia_cna_rotacion(df: pd.DataFrame, manifest: dict) -> str:
    bloques = "\n".join(
        f"- **{r.institucion} — {r.nombre_uc}**: {r.contratos} licitaciones "
        f"públicas repartidas entre {r.n_proveedores} proveedores con índice "
        f"de equidad {r.evenness} (1.0 = reparto perfecto), "
        f"${r.monto_mxn_millones}M MXN. Proveedores: {r.proveedores}"
        for r in df.itertuples())
    return f"""# Borrador de denuncia — posible coordinación de posturas en licitaciones

{AVISO}

## Hechos

El análisis de los datos abiertos de ComprasMX identifica unidades
compradoras donde un grupo cerrado de proveedores se reparte la totalidad de
las licitaciones públicas en proporciones casi iguales — patrón consistente
con la coordinación de posturas:

{bloques}

## Posible infracción a investigar

**Ley Federal de Competencia Económica, artículo 53** (prácticas monopólicas
absolutas): contratos, convenios o arreglos entre competidores para
establecer, concertar o coordinar posturas en licitaciones públicas.

## Petición

Se solicita a la **Comisión Nacional Antimonopolio** el inicio de una
investigación por posibles prácticas monopólicas absolutas en los
procedimientos descritos. Los datos de cada procedimiento constan en los
datos abiertos de ComprasMX (anexo: `f06_rotacion_licitaciones.csv`).

{_evidencia(manifest, _contratos_files(manifest))}
"""


def _url_contrato(c: dict) -> str:
    """Liga del contrato: en federal se reconstruye sobre el portal vigente;
    en estatal el hallazgo ya trae la liga directa del portal del estado.
    NaN/'nan'/'' se tratan como sin liga (nunca '<nan>' en un documento)."""
    def _vacio(v) -> bool:
        return (v is None or (isinstance(v, float) and pd.isna(v))
                or str(v).strip().lower() in ("", "nan", "none"))
    u = c.get("url")
    if _vacio(u):
        u = portal_url(c.get("direccion_anuncio"))
    return "" if _vacio(u) else str(u).strip()


def _items_contratos(cs: list[dict]) -> str:
    return "\n".join(
        f"{i}. Contrato con fecha efectiva **{c.get('fecha') or c.get('fecha_contrato')}**, "
        f"monto **{_monto(c)}**, procedimiento "
        f"*{c.get('tipo_procedimiento', 'no especificado')}*."
        + (f" Fuente: <{_url_contrato(c)}>" if _url_contrato(c) else "")
        for i, c in enumerate(sorted(cs, key=lambda c: -_importe(c)), 1))


def denuncia_inhabilitado_estatal(grupo: dict, manifest: dict,
                                  verificado: str | None = None) -> str:
    """Denuncia ante el OIC/Contraloría del estado: contrato estatal o municipal
    firmado con un proveedor inhabilitado por la SFP. La LGRA obliga también a
    los servidores de los estados (arts. 1 y 10)."""
    g = grupo
    titulo = "Denuncia" if verificado else "Borrador de denuncia"
    aviso = AVISO_VERIFICADO.format(fecha=verificado) if verificado else AVISO
    cs = sorted(g["contratos"], key=lambda c: -_importe(c))
    total = sum(_importe(c) for c in cs)
    fin = g.get("hasta")
    if fin is None or (isinstance(fin, float) and pd.isna(fin)) or not str(fin).strip():
        fin = "sin fecha de término registrada"
    estado = g.get("estado") or "la entidad federativa"
    sujeto = g.get("institucion")
    plural = "los siguientes contratos" if len(cs) > 1 else "el siguiente contrato"
    nota_rfc = ("" if g.get("rfc_valido", True) else
                "\n> El RFC proviene de la captura estatal y debe cotejarse "
                "contra el directorio de la SFP antes de presentar.\n")
    return f"""# {titulo} — contratación estatal con proveedor inhabilitado

{aviso}
{nota_rfc}
## Hechos

1. El Directorio de Proveedores y Contratistas Sancionados de la SFP registra a
   **{g['proveedor']}** (RFC **{g['rfc']}**) con inhabilitación del
   **{g.get('inhabilitado_desde')}** al **{fin}**.
2. No obstante dicha inhabilitación, los datos abiertos de la
   **Plataforma Nacional de Transparencia** (obligación de transparencia,
   art. 70 fr. XXVIII) registran que **{sujeto}** ({estado}) celebró con dicho
   proveedor {plural}, con fecha dentro del periodo de inhabilitación, por un
   monto conjunto de **${total:,.2f} MXN**:

{_items_contratos(cs)}

## Posibles infracciones a investigar

- **Ley General de Responsabilidades Administrativas, artículo 59**
  (contratación indebida), aplicable a los servidores públicos de las entidades
  federativas conforme a sus artículos 1 y 10: autorizar contratación con quien
  se encuentra inhabilitado.
- **Ley General de Responsabilidades Administrativas, artículo 67**
  (participación ilícita) del particular inhabilitado.
- La **ley estatal de adquisiciones** correspondiente, que reproduce la
  prohibición de adjudicar contratos a inhabilitados.

## Petición

Se solicita al **Órgano Interno de Control / Contraloría del Estado de {estado}**
investigar las contrataciones descritas, deslindar las responsabilidades
administrativas que en su caso procedan, e informar el número de expediente
asignado para seguimiento.

{_evidencia(manifest, ["sfp_sancionados.json"])}
"""


def denuncia_efos_post_definitivo(grupo: dict, manifest: dict,
                                  verificado: str | None = None) -> str:
    """Denuncia ante el SAT y la FGR: contrato firmado DESPUÉS de que el SAT
    publicó al proveedor como EFOS definitivo (operaciones inexistentes)."""
    g = grupo
    titulo = "Denuncia" if verificado else "Borrador de denuncia"
    aviso = AVISO_VERIFICADO.format(fecha=verificado) if verificado else AVISO
    cs = sorted(g["contratos"], key=lambda c: -_importe(c))
    total = sum(_importe(c) for c in cs)
    plural = "los siguientes contratos" if len(cs) > 1 else "el siguiente contrato"
    estatal = g.get("estado")
    quien = (f"**{g.get('institucion')}** ({estatal})" if estatal
             else f"**{g.get('institucion')}**")
    copia = ("\n- Con copia al **Órgano Interno de Control / Contraloría del "
             f"Estado de {estatal}**." if estatal else "")
    return f"""# {titulo} — contratación con empresa facturera (EFOS definitiva)

{aviso}

## Hechos

1. El Servicio de Administración Tributaria publicó a **{g['proveedor']}**
   (RFC **{g['rfc']}**) en el listado **definitivo** del artículo 69-B del
   Código Fiscal de la Federación —empresas que facturan operaciones
   inexistentes—, con publicación en el DOF el **{g.get('definitivo_dof')}**.
2. Con fecha **posterior** a esa publicación, los datos abiertos registran que
   {quien} celebró con dicho proveedor {plural}, por un monto conjunto de
   **${total:,.2f} MXN**:

{_items_contratos(cs)}

## Posibles infracciones a investigar

- **Código Fiscal de la Federación, artículo 69-B**: el proveedor ampara
  operaciones inexistentes; los comprobantes que expidió no producen efecto
  fiscal alguno.
- **Código Penal Federal, artículo 113-bis**: expedir o dar efectos fiscales a
  comprobantes que amparan operaciones inexistentes.
- La responsabilidad administrativa del servidor público que autorizó la
  contratación pese a la publicación definitiva del SAT.{copia}

## Petición

Se solicita al **Servicio de Administración Tributaria** y a la
**Fiscalía General de la República** investigar las operaciones descritas y,
en su caso, ejercer las facultades de comprobación y la acción penal que
correspondan, e informar el número de expediente asignado.

{_evidencia(manifest, ["sat_69b_completo.csv", *_contratos_files(manifest)])}
"""


def build_all(findings_dir: Path = FINDINGS, out_dir: Path = OUT,
              manifest: dict | None = None,
              verificados: dict[str, str] | None = None) -> list[Path]:
    """verificados: RFC -> fecha de verificación humana; esos casos salen como
    denuncia presentable en lugar de borrador."""
    manifest = read_manifest() if manifest is None else manifest
    verificados = verificados or {}
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    f05 = findings_dir / "f05_durante_inhabilitacion.csv"
    if f05.exists():
        df = pd.read_csv(f05)
        nombres = nombres_f05(r for _, r in df.iterrows())
        for (_, caso), name in zip(df.iterrows(), nombres):
            p = out_dir / f"{name}.md"
            p.write_text(
                denuncia_inhabilitado(caso.to_dict(), manifest,
                                      verificado=verificados.get(caso["rfc"])),
                encoding="utf-8")
            paths.append(p)

    f07 = findings_dir / "f07_convenios_inflados.csv"
    if f07.exists():
        df = pd.read_csv(f07)
        if len(df):
            p = out_dir / "asf_convenios_sobre_tope.md"
            p.write_text(denuncia_asf_convenios(df, manifest), encoding="utf-8")
            paths.append(p)

    f06 = findings_dir / "f06_rotacion_licitaciones.csv"
    if f06.exists():
        df = pd.read_csv(f06)
        if len(df):
            p = out_dir / "cna_rotacion_licitaciones.md"
            p.write_text(denuncia_cna_rotacion(df, manifest), encoding="utf-8")
            paths.append(p)

    return paths


if __name__ == "__main__":
    import argparse
    from datetime import date

    ap = argparse.ArgumentParser()
    ap.add_argument("--verificado", action="append", default=[],
                    metavar="RFC[=FECHA]",
                    help="marca los casos de ese RFC como verificados "
                         "(fecha por omisión: hoy)")
    args = ap.parse_args()
    verificados = {}
    for v in args.verificado:
        rfc, _, fecha = v.partition("=")
        verificados[rfc.strip().upper()] = fecha or date.today().isoformat()

    written = build_all(verificados=verificados)
    print(f"escribí {len(written)} documentos -> {OUT}"
          + (f" ({len(verificados)} RFC verificados)" if verificados else ""))
