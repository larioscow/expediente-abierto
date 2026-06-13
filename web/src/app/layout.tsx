import type { Metadata } from "next";
import { JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import cifras from "@/data/cifras.json";
import meta from "@/data/meta.json";
import { fmt } from "@/lib/fmt";
import "./globals.css";

const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: {
    default:
      "Expediente Abierto: detector de corrupción en las compras del gobierno de México",
    template: "%s · Expediente Abierto",
  },
  description:
    "Señala los contratos públicos de México con indicios de corrupción: " +
    `dinero a empresas fantasma y a proveedores inhabilitados. ` +
    `${cifras.inhabilitadas_n} contratos firmados durante una inhabilitación, ` +
    `$${fmt(cifras.facturera_rfc_monto, 0)} millones a factureras confirmadas ` +
    `por el SAT, ${cifras.denuncias_n} denuncias presentadas.`,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es" className={mono.variable}>
      <body>
        <div className="pagina">
          <header className="folio">
            <Link href="/" className="marca">
              expediente abierto <span className="punto">·</span> méxico
            </Link>
            <nav className="indice" aria-label="Portal">
              <Link href="/">inicio</Link>
              <Link href="/denuncias/">casos</Link>
              <Link href="/datos/">datos</Link>
              <Link href="/replica/">réplica</Link>
            </nav>
            <span className="corte">corte de datos: {meta.corte}</span>
          </header>
          {children}
          <footer>
            <div>
              Cada dato con su fuente oficial.{" "}
              <Link href="/replica/">Aviso legal y derecho de réplica</Link>.
            </div>
            <div>Sin cookies, sin rastreadores.</div>
          </footer>
        </div>
      </body>
    </html>
  );
}
