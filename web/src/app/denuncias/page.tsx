import type { Metadata } from "next";
import { EvidenceTable } from "@/components/EvidenceTable";
import { VentanaSancion } from "@/components/VentanaSancion";
import denuncias from "@/data/denuncias.json";
import { fmt, pesos } from "@/lib/fmt";

export const metadata: Metadata = {
  title: `${denuncias.folios.length} denuncias presentadas`,
  description:
    "Las denuncias presentadas ante la Secretaría Anticorrupción y Buen Gobierno: " +
    "cada folio con sus contratos y la liga para verificarlos.",
};

export default function Denuncias() {
  const contratos = denuncias.casos.reduce((s, c) => s + c.contratos.length, 0);
  const millones =
    denuncias.casos.reduce(
      (s, c) => s + c.contratos.reduce((t, x) => t + x.importe_mxn, 0),
      0,
    ) / 1e6;
  return (
    <main>
      <header className="banda banda-pagina">
        <h1>{denuncias.folios.length} denuncias presentadas</h1>
        <p className="intro">
          Estas denuncias las presentamos en el{" "}
          <a href="https://sidec.buengobierno.gob.mx/" rel="noopener">SIDEC</a>,
          el sistema de denuncias ciudadanas de la Secretaría Anticorrupción y
          Buen Gobierno, con el expediente completo de pruebas. Cada denuncia
          ampara los contratos que una empresa firmó con una institución
          durante su inhabilitación.
        </p>
        <dl className="tablero menor">
          <div>
            <dt>empresas</dt>
            <dd>{denuncias.casos.length}</dd>
          </div>
          <div>
            <dt>contratos</dt>
            <dd>{contratos}</dd>
          </div>
          <div>
            <dt>millones mxn</dt>
            <dd>${fmt(millones, 0)}</dd>
          </div>
          <div>
            <dt>folios sidec</dt>
            <dd>{denuncias.folios.length}</dd>
          </div>
        </dl>
        <VentanaSancion
          ventanas={denuncias.casos.map((c) => ({
            etiqueta: c.empresa,
            desde: c.inhabilitada_desde,
            hasta: c.inhabilitada_hasta,
            contratos: c.contratos.map((x) => ({
              fecha: x.fecha,
              importe: x.importe_mxn,
            })),
          }))}
        />
      </header>

      <section>
        <ul className="hallazgos">
          {denuncias.casos.map((caso) => {
            const total = caso.contratos.reduce((s, c) => s + c.importe_mxn, 0);
            return (
              <li key={caso.rfc}>
                <a href={`#${caso.rfc}`}>
                  <strong>{caso.empresa.toLowerCase()}</strong>
                  <span>
                    sanción {caso.inhabilitada_desde} → {caso.inhabilitada_hasta}
                  </span>
                  <span className="cifra">
                    {pesos(total)}
                    <small>
                      {caso.contratos.length}{" "}
                      {caso.contratos.length === 1 ? "contrato" : "contratos"}
                    </small>
                  </span>
                </a>
              </li>
            );
          })}
        </ul>

        {denuncias.casos.map((caso) => {
          const total = caso.contratos.reduce((s, c) => s + c.importe_mxn, 0);
          return (
            <div key={caso.rfc} id={caso.rfc}>
              <h2>{caso.empresa.toLowerCase()}</h2>
              <p className="caso-meta">
                <span>
                  rfc {caso.rfc} · sanción {caso.inhabilitada_desde} →{" "}
                  {caso.inhabilitada_hasta} · folios {caso.folios.join(", ")}
                </span>
                <b>{pesos(total)}</b>
              </p>
              <EvidenceTable
                cols={[
                  { key: "institucion", label: "quién contrató" },
                  { key: "fecha", label: "firma del contrato", nw: true },
                  { key: "importe_mxn", label: "monto (MXN)", num: true, dec: 0 },
                  { key: "folio", label: "folio de denuncia", nw: true },
                  { key: "url", label: "fuente", link: true },
                ]}
                rows={caso.contratos}
              />
            </div>
          );
        })}

        <p className="nota">
          El directorio de sancionados publica con rezago: alguna de estas
          inhabilitaciones podría estar impugnada o suspendida sin que el
          registro lo muestre aún. Cada folio pide investigar; ninguno imputa
          un delito.
        </p>
      </section>
    </main>
  );
}
