// All calls to the Python backend. The engineer's name is sent with every call so the audit log can record it.
const BASE = import.meta.env.VITE_API_URL || ''

export const getUser = () => localStorage.getItem('lea_user') || ''
export const setUser = (name) => localStorage.setItem('lea_user', name)

async function request(path, options = {}) {
  const user = getUser().replace(/[^\x20-\x7E]/g, '')
  let res
  try {
    res = await fetch(`${BASE}/api${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', 'X-User': user, ...(options.headers || {}) },
    })
  } catch {
    throw new Error('Cannot reach the backend. Start it with: uvicorn app.main:app --port 8000')
  }
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail || detail } catch { /* keep status text */ }
    throw new Error(detail)
  }
  return res.json()
}

const qs = (params) => {
  const p = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '') return
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x))
    else p.append(k, v)
  })
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const api = {
  meta: (asOf) => request(`/meta${qs({ as_of: asOf })}`),
  brief: (asOf) => request(`/brief${qs({ as_of: asOf })}`),
  aircraftList: (asOf) => request(`/aircraft${qs({ as_of: asOf })}`),
  aircraft: (reg, asOf) => request(`/aircraft/${encodeURIComponent(reg)}${qs({ as_of: asOf })}`),
  workOrder: (wo) => request(`/workorders/${wo}`),
  amm: (wo) => request(`/faults/${wo}/amm`),
  keywords: (wo) => request(`/faults/${wo}/keywords`),
  partsSearch: (q, opts = {}) => request(`/parts/search${qs({ q, stores: opts.stores, own_only: opts.ownOnly, include_unserviceable: opts.includeUnserviceable })}`),
  toolsSearch: (q, where, asOf) => request(`/tools/search${qs({ q, where, as_of: asOf })}`),
  roster: (shiftDate) => request(`/roster${qs({ shift_date: shiftDate })}`),
  rosterAuto: (shiftDate) => request(`/roster/auto${qs({ shift_date: shiftDate })}`, { method: 'POST' }),
  rosterSet: (aircraft_reg, engineer, shift_date) =>
    request('/roster', { method: 'PUT', body: JSON.stringify({ aircraft_reg, engineer, shift_date }) }),
  markDone: (wo_number, note, as_of) =>
    request('/workorders/done', { method: 'POST', body: JSON.stringify({ wo_number, note, as_of }) }),
  undoDone: (wo) => request(`/workorders/${wo}/done`, { method: 'DELETE' }),
  ack: (wo_number, note) => request('/flags/ack', { method: 'POST', body: JSON.stringify({ wo_number, note }) }),
  aiAircraft: (aircraft_reg, question, as_of) =>
    request('/ai/aircraft', { method: 'POST', body: JSON.stringify({ aircraft_reg, question, as_of }) }),
  aiParts: (query, question) => request('/ai/parts', { method: 'POST', body: JSON.stringify({ query, question }) }),
  audit: (limit = 200) => request(`/audit?limit=${limit}`),
}
