export function fmt(x: number | null | undefined, dec = 1): string {
  if (x == null || Number.isNaN(x)) return "—";
  const decimals = Number.isInteger(x) ? 0 : dec;
  return x.toLocaleString("es-MX", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function pesos(importe: number): string {
  if (importe >= 1e6) return `$${fmt(importe / 1e6)} millones`;
  return `$${importe.toLocaleString("es-MX", { maximumFractionDigits: 0 })} pesos`;
}

export function fechaCentro(iso: string | null | undefined): string {
  if (!iso) return "—";
  const f = new Date(iso).toLocaleString("es-MX", {
    timeZone: "America/Mexico_City",
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${f} (hora del centro)`;
}
