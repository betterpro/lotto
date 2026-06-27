import { createClient } from '@supabase/supabase-js'

let client = null

export function getSupabase() {
  if (client) return client
  const url = import.meta.env.VITE_SUPABASE_URL || ''
  const key = import.meta.env.VITE_SUPABASE_ANON_KEY || ''
  if (!url || !key) return null
  client = createClient(url, key, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  })
  return client
}

export async function resolveSupabaseConfig() {
  const fromEnv = {
    url: import.meta.env.VITE_SUPABASE_URL || '',
    anonKey: import.meta.env.VITE_SUPABASE_ANON_KEY || '',
  }
  if (fromEnv.url && fromEnv.anonKey) return fromEnv
  try {
    const res = await fetch('/api/auth/config')
    if (!res.ok) return fromEnv
    const cfg = await res.json()
    return {
      url: fromEnv.url || cfg.supabase_url || '',
      anonKey: fromEnv.anonKey || cfg.supabase_anon_key || '',
    }
  } catch {
    return fromEnv
  }
}

export async function initSupabaseClient() {
  const { url, anonKey } = await resolveSupabaseConfig()
  if (!url || !anonKey) return null
  client = createClient(url, anonKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  })
  return client
}
