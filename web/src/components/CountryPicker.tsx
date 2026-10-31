import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api";
import { RELATIONSHIP_LABELS } from "../format";
import { keys, useCountries } from "../hooks";
import { ErrorNote, Field } from "./ui";

type Relationship = "tax_resident" | "citizen" | "lives_here" | "holds_accounts" | "sends_money_to";

/** Add any country in the world to your profile, with your relationship to it. */
export function AddCountry({ exclude = [], onDone }: { exclude?: string[]; onDone?: () => void }) {
  const countries = useCountries();
  const qc = useQueryClient();
  const [code, setCode] = useState("");
  const [rels, setRels] = useState<Relationship[]>(["lives_here"]);
  const add = useMutation({
    mutationFn: () => call(api.PUT("/v1/me/countries/{code}", { params: { path: { code } }, body: { relationships: rels } })),
    onSuccess: (data) => {
      qc.setQueryData(keys.me, data);
      setCode("");
      onDone?.();
    },
  });
  const options = (countries.data ?? []).filter((c) => !exclude.includes(c.code));
  const toggle = (r: Relationship) => setRels((cur) => (cur.includes(r) ? cur.filter((x) => x !== r) : [...cur, r]));
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        if (code) add.mutate();
      }}
    >
      <div className="form">
        <Field label="Country">
          <select value={code} onChange={(e) => setCode(e.target.value)} required>
            <option value="">Choose a country…</option>
            {options.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name} ({c.currency}){c.has_pack ? "" : " · basic support"}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div className="checks" role="group" aria-label="Your relationship to this country">
        {(Object.keys(RELATIONSHIP_LABELS) as Relationship[]).map((r) => (
          <label key={r}>
            <input type="checkbox" checked={rels.includes(r)} onChange={() => toggle(r)} />
            {RELATIONSHIP_LABELS[r]}
          </label>
        ))}
      </div>
      <ErrorNote error={add.error} />
      <div>
        <button className="btn" disabled={!code || add.isPending}>Add country</button>
      </div>
    </form>
  );
}
