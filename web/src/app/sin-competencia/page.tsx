import type { Metadata } from "next";
import { EvidenceTable } from "@/components/EvidenceTable";
import data from "@/data/sin_competencia.json";
import { fmt } from "@/lib/fmt";

const r = data.resumen;

export const metadata: Metadata = {
  title: `$${fmt(r.monto_directas_mxn_m, 0)} millones por adjudicación directa`,
  description:
    "Instituciones federales donde la adjudicación directa es la regla y " +
    "proveedores que concentran ese gasto.",
};

export default function SinCompetencia() {
  return (
    <main>
      <header className="banda banda-pagina">
        <h1>
          ${fmt(r.monto_directas_mxn_m, 0)} millones por adjudicación directa
        </h1>
        <p className="intro">
          La ley permite la adjudicación directa como excepción, pero hay
          oficinas donde es la regla. En las {r.instituciones_total}{" "}
          instituciones de este hallazgo, esa vía concentra $
          {fmt(r.monto_directas_mxn_m, 0)} millones de{" "}
          {fmt(r.contratos_total)} contratos. Los medicamentos de patente y
          las compras entre entidades públicas tienen su propia vía en los
          artículos 1 y 41 de la LAASSP.
        </p>
        <dl className="tablero menor">
          <div>
            <dt>instituciones</dt>
            <dd>{r.instituciones_total}</dd>
          </div>
          <div>
            <dt>millones mxn directos</dt>
            <dd>${fmt(r.monto_directas_mxn_m, 0)}</dd>
          </div>
          <div>
            <dt>contratos</dt>
            <dd>{fmt(r.contratos_total)}</dd>
          </div>
        </dl>
      </header>
      <section>
        <h2>Quién compra casi todo sin licitar</h2>
        <p className="muted">
          las {data.instituciones.length} instituciones con mayor proporción
          de gasto directo, de {r.instituciones_total}
        </p>
        <EvidenceTable
          cols={[
            { key: "institucion", label: "institución" },
            { key: "contratos", label: "contratos", num: true },
            { key: "pct_directas_n", label: "% directas (contratos)", num: true, dec: 1 },
            { key: "monto_mxn_millones", label: "millones MXN", num: true, dec: 0 },
            { key: "pct_directas_monto", label: "% directas (dinero)", num: true, dec: 1 },
          ]}
          rows={data.instituciones}
        />
        <p className="nota">
          Comprar por adjudicación directa es legal cuando se funda y motiva.
          Esa justificación no viene en los datos abiertos: hay que pedir el
          expediente antes de citar un caso.
        </p>

        <h2>Quién concentra ese dinero</h2>
        <EvidenceTable
          cols={[
            { key: "institucion", label: "institución" },
            { key: "proveedor", label: "empresa" },
            { key: "monto_directas_mxn_m", label: "millones directos", num: true, dec: 1 },
            { key: "n_directas", label: "contratos", num: true },
            { key: "pct_del_gasto_directo", label: "% del gasto directo", num: true, dec: 1 },
          ]}
          rows={data.proveedor_unico}
        />
        <p className="nota">
          Concentrar contratos directos no es una falta del proveedor. La
          decisión de no licitar la toma la oficina que adjudica.
        </p>
        <p className="descarga">
          La concentración por proveedor, completa:{" "}
          <a href="/datos/f02_proveedores_concentracion_directas.csv" download>
            f02_proveedores_concentracion_directas.csv
          </a>
          . Las {r.instituciones_total} instituciones:{" "}
          <a href="/datos/f02_instituciones_pct_directas.csv" download>
            f02_instituciones_pct_directas.csv
          </a>
          .
        </p>
      </section>
    </main>
  );
}
