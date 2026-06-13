import type { Metadata } from "next";
import { EvidenceTable } from "@/components/EvidenceTable";
import cifras from "@/data/cifras.json";
import data from "@/data/inhabilitadas.json";
import { fmt } from "@/lib/fmt";

export const metadata: Metadata = {
  title: `${cifras.inhabilitadas_n} contratos a empresas inhabilitadas`,
  description:
    "Contratos federales y estatales firmados dentro del periodo de " +
    "inhabilitación que consta en el directorio oficial de sancionados, con " +
    "liga al contrato original.",
};

export default function Inhabilitadas() {
  const empresas = new Set(data.contratos.map((c) => c.rfc)).size;
  const millones = data.contratos.reduce((s, c) => s + c.monto_mxn_millones, 0);
  return (
    <main>
      <header className="banda banda-pagina">
        <h1>
          {cifras.inhabilitadas_n} contratos firmados durante una
          inhabilitación
        </h1>
        <p className="intro">
          Cuando una empresa incumple o defrauda, la autoridad puede{" "}
          <strong>inhabilitarla</strong>. Mientras la sanción corre, el
          artículo 50 de la LAASSP impide darle contratos públicos y el 59 de
          la LGRA sanciona al servidor público que lo autoriza. La lista se
          limita a contratos cuya fecha de firma cae dentro de una
          inhabilitación registrada con el RFC de la empresa en el directorio
          oficial de sancionados.
        </p>
        <dl className="tablero menor">
          <div>
            <dt>contratos</dt>
            <dd>{cifras.inhabilitadas_n}</dd>
          </div>
          <div>
            <dt>empresas</dt>
            <dd>{empresas}</dd>
          </div>
          <div>
            <dt>millones mxn</dt>
            <dd>${fmt(millones, 0)}</dd>
          </div>
        </dl>
      </header>
      <section>
        <EvidenceTable
          cols={[
            { key: "proveedor", label: "empresa" },
            { key: "ambito", label: "ámbito", nw: true },
            { key: "desde", label: "inhabilitada desde", nw: true },
            { key: "hasta", label: "hasta", nw: true },
            { key: "fecha_contrato", label: "firma del contrato", nw: true },
            { key: "comprador", label: "quién contrató" },
            { key: "monto_mxn_millones", label: "millones MXN", num: true, dec: 2 },
            { key: "direccion_anuncio", label: "fuente", link: true },
          ]}
          rows={data.contratos}
        />
        <p className="nota">
          La empresa pudo impugnar la sanción, o un juez pudo suspenderla,
          sin que el directorio lo refleje todavía. El{" "}
          <a href="/replica/">derecho de réplica</a> está abierto.
        </p>
        <p className="descarga">
          Federal:{" "}
          <a href="/datos/f05_durante_inhabilitacion.csv" download>
            f05_durante_inhabilitacion.csv
          </a>
          ; estatal:{" "}
          <a href="/datos/f10_inhabilitados_estatal.csv" download>
            f10_inhabilitados_estatal.csv
          </a>
          .
        </p>
      </section>
    </main>
  );
}
