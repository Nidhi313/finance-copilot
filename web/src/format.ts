/** Money arrives from the API as decimal strings. Format with the country's locale,
 * so India shows 1,00,000 and Australia shows 100,000. */
export function money(value: string | number | null | undefined, currency: string, locale = "en-AU", opts: { sign?: boolean; decimals?: number } = {}): string {
  if (value === null || value === undefined || value === "") return "-";
  const n = typeof value === "number" ? value : Number(value);
  const decimals = opts.decimals ?? 2;
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      currencyDisplay: "narrowSymbol",
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
      signDisplay: opts.sign ? "exceptZero" : "auto",
    }).format(n);
  } catch {
    return `${currency} ${n.toFixed(decimals)}`;
  }
}

export function num(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === "") return 0;
  return typeof value === "number" ? value : Number(value);
}

export function shortDate(iso: string, locale = "en-AU"): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric" });
}

export function monthLabel(ym: string, locale = "en-AU"): string {
  const d = new Date(`${ym}-01T00:00:00`);
  return d.toLocaleDateString(locale, { month: "short", year: "2-digit" });
}

export function thisMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export const RELATIONSHIP_LABELS: Record<string, string> = {
  lives_here: "I live here",
  tax_resident: "Tax resident",
  citizen: "Citizen",
  holds_accounts: "I hold accounts here",
  sends_money_to: "I send money here",
};
