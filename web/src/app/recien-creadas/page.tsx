import type { Metadata } from "next";
import { EvidenceTable } from "@/components/EvidenceTable";
import cifras from "@/data/cifras.json";
import data from "@/data/recien_creadas.json";
import { fmt } from "@/lib/fmt";

export const metadata: Metadata = {
  title: `$${fmt(cifras.jovenes_monto, 0)} millones a empresas recién creadas`,
  description:
    `$${fmt(cifras.jovenes_monto, 0)} millones en contratos federales a ` +
    "empresas con menos de un año de constituidas. La mayoría se entregó " +
    "sin licitación.",
};

export default function RecienCreadas() {
  const masJoven = Math.min(...data.contratos.map((c) => c.edad_dias));
  const sinLicitacion = data.contratos.filter((c) =>
    String(c.tipo_procedimiento ?? "").startsWith("ADJUDICACIÓN"),
  ).length;
  const tieneTecho = data.contratos.some(
    (c) => "tipo_monto" in c && c.tipo_monto === "techo_maximo",
  );
  return (
    <main>
      <header className="banda banda-pagina">
        <h1>
          ${fmt(cifras.jovenes_monto, 0)} millones a empresas con menos de un
          año de vida
        </h1>
        <p className="intro">
          Empresas que aún no cumplían un año de constituidas ganaron
          contratos federales por ${fmt(cifras.jovenes_monto, 0)} millones;
          la fecha de creación consta en el propio RFC. De ese universo,{" "}
          {fmt(data.resumen.jovenes_grandes_total)} contratos fueron de $5
          millones o más. Aquí los {data.contratos.length} mayores, que suman
          ${fmt(data.resumen.top_monto_mxn_m, 0)} millones;{" "}
          {sinLicitacion} de los {data.contratos.length} se adjudicaron sin
          licitación pública.
        </p>
        <dl className="tablero menor">
          <div>
            <dt>millones mxn</dt>
            <dd>${fmt(cifras.jovenes_monto, 0)}</dd>
          </div>
          <div>
            <dt>contratos de $5M o más</dt>
            <dd>{fmt(data.resumen.jovenes_grandes_total)}</dd>
          </div>
          <div>
            <dt>la más joven</dt>
            <dd>{masJoven} días</dd>
          </div>
        </dl>
      </header>
      <section>
        <EvidenceTable
          cols={[
            { key: "proveedor", label: "empresa" },
            { key: "constituida", label: "creada", nw: true },
            { key: "fecha_contrato", label: "ganó", nw: true },
            { key: "edad_dias", label: "días", num: true },
            { key: "institucion", label: "quién contrató" },
            { key: "monto_mxn_millones", label: "millones MXN", num: true, dec: 1 },
            { key: "direccion_anuncio", label: "fuente", link: true },
          ]}
          rows={data.contratos}
        />
        <p className="nota">
          Ganar contratos con meses de constituida no es una falta en sí. La
          alerta salta cuando los montos son de este tamaño y no hubo
          licitación de por medio. Antes de afirmar nada hay que cotejar la
          fecha de constitución en el acta.
        </p>
        {tieneTecho && (
          <p className="nota">
            En algunos contratos la cifra es el monto máximo autorizado, no
            necesariamente lo que se terminó pagando (filas con tipo
            «techo_maximo» en el archivo descargable).
          </p>
        )}
        <p className="descarga">
          Los {data.contratos.length} contratos con la edad exacta de cada
          empresa:{" "}
          <a href="/datos/f04_top30_jovenes_grandes.csv" download>
            f04_top30_jovenes_grandes.csv
          </a>
          . El universo por año:{" "}
          <a href="/datos/f04_resumen.csv" download>
            f04_resumen.csv
          </a>
          .
        </p>
      </section>
    </main>
  );
}
