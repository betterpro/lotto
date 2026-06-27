import { initSupabaseClient } from './supabase.js'
import { setAccessToken } from './api.js'

let ready = null

export function initAuthSession() {
  if (!ready) {
    ready = (async () => {
      const supabase = await initSupabaseClient()
      if (!supabase) return null
      const { data: { session } } = await supabase.auth.getSession()
      setAccessToken(session?.access_token ?? null)
      supabase.auth.onAuthStateChange((_event, nextSession) => {
        setAccessToken(nextSession?.access_token ?? null)
      })
      return supabase
    })()
  }
  return ready
}

export async function signOutEverywhere() {
  const supabase = await initAuthSession()
  if (supabase) await supabase.auth.signOut()
  setAccessToken(null)
}
