import type { Metadata } from "next";
import Link from "next/link";
import { CONTACTO_REPLICA, REPO_URL } from "@/lib/config";

export const metadata: Metadata = {
  title: "Aviso legal y derecho de réplica",
  description:
    "Qué afirma este sitio y qué no. Cómo pedir una corrección o publicar " +
    "una réplica, con respuesta en 10 días hábiles.",
};

export default function Replica() {
  return (
    <main>
      <header className="banda banda-pagina">
        <h1>Aviso legal y derecho de réplica</h1>
        <p className="intro">
          Este sitio publica <strong>hechos verificables con fuente
          oficial</strong>: contratos asentados en los datos abiertos de
          ComprasMX y registros de los listados públicos del SAT (art. 69-B
          del Código Fiscal) y del Directorio de Proveedores y Contratistas
          Sancionados. Que una persona o empresa aparezca aquí{" "}
          <strong>no la acusa de ningún delito</strong>. Significa que dos
          registros públicos coinciden y que, a juicio de este proyecto, la
          autoridad debería investigar.
        </p>
      </header>
      <section className="legal">
        <ul>
          <li>
            El listado del 69-B es un acto administrativo del SAT y se puede
            impugnar. Cuando una empresa desvirtúa la presunción o gana el
            juicio, sale del hallazgo principal en la siguiente actualización.
          </li>
          <li>
            Las inhabilitaciones también se pelean en tribunales y a veces un
            juez las suspende. El sitio refleja el directorio público tal
            como estaba el día de la descarga.
          </li>
          <li>
            Los cruces por nombre (histórico y monitoreo en vivo) están
            etiquetados como tales. Puede haber homónimos y hay que confirmar
            cada caso.
          </li>
        </ul>

        <h2>Cómo pedir una corrección</h2>
        <p className="intro">
          Si una empresa o persona mencionada considera que un dato es
          incorrecto o está desactualizado, escriba a{" "}
          <strong>
            <a href={`mailto:${CONTACTO_REPLICA}`}>{CONTACTO_REPLICA}</a>
          </strong>{" "}
          con los documentos que lo respalden: la resolución que desvirtúa,
          una suspensión judicial o la fe de erratas de la fuente.
          Compromisos:
        </p>
        <ul>
          <li>Respuesta en un máximo de 10 días hábiles.</li>
          <li>
            Si la fuente oficial respalda la aclaración, la corrección se
            publica en la siguiente actualización y se deja constancia del
            cambio.
          </li>
          <li>La réplica se publica junto al dato si así se solicita.</li>
        </ul>

        <h2>Cómo verificar las cifras</h2>
        <p className="intro">
          Toda cifra publicada se puede recalcular desde las fuentes
          oficiales citadas.
          {REPO_URL ? (
            <>
              {" "}
              El método y el código están en el{" "}
              <a href={REPO_URL}>repositorio del proyecto</a> para que
              cualquiera reproduzca el análisis por su cuenta.
            </>
          ) : null}{" "}
          Los archivos derivados, con su huella sha-256 para validar
          cualquier copia, están en la sección{" "}
          <Link href="/datos/">datos</Link>.
        </p>
      </section>
    </main>
  );
}
