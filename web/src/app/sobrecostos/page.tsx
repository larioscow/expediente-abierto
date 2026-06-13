import type { Metadata } from "next";
import { EvidenceTable } from "@/components/EvidenceTable";
import cifras from "@/data/cifras.json";
import data from "@/data/sobrecostos.json";
import { fmt } from "@/lib/fmt";

export const metadata: Metadata = {
  title: `${cifras.sobrecostos_n} contratos crecieron por encima del tope legal`,
  description:
    "Contratos federales cuyo monto final superó el tope que la ley fija " +
    "para las ampliaciones (+20%, obra pública +25%), con la fuente de cada uno.",
};

export default function Sobrecostos() {
  const alDoble = data.contratos.filter((c) => c.pct_incremento >= 100).length;
  const mayor = Math.max(...data.contratos.map((c) => c.pct_incremento));
  return (
    <main>
      <header className="banda banda-pagina">
        <h1>
          {cifras.sobrecostos_n} contratos crecieron por encima del tope legal
        </h1>
        <p className="intro">
          Un contrato público no puede crecer más de <strong>20%</strong>{" "}
          sobre lo firmado; en obra pública el tope sube a 25%. Lo fijan el
          artículo 52 de la LAASSP y el 59 de la LOPSRM, y las ampliaciones
          se firman en convenios modificatorios. En esta lista solo aparecen
          los contratos que, según su monto final registrado, rebasan el tope
          que les aplica.
        </p>
        <dl className="tablero menor">
          <div>
            <dt>contratos</dt>
            <dd>{cifras.sobrecostos_n}</dd>
          </div>
          <div>
            <dt>al doble o más</dt>
            <dd>{alDoble}</dd>
          </div>
          <div>
            <dt>el que más creció</dt>
            <dd>+{fmt(mayor, 0)}%</dd>
          </div>
        </dl>
      </header>
      <section>
        <EvidenceTable
          cols={[
            { key: "proveedor", label: "empresa" },
            { key: "institucion", label: "quién contrató" },
            { key: "monto_original", label: "firmado por (MXN)", num: true, dec: 0 },
            { key: "monto_ultimo_convenio", label: "terminó en (MXN)", num: true, dec: 0 },
            { key: "pct_incremento", label: "creció %", num: true, dec: 1 },
            { key: "fecha_contrato", label: "firma", nw: true },
            { key: "direccion_anuncio", label: "fuente", link: true },
          ]}
          rows={data.contratos}
        />
        <p className="nota">
          La ley permite rebasar el tope solo con autorización escrita. Esa
          autorización, si existió, consta en el expediente de cada contrato,
          que estos datos no incluyen. Aparecer en la lista no prueba una
          irregularidad.
        </p>
        <p className="descarga">
          Ambos montos y el anuncio de cada convenio:{" "}
          <a href="/datos/f07_convenios_inflados.csv" download>
            f07_convenios_inflados.csv
          </a>
          .
        </p>
      </section>
    </main>
  );
}
