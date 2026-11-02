/**
 * Sign-in. With VITE_AUTH_MODE=entra the app signs people in through Microsoft
 * Entra External ID (MSAL) and sends an access token with every API call. With
 * "dev" there is no sign-in and the API uses its local demo user.
 */
import {
  type AccountInfo,
  EventType,
  InteractionRequiredAuthError,
  PublicClientApplication,
} from "@azure/msal-browser";

const env = import.meta.env;
export const AUTH_MODE: "dev" | "entra" = env.VITE_AUTH_MODE === "entra" ? "entra" : "dev";
const subdomain = env.VITE_ENTRA_TENANT_SUBDOMAIN ?? "";
const tenantId = env.VITE_ENTRA_TENANT_ID ?? "";
export const API_SCOPES = env.VITE_ENTRA_API_SCOPE ? [env.VITE_ENTRA_API_SCOPE as string] : [];

export const msal: PublicClientApplication | null =
  AUTH_MODE === "entra"
    ? new PublicClientApplication({
        auth: {
          clientId: env.VITE_ENTRA_WEB_CLIENT_ID ?? "",
          // Naming the tenant by id makes MSAL load this exact tenant's sign-in metadata:
          // https://<subdomain>.ciamlogin.com/<tenant-id>/v2.0/.well-known/openid-configuration
          authority: `https://${subdomain}.ciamlogin.com/${tenantId}`,
          knownAuthorities: [`${subdomain}.ciamlogin.com`],
          redirectUri: window.location.origin,
          postLogoutRedirectUri: window.location.origin,
        },
        cache: { cacheLocation: "sessionStorage" },
      })
    : null;

export function configProblem(): string | null {
  if (AUTH_MODE !== "entra") return null;
  const missing = [
    ["VITE_ENTRA_TENANT_SUBDOMAIN", subdomain],
    ["VITE_ENTRA_TENANT_ID", tenantId],
    ["VITE_ENTRA_WEB_CLIENT_ID", env.VITE_ENTRA_WEB_CLIENT_ID],
    ["VITE_ENTRA_API_SCOPE", env.VITE_ENTRA_API_SCOPE],
  ].filter(([, v]) => !v).map(([k]) => k);
  return missing.length ? `Sign-in is switched on but web/.env.local is missing: ${missing.join(", ")}` : null;
}

/** Set up MSAL and finish a sign-in redirect if we are returning from one. */
export async function initAuth(): Promise<void> {
  if (!msal) return;
  await msal.initialize();
  msal.addEventCallback((event) => {
    if (event.eventType === EventType.LOGIN_SUCCESS && event.payload && "account" in event.payload) {
      msal.setActiveAccount(event.payload.account as AccountInfo);
    }
  });
  const result = await msal.handleRedirectPromise();
  if (result?.account) msal.setActiveAccount(result.account);
  else if (!msal.getActiveAccount() && msal.getAllAccounts().length) msal.setActiveAccount(msal.getAllAccounts()[0]);
}

export function currentAccount(): AccountInfo | null {
  return msal?.getActiveAccount() ?? null;
}

export function signIn(): Promise<void> {
  return msal ? msal.loginRedirect({ scopes: API_SCOPES }) : Promise.resolve();
}

export function signOut(): Promise<void> {
  return msal ? msal.logoutRedirect({ account: currentAccount() ?? undefined }) : Promise.resolve();
}

/** An access token for the API, refreshed silently; redirects to sign in if that fails. */
export async function getToken(): Promise<string | null> {
  if (!msal) return null;
  const account = currentAccount();
  if (!account) {
    await signIn();
    return null;
  }
  try {
    const result = await msal.acquireTokenSilent({ scopes: API_SCOPES, account });
    return result.accessToken;
  } catch (e) {
    if (e instanceof InteractionRequiredAuthError) {
      await msal.acquireTokenRedirect({ scopes: API_SCOPES, account });
      return null;
    }
    throw e;
  }
}
