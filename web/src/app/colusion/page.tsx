import type { Metadata } from "next";
import { EvidenceTable } from "@/components/EvidenceTable";
import data from "@/data/colusion.json";
import { fmt } from "@/lib/fmt";

const r = data.resumen;

export const metadata: Metadata = {
  title: `Patrones de reparto en ${fmt(r.oficinas_total)} oficinas compradoras`,
  description:
    "Reparto de licitaciones entre grupos cerrados, ganadoras constituidas " +
    "con días de diferencia y varias adjudicaciones al mismo proveedor el " +
    "mismo día en la contratación federal.",
};

export default function Colusion() {
  return (
    <main>
      <header className="banda banda-pagina">
        <h1>Patrones de reparto en {fmt(r.oficinas_total)} oficinas compradoras</h1>
        <p className="intro">
          Tres patrones que la competencia real difícilmente produce. Una
          oficina o una empresa entra a estas tablas únicamente por los
          números de sus adjudicaciones.
        </p>
        <dl className="tablero menor">
          <div>
            <dt>grupos que se turnan</dt>
            <dd>{fmt(r.rotacion_total)}</dd>
          </div>
          <div>
            <dt>anillos de constitución</dt>
            <dd>{fmt(r.anillos_total)}</dd>
          </div>
          <div>
            <dt>casos de mismo día</dt>
            <dd>{fmt(r.fraccionamiento_total)}</dd>
          </div>
        </dl>
      </header>
      <section>
        <h2>Se turnan los contratos de una misma oficina</h2>
        <EvidenceTable
          cols={[
            { key: "institucion", label: "institución" },
            { key: "nombre_uc", label: "oficina compradora" },
            { key: "contratos", label: "contratos", num: true },
            { key: "n_proveedores", label: "empresas", num: true },
            { key: "monto_mxn_millones", label: "millones MXN", num: true, dec: 1 },
            { key: "proveedores", label: "quiénes" },
          ]}
          rows={data.rotacion}
        />
        <p className="nota">
          En mercados con pocos proveedores la alternancia puede darse sola.
          Las actas de fallo dicen si hubo competencia o puro trámite.
        </p>

        <h2>Ganadoras nacidas con días de diferencia</h2>
        <p className="muted">
          los {data.anillos.length} grupos con más dinero, de{" "}
          {fmt(r.anillos_total)}
        </p>
        <EvidenceTable
          cols={[
            { key: "institucion", label: "institución" },
            { key: "nombre_uc", label: "oficina compradora" },
            { key: "empresas", label: "empresas", num: true },
            { key: "dias_entre_constituciones", label: "días entre constituciones", num: true },
            { key: "contratos", label: "contratos", num: true },
            { key: "monto_mxn_millones", label: "millones MXN", num: true, dec: 1 },
          ]}
          rows={data.anillos}
        />
        <p className="nota">
          Grupos corporativos legítimos también constituyen filiales en lote.
          El Registro Público de Comercio dice quién está detrás de cada
          empresa; ese cotejo va antes que cualquier nombre publicado.
        </p>

        <h2>Varios contratos al mismo proveedor, el mismo día</h2>
        <p className="muted">
          los {data.fraccionamiento.length} casos con más dinero, de{" "}
          {fmt(r.fraccionamiento_total)}
        </p>
        <EvidenceTable
          cols={[
            { key: "institucion", label: "institución" },
            { key: "nombre_uc", label: "oficina compradora" },
            { key: "proveedor", label: "empresa" },
            { key: "dia", label: "día", nw: true },
            { key: "contratos", label: "contratos", num: true },
            { key: "total_mxn", label: "total MXN", num: true, dec: 0 },
          ]}
          rows={data.fraccionamiento}
        />
        <p className="nota">
          Una compra consolidada, como los medicamentos de todo el año, deja
          el mismo rastro. Si fue eso o fraccionamiento, lo dice el
          expediente de cada caso.
        </p>
        <p className="descarga">
          Las tres tablas completas en CSV:{" "}
          <a href="/datos/f06_rotacion_licitaciones.csv" download>
            rotación
          </a>
          ,{" "}
          <a href="/datos/f06_anillos_constitucion.csv" download>
            constituciones en lote
          </a>{" "}
          y{" "}
          <a href="/datos/f06_fraccionamiento_mismo_dia.csv" download>
            adjudicaciones del mismo día
          </a>
          .
        </p>
      </section>
    </main>
  );
}
