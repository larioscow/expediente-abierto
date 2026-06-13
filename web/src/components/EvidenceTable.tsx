type Cell = string | number | boolean | null;

export type Col = {
  key: string;
  label: string;
  num?: boolean;
  dec?: number;
  link?: boolean;
  nw?: boolean; // no partir el valor (fechas, folios)
};

function fmtCell(v: Cell, col: Col): string {
  if (v == null || v === "") return "—";
  if (col.num && typeof v === "number") {
    const dec = col.dec ?? (Number.isInteger(v) ? 0 : 1);
    // un monto real nunca debe imprimirse como 0: si los decimales pedidos
    // lo aplastan, caer a cifras significativas
    if (v !== 0 && Math.round(Math.abs(v) * 10 ** dec) === 0) {
      return v.toLocaleString("es-MX", { maximumSignificantDigits: 2 });
    }
    return v.toLocaleString("es-MX", {
      minimumFractionDigits: dec,
      maximumFractionDigits: dec,
    });
  }
  return String(v);
}

function clases(col: Col): string | undefined {
  const c = [col.num && "num", col.nw && "nw"].filter(Boolean).join(" ");
  return c || undefined;
}

export function EvidenceTable({
  cols,
  rows,
  pie,
}: {
  cols: Col[];
  rows: Record<string, Cell>[];
  pie?: Record<string, Cell>;
}) {
  if (!rows.length) {
    return <p className="pendiente">Sin registros en la última actualización.</p>;
  }
  const llave = cols.find((c) => !c.num && !c.link)?.key;
  return (
    <div className="wrap">
      <table>
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c.key} scope="col" className={c.num ? "num" : undefined}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {cols.map((c) =>
                c.link ? (
                  <td key={c.key} className="fuente" data-label={c.label}>
                    {r[c.key] ? (
                      <a
                        href={String(r[c.key])}
                        rel="noopener"
                        aria-label={`fuente: ${llave ? String(r[llave] ?? "") : `fila ${i + 1}`}`}
                      >
                        fuente
                      </a>
                    ) : null}
                  </td>
                ) : (
                  <td key={c.key} className={clases(c)} data-label={c.label}>
                    {fmtCell(r[c.key], c)}
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
        {pie ? (
          <tfoot>
            <tr>
              {cols.map((c) => (
                <td key={c.key} className={clases(c)} data-label={c.label}>
                  {pie[c.key] != null && pie[c.key] !== ""
                    ? fmtCell(pie[c.key], c)
                    : ""}
                </td>
              ))}
            </tr>
          </tfoot>
        ) : null}
      </table>
    </div>
  );
}
