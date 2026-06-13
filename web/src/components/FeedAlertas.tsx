export type Alerta = {
  uuid: string;
  ts?: string;
  numero: string;
  nombre: string;
  dependencia: string;
  entidad?: string;
  orden_gobierno?: string;
  estado_comprador?: string;
  score: number;
  reasons?: string[];
  url: string;
};

export function razon(r: string): string {
  const i = r.indexOf(": ");
  return i >= 0 ? r.slice(i + 2) : r;
}

// El portal trunca los títulos largos a media palabra ("…POBLACIÓN DAMN")
// y a veces los envuelve en comillas desparejadas ("''OBJETO”"): se recorta
// la palabra colgante, se marca la elipsis y se pelan las comillas.
export function titulo(nombre: string): string {
  const limpio = nombre.replace(/^[‘’“”"']+/, "").replace(/[‘’“”"']+$/, "").trim();
  if (limpio.length < 78) return limpio;
  return `${limpio.replace(/\s+\S*$/, "")}…`;
}

function hora(ts?: string): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleTimeString("es-MX", {
    timeZone: "America/Mexico_City",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function FeedAlertas({
  alertas,
  max,
}: {
  alertas: Alerta[];
  max?: number;
}) {
  const orden = [...alertas]
    .sort((a, b) => (b.ts ?? "").localeCompare(a.ts ?? ""))
    .slice(0, max ?? alertas.length);
  return (
    <ol className="registro">
      {orden.map((a) => (
        <li key={a.uuid}>
          <div className="cuando">
            <span className="hora">{hora(a.ts)}</span>
            <span
              className="puntos"
              role="img"
              aria-label={`riesgo ${a.score}`}
              title={`riesgo ${a.score}`}
            >
              {Array.from({ length: Math.min(a.score, 8) }, (_, i) => (
                <i key={i} />
              ))}
            </span>
          </div>
          <div>
            <p className="meta">
              {a.dependencia}
              {a.entidad ? ` · ${a.entidad}` : ""}
            </p>
            <p className="objeto">{titulo(a.nombre)}</p>
            <p className="senales">
              {(a.reasons ?? []).map(razon).join(" · ")}
              {" "}
              <span className="numero" style={{ whiteSpace: "nowrap" }}>
                · {a.numero}
              </span>{" "}
              <span style={{ whiteSpace: "nowrap" }}>
                ·{" "}
                <a href={a.url} rel="noopener">
                  fuente
                </a>
              </span>
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
