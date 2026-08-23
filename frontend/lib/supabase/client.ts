import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { getSupabasePublicConfig } from "./config";

let browserClient: SupabaseClient | null = null;
const TAB_ID_STORAGE_KEY = "parksmart:supabase-auth-tab-id";

function tabScopedAuthStorageKey(): string {
  const existing = window.sessionStorage.getItem(TAB_ID_STORAGE_KEY);
  if (existing) return `parksmart-auth:${existing}`;

  const tabId = window.crypto.randomUUID();
  window.sessionStorage.setItem(TAB_ID_STORAGE_KEY, tabId);
  return `parksmart-auth:${tabId}`;
}

export function createBrowserSupabaseClient(): SupabaseClient {
  if (browserClient) return browserClient;

  const { url, publishableKey } = getSupabasePublicConfig();
  browserClient = createClient(url, publishableKey, {
    auth: {
      autoRefreshToken: true,
      detectSessionInUrl: true,
      persistSession: true,
      storage: window.sessionStorage,
      storageKey: tabScopedAuthStorageKey(),
    },
  });
  return browserClient;
}
