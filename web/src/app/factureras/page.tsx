import type { Metadata } from "next";
import { EvidenceTable } from "@/components/EvidenceTable";
import cifras from "@/data/cifras.json";
import data from "@/data/factureras.json";
import { fmt } from "@/lib/fmt";

export const metadata: Metadata = {
  title: "Contratos a factureras confirmadas por el SAT",
  description:
    `$${fmt(cifras.facturera_rfc_monto, 0)} millones en contratos federales ` +
    "y estatales a factureras confirmadas por el SAT (art. 69-B definitivo). " +
    "Todo verificado por RFC, con liga al anuncio de origen.",
};

export default function Factureras() {
  return (
    <main>
      <header className="banda banda-pagina">
        <h1>
          ${fmt(cifras.facturera_rfc_monto, 0)} millones a factureras
          confirmadas por el SAT
        </h1>
        <p className="intro">
          El SAT publica, en la lista del artículo 69-B del Código Fiscal,
          qué empresas facturan operaciones que no existen: las{" "}
          <strong>«factureras»</strong>. Aquí solo hay empresas cuyo RFC está
          en la lista definitiva y que recibieron contratos públicos. La
          confirmación del SAT tarda años. Para cuando llega, el dinero ya se
          pagó.
        </p>
        <dl className="tablero menor">
          <div>
            <dt>millones mxn</dt>
            <dd>${fmt(cifras.facturera_rfc_monto, 0)}</dd>
          </div>
          <div>
            <dt>contratos por rfc</dt>
            <dd>{cifras.facturera_rfc_contratos}</dd>
          </div>
          <div>
            <dt>firmados en</dt>
            <dd>{cifras.facturera_rfc_rango}</dd>
          </div>
        </dl>
      </header>
      <section>
        <EvidenceTable
          cols={[
            { key: "proveedor", label: "empresa" },
            { key: "ambito", label: "ámbito", nw: true },
            { key: "definitivo_dof", label: "confirmada por SAT", nw: true },
            { key: "fecha_contrato", label: "firma del contrato", nw: true },
            { key: "comprador", label: "quién contrató" },
            { key: "monto_mxn_millones", label: "millones MXN", num: true, dec: 2 },
            { key: "direccion_anuncio", label: "fuente", link: true },
          ]}
          rows={data.confirmadas_rfc}
        />
        <p className="nota">
          Las empresas que desvirtuaron su situación ante el SAT u obtuvieron
          sentencia favorable se excluyen en cada actualización.
        </p>

        <h2>El histórico que falta confirmar</h2>
        <p>
          Otros ${fmt(cifras.facturera_hist_monto, 0)} millones en{" "}
          {fmt(cifras.facturera_hist_contratos)} contratos de 2010 a 2023,
          repartidos entre {fmt(cifras.facturera_hist_empresas)} empresas,
          coinciden por <strong>nombre</strong> con factureras confirmadas.
          Puede haber homónimos: ningún caso de esta tabla debe publicarse
          sin confirmar el RFC. Los {data.historico_nombre.length} montos
          mayores:
        </p>
        <EvidenceTable
          cols={[
            { key: "proveedor", label: "empresa" },
            { key: "definitivo_dof", label: "confirmada por SAT", nw: true },
            { key: "inicio_contrato", label: "firma del contrato", nw: true },
            { key: "titulo_contrato", label: "objeto" },
            { key: "monto_mxn_millones", label: "millones MXN", num: true, dec: 2 },
          ]}
          rows={data.historico_nombre}
        />
        <p className="descarga">
          La evidencia verificada por RFC, federal{" "}
          <a href="/datos/f01_detalle_completo.csv" download>
            f01_detalle_completo.csv
          </a>{" "}
          y estatal{" "}
          <a href="/datos/f10_efos_estatal.csv" download>
            f10_efos_estatal.csv
          </a>
          ; el histórico por nombre{" "}
          <a href="/datos/f01h_detalle_completo.csv" download>
            f01h_detalle_completo.csv
          </a>
          .
        </p>
      </section>
    </main>
  );
}
