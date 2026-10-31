import { describe, expect, it } from "vitest";
import { parseCsvRows, sniffDelimiter } from "./csv";
import { money } from "./format";

describe("money", () => {
  it("uses Indian digit grouping for en-IN", () => {
    expect(money("250000", "INR", "en-IN", { decimals: 0 })).toBe("₹2,50,000");
  });
  it("uses standard grouping for en-AU", () => {
    expect(money("250000", "AUD", "en-AU", { decimals: 0 })).toBe("$250,000");
  });
  it("shows a dash for missing values", () => {
    expect(money(null, "AUD")).toBe("-");
  });
});

describe("csv preview", () => {
  it("detects semicolons and handles quoted commas", () => {
    const text = 'Date;Desc;Amount\n01/10/2026;"Shop, Ltd";-5,00\n';
    const d = sniffDelimiter(text);
    expect(d).toBe(";");
    expect(parseCsvRows(text, d)[1]).toEqual(["01/10/2026", "Shop, Ltd", "-5,00"]);
  });
});
