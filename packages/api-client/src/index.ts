/**
 * Typed client for the Finance Copilot REST API, generated from FastAPI's
 * OpenAPI spec. Shared by the web app now and a mobile app later.
 *
 * Regenerate after any API change:
 *   (cd api && python -m app.openapi > ../packages/api-client/openapi.json)
 *   npm run gen:api
 */
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type { paths };

export function createApiClient(baseUrl: string, getToken?: () => Promise<string | null>) {
  const client = createClient<paths>({ baseUrl });
  if (getToken) {
    client.use({
      async onRequest({ request }) {
        const token = await getToken();
        if (token) request.headers.set("Authorization", `Bearer ${token}`);
        return request;
      },
    });
  }
  return client;
}

export type ApiClient = ReturnType<typeof createApiClient>;
