import Link from "next/link";
import { EvidenceTable } from "@/components/EvidenceTable";
import { FeedAlertas } from "@/components/FeedAlertas";
import { MapaMatriz } from "@/components/MapaMatriz";
import { PulsoAlertas } from "@/components/PulsoAlertas";
import alertas from "@/data/alertas.json";
import cifras from "@/data/cifras.json";
import colusion from "@/data/colusion.json";
import denuncias from "@/data/denuncias.json";
import meta from "@/data/meta.json";
import sinCompetencia from "@/data/sin_competencia.json";
import { fechaCentro, fmt } from "@/lib/fmt";

// Hallazgos ordenados de lo más cierto (un registro lo dice, y hay un
// contrato dentro de la ventana) a lo más inferido (un patrón estadístico).
// Cada uno cita la regla que lo justifica, al modo de Euclides: nada se
// afirma sin nombrar de dónde sale.
const hallazgos = [
  {
    href: "/inhabilitadas/",
    titulo: "Contratos firmados en plena inhabilitación",
    detalle: "Empresas que tenían prohibido contratar siguieron cobrando.",
    regla:
      "El art. 50 de la LAASSP prohíbe dar contratos a una empresa " +
      "inhabilitada; el 59 de la LGRA sanciona a quien lo autoriza.",
    cifra: String(cifras.inhabilitadas_n),
    unidad: "contratos",
  },
  {
    href: "/factureras/",
    titulo: "Dinero público a factureras confirmadas por el SAT",
    detalle:
      `${cifras.facturera_rfc_contratos} contratos verificados por RFC. ` +
      `Otros $${fmt(cifras.facturera_hist_monto, 0)} millones del histórico ` +
      "siguen en revisión.",
    regla:
      "Art. 69-B del Código Fiscal: el RFC está en la lista definitiva " +
      "del SAT por facturar operaciones que no existen.",
    cifra: `$${fmt(cifras.facturera_rfc_monto, 0)}`,
    unidad: "millones mxn",
  },
  {
    href: "/sobrecostos/",
    titulo: "Contratos que crecieron por encima del tope legal",
    detalle: "Se firmaron por un precio y terminaron costando mucho más.",
    regla:
      "Un contrato no puede crecer más de 20% (art. 52 LAASSP); 25% en " +
      "obra pública (art. 59 LOPSRM). Estos rebasan el tope que les aplica.",
    cifra: String(cifras.sobrecostos_n),
    unidad: "contratos",
  },
  {
    href: "/recien-creadas/",
    titulo: "Empresas con menos de un año de vida",
    detalle: "Casi siempre por adjudicación directa.",
    regla:
      "La adjudicación directa es excepción, no regla (arts. 1 y 41 " +
      "LAASSP); aquí la gana una empresa que aún no cumplía un año.",
    cifra: `$${fmt(cifras.jovenes_monto, 0)}`,
    unidad: "millones mxn",
  },
  {
    href: "/colusion/",
    titulo: "Grupos cerrados que se reparten las licitaciones",
    detalle:
      "Empresas que se turnan los contratos de una misma oficina. " +
      "Algunas nacieron con días de diferencia.",
    regla:
      "Reparto y rotación que la competencia real difícilmente produce. " +
      "Aquí no hay ley citada: es un patrón en los propios números.",
    cifra: String(colusion.resumen.oficinas_total),
    unidad: "oficinas",
  },
  {
    href: "/sin-competencia/",
    titulo: "Instituciones que compran casi todo sin competencia",
    detalle: "Unos cuantos proveedores concentran el gasto.",
    regla:
      "La adjudicación directa es una excepción de la ley (arts. 1 y 41 " +
      "LAASSP), no la vía para casi todo el gasto de una oficina.",
    cifra: String(sinCompetencia.resumen.instituciones_total),
    unidad: "instituciones",
  },
];

// "83017-2026"…"83022-2026" consecutivos -> "83017–83022/2026 · 6 folios";
// si la numeración salta, se listan completos para no inventar un rango.
function rangoFolios(folios: string[]): string {
  if (folios.length === 1) return folios[0];
  const orden = [...folios].sort();
  const nums = orden.map((f) => parseInt(f, 10));
  const anios = new Set(orden.map((f) => f.split("-")[1]));
  const consecutivos =
    anios.size === 1 &&
    nums.every((n, i) => i === 0 || n === nums[i - 1] + 1);
  if (consecutivos && folios.length > 2) {
    return `${nums[0]}–${nums[nums.length - 1]}/${[...anios][0]} · ${folios.length} folios`;
  }
  return orden.join(", ");
}

export default function Portada() {
  const casos = denuncias.casos.map((c) => ({
    empresa: c.empresa,
    sancion: `${c.inhabilitada_desde.replaceAll("-", "‑")} al ${c.inhabilitada_hasta.replaceAll("-", "‑")}`,
    contratos: c.contratos.length,
    importe_mxn: c.contratos.reduce((s, x) => s + x.importe_mxn, 0),
    folios: rangoFolios(c.folios),
  }));
  const totalCasos = {
    empresa: `${casos.length} empresas`,
    contratos: casos.reduce((s, c) => s + c.contratos, 0),
    importe_mxn: casos.reduce((s, c) => s + c.importe_mxn, 0),
    folios: `${denuncias.folios.length} folios`,
  };
  return (
    <main>
      <header className="heroe">
        <h1>
          La impunidad, documentada<span className="punto">.</span>
        </h1>
        <div>
          <p className="intro">
            Un detector de corrupción en las compras del gobierno de México.
            Señala los contratos sospechosos: dinero público a empresas
            fantasma, a proveedores inhabilitados, a precios inflados. Con
            nombre, monto y fuente oficial.
          </p>
        </div>
        <figure className="mapa">
          <MapaMatriz
            entidades={[...new Set(alertas.alertas.map((a) => a.entidad))]}
          />
        </figure>
      </header>

      <section>
        <dl className="tablero">
          <div>
            <dt>denuncias presentadas</dt>
            <dd>{denuncias.folios.length}</dd>
          </div>
          <div>
            <dt>millones mxn a factureras</dt>
            <dd>${fmt(cifras.facturera_rfc_monto, 0)}</dd>
          </div>
        </dl>
      </section>

      <section>
        <h2>Los casos denunciados</h2>
        <p>
          Cuando un caso es claro, lo denunciamos ante la Secretaría
          Anticorrupción y Buen Gobierno. Van {denuncias.folios.length}{" "}
          denuncias.{" "}
          <Link href="/denuncias/">Aquí están, con sus contratos y folios</Link>
          .
        </p>
        <EvidenceTable
          cols={[
            { key: "empresa", label: "empresa" },
            { key: "sancion", label: "tenía prohibido contratar" },
            { key: "contratos", label: "contratos", num: true },
            { key: "importe_mxn", label: "monto (MXN)", num: true, dec: 0 },
            { key: "folios", label: "folios de denuncia" },
          ]}
          rows={casos}
          pie={totalCasos}
        />
        <p className="nota">
          Denunciamos para que la autoridad revise lo que ya consta en
          registros oficiales. Ningún folio acusa de un delito, y alguna de
          estas inhabilitaciones podría estar impugnada todavía.
        </p>
      </section>

      <section>
        <h2>Cómo leer esto</h2>
        <p className="intro">
          Antes de los hallazgos, los cimientos que todo lo de abajo da por
          sentado: qué significa cada término, de dónde salen los datos y qué
          regla se está aplicando. Nada se afirma sin decir de dónde sale.
        </p>

        <h3>Definiciones</h3>
        <dl className="glosario">
          <div>
            <dt>Facturera (69-B)</dt>
            <dd>
              Empresa que el SAT puso en la lista del artículo 69-B del Código
              Fiscal por facturar operaciones que no existen. «Definitiva»
              significa que el SAT ya lo confirmó.
            </dd>
          </div>
          <div>
            <dt>Inhabilitado</dt>
            <dd>
              Proveedor al que la autoridad le prohibió contratar con el
              gobierno por un periodo. Consta en el directorio de sancionados
              de la SFP o en el DOF.
            </dd>
          </div>
          <div>
            <dt>Adjudicación directa</dt>
            <dd>
              Contrato dado a un solo proveedor sin licitación. La ley solo la
              permite como excepción.
            </dd>
          </div>
          <div>
            <dt>Convenio modificatorio</dt>
            <dd>
              Documento que aumenta el monto o el plazo de un contrato ya
              firmado.
            </dd>
          </div>
          <div>
            <dt>Colusión</dt>
            <dd>
              Empresas que aparentan competir pero se turnan los contratos de
              una misma oficina.
            </dd>
          </div>
          <div>
            <dt>Señal</dt>
            <dd>
              Un filtro automático que marca un contrato para revisar. Una
              bandera, no una acusación.
            </dd>
          </div>
        </dl>

        <h3>Supuestos y fuentes</h3>
        <ul className="cimientos">
          <li>
            Todo sale de <strong>registros oficiales</strong>: el SAT, la SFP,
            el DOF, ComprasMX y la Plataforma Nacional de Transparencia.
          </li>
          <li>
            ComprasMX publica el <strong>nombre</strong> del proveedor, no su
            RFC. Una coincidencia por nombre debe confirmarse en el acta de
            fallo antes de citarla.
          </li>
          <li>
            Ningún hallazgo acusa de un delito: señala lo que ya consta en
            registros oficiales para que la autoridad revise. Alguna
            inhabilitación podría estar impugnada todavía.
          </li>
        </ul>

        <h3>Las reglas</h3>
        <ul className="cimientos">
          <li>
            <strong>Inhabilitación.</strong> El art. 50 de la LAASSP prohíbe
            dar contratos a una empresa inhabilitada; el art. 59 de la LGRA
            sanciona al servidor que lo autoriza.
          </li>
          <li>
            <strong>Factureras.</strong> El art. 69-B del Código Fiscal: el RFC
            quedó en la lista definitiva del SAT por operaciones simuladas.
          </li>
          <li>
            <strong>Tope de convenios.</strong> Un contrato no puede crecer más
            de 20% (art. 52 LAASSP); 25% en obra pública (art. 59 LOPSRM).
          </li>
          <li>
            <strong>Plazo de licitación.</strong> Una licitación pública
            necesita ≥15 días entre convocatoria y apertura (art. 32 LAASSP),
            reducibles a 10 con justificación.
          </li>
        </ul>
      </section>

      <section>
        <h2>Hallazgos</h2>
        <ul className="hallazgos">
          {hallazgos.map((h) => (
            <li key={h.href}>
              <Link href={h.href}>
                <strong>{h.titulo}</strong>
                <span>{h.detalle}</span>
                <span className="regla">Regla: {h.regla}</span>
                <span className="cifra">
                  {h.cifra}
                  <small>{h.unidad}</small>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section className="banda banda-envivo">
        <div className="cabecera">
          <h2 className="envivo">Monitor de señales</h2>
          <span className="ultima">
            {alertas.alertas.length} en observación · última revisión:{" "}
            {fechaCentro(meta.alertas_ultima)}
          </span>
        </div>
        <p className="intro">
          Esto no son denuncias ni fraude probado. Son filtros automáticos
          sobre las compras del día. Cada señal es una regla con nombre:
          adjudicación directa, plazo recortado, un ganador que aparece en una
          lista de sancionados. Marcan un contrato que vale la pena revisar;
          más puntos solo significan más señales encendidas, no más culpa. Lo
          confirmado está arriba, en los casos denunciados.
        </p>
        {alertas.alertas.length === 0 ? (
          <p className="pendiente">
            Sin señales por ahora. El monitor sigue corriendo.
          </p>
        ) : (
          <>
            <PulsoAlertas alertas={alertas.alertas} />
            <FeedAlertas alertas={alertas.alertas} max={12} />
            {alertas.alertas.length > 12 && (
              <p className="nota">
                Se listan las 12 más recientes; la tira de arriba dibuja las{" "}
                {alertas.alertas.length}.
              </p>
            )}
          </>
        )}
        <p className="nota">
          ComprasMX no publica el RFC, solo el nombre del proveedor. Antes de
          citar una coincidencia hay que confirmarla en el acta de fallo.
        </p>
      </section>
    </main>
  );
}
