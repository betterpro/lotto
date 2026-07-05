// @supabase/supabase-js is heavy (~120 KB) and only web sign-in needs it, so it
// is dynamically imported here — this keeps it out of the main bundle entirely
// and Telegram sessions never download or parse it.

let client = null

const CONFIG_CACHE_KEY = 'lottoo_auth_config'

function readCachedConfig() {
  try {
    const raw = localStorage.getItem(CONFIG_CACHE_KEY)
    if (!raw) return null
    const cfg = JSON.parse(raw)
    return cfg?.url && cfg?.anonKey ? cfg : null
  } catch {
    return null
  }
}

export async function resolveSupabaseConfig() {
  const fromEnv = {
    url: import.meta.env.VITE_SUPABASE_URL || '',
    anonKey: import.meta.env.VITE_SUPABASE_ANON_KEY || '',
  }
  if (fromEnv.url && fromEnv.anonKey) return fromEnv

  // Cached from a previous load — avoids the /api/auth/config round trip.
  const cached = readCachedConfig()
  if (cached) return cached

  try {
    const res = await fetch('/api/auth/config')
    if (!res.ok) return fromEnv
    const cfg = await res.json()
    const resolved = {
      url: fromEnv.url || cfg.supabase_url || '',
      anonKey: fromEnv.anonKey || cfg.supabase_anon_key || '',
    }
    if (resolved.url && resolved.anonKey) {
      try { localStorage.setItem(CONFIG_CACHE_KEY, JSON.stringify(resolved)) } catch { /* ignore */ }
    }
    return resolved
  } catch {
    return fromEnv
  }
}

export async function initSupabaseClient() {
  if (client) return client
  const { url, anonKey } = await resolveSupabaseConfig()
  if (!url || !anonKey) return null
  const { createClient } = await import('@supabase/supabase-js')
  client = createClient(url, anonKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  })
  return client
}
