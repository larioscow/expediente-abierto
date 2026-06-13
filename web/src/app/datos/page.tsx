import type { Metadata } from "next";
import datos from "@/data/datos.json";

const filas = datos.archivos.reduce((s, f) => s + f.filas, 0);

export const metadata: Metadata = {
  title: "Datos",
  description:
    "Todos los hallazgos del proyecto en CSV, con huella sha-256 para " +
    "verificar cada copia. Uso libre citando la fuente.",
};

export default function Datos() {
  const situaciones = datos.situaciones as Record<string, Record<string, number>>;
  return (
    <main>
      <header className="banda banda-pagina">
        <h1>
          {datos.archivos.length} archivos, {filas.toLocaleString("es-MX")}{" "}
          filas, cada archivo con su huella
        </h1>
        <p className="intro">
          Los hallazgos completos en CSV, tal como los produce el análisis,
          cada uno con su huella sha-256 para verificar cualquier copia. Los
          datos de origen vienen del gobierno: ComprasMX, el SAT, la
          Secretaría Anticorrupción y Buen Gobierno (antes SFP) y la CFE.
          Aquí están los cruces, libres para descargar citando la fuente.
        </p>
      </header>
      <section className="datos">
        <div className="wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">archivo</th>
                <th scope="col" className="num">filas</th>
                <th scope="col">sha-256</th>
              </tr>
            </thead>
            <tbody>
              {datos.archivos.map((f) => (
                <tr key={f.nombre}>
                  <td data-label="archivo">
                    <a href={`/datos/${f.nombre}`} download>
                      {f.nombre}
                    </a>
                  </td>
                  <td className="num" data-label="filas">
                    {f.filas.toLocaleString("es-MX")}
                  </td>
                  <td
                    className="muted hash"
                    data-label="sha-256"
                    style={{ fontSize: ".62rem" }}
                  >
                    {f.sha256}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="nota">
          Los archivos con columna <code>situacion</code> separan los
          estatus del listado 69-B del SAT (la lista de factureras):{" "}
          {Object.entries(situaciones)
            .map(
              ([nombre, cuentas]) =>
                `${nombre} (${Object.entries(cuentas)
                  .map(
                    ([k, v]) =>
                      `${Number(v).toLocaleString("es-MX")} ${k.toLowerCase()}`,
                  )
                  .join(", ")})`,
            )
            .join("; ")}
          . Estos archivos no acusan a nadie: las filas «presunto» siguen sin
          resolución firme del SAT y los cruces por nombre admiten homónimos.
          También puede haber inhabilitaciones impugnadas o suspendidas que
          el directorio aún no refleja.
        </p>
      </section>
    </main>
  );
}
