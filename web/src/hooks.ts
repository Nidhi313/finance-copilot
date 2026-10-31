import { useQuery } from "@tanstack/react-query";
import { api, call, type Schemas } from "./api";

export const keys = {
  me: ["me"] as const,
  countries: ["countries"] as const,
  country: (code: string) => ["country", code] as const,
  categories: ["categories"] as const,
  accounts: (country?: string) => ["accounts", country ?? "all"] as const,
};

export function useMe() {
  return useQuery({ queryKey: keys.me, queryFn: () => call(api.GET("/v1/me")) });
}

export function useCountries() {
  return useQuery({ queryKey: keys.countries, queryFn: () => call(api.GET("/v1/countries")), staleTime: Infinity });
}

export function useCountry(code: string | null | undefined) {
  return useQuery({
    queryKey: keys.country(code ?? ""),
    queryFn: () => call(api.GET("/v1/countries/{code}", { params: { path: { code: code! } } })),
    enabled: !!code,
    staleTime: 5 * 60_000,
  });
}

export function useCategories() {
  return useQuery({ queryKey: keys.categories, queryFn: () => call(api.GET("/v1/categories")) });
}

export function useAccounts(country?: string) {
  return useQuery({
    queryKey: keys.accounts(country),
    queryFn: () => call(api.GET("/v1/accounts", { params: { query: { country } } })),
  });
}

/** The country currently selected in the switcher, with its context (pack or basic). */
export function useActiveCountry(): { code: string | null; ctx: Schemas["CountryContextOut"] | undefined; locale: string } {
  const me = useMe();
  const code = me.data?.active_country_code ?? null;
  const ctx = useCountry(code);
  return { code, ctx: ctx.data, locale: ctx.data?.locale ?? "en-AU" };
}

/** Format money in the locale of the user's own country that uses that currency
 * (so INR shows lakh grouping), falling back to the active country's locale. */
export function useLocaleForCurrency(): (currency: string) => string {
  const me = useMe();
  const countries = useCountries();
  const { locale } = useActiveCountry();
  const linked = new Set(me.data?.countries.map((c) => c.country_code));
  const map = new Map<string, string>();
  for (const c of countries.data ?? []) if (linked.has(c.code) && !map.has(c.currency)) map.set(c.currency, c.locale);
  return (currency: string) => map.get(currency) ?? locale;
}
