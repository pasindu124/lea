import { useState } from 'react'
import { api } from '../api'
import { useApp } from '../context'
import { ErrorBox, Guard, Loading } from '../ui'
import { fmtDate, useAsync } from '../util'

export default function Shift() {
  const { asOf, meta } = useApp()
  const roster = useAsync(() => api.roster(asOf || null), [asOf])
  const list = useAsync(() => api.aircraftList(asOf || null), [asOf])
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [add, setAdd] = useState({ reg: '', engineer: '' })

  const run = async (fn) => {
    setBusy(true); setError(null)
    try { await fn(); roster.reload() } catch (e) { setError(e) } finally { setBusy(false) }
  }
  const engineers = roster.data?.engineers || meta?.engineers || []
  const assigned = roster.data?.assignments || {}
  const info = Object.fromEntries((list.data || []).map((a) => [a.aircraft_reg, a]))
  const rows = Object.entries(assigned).sort((a, b) => (info[b[0]]?.score || 0) - (info[a[0]]?.score || 0))
  const free = (list.data || []).filter((a) => !(a.aircraft_reg in assigned))

  return (
    <div className="page">
      <div className="page-head">
        <h1>Shift setup</h1>
        <p>Choose which aircraft each engineer looks after tonight. Every change is written to the audit log.</p>
      </div>
      <div className="callout info">
        Planning's real roster is not in the data pack, so this is a placeholder. “Suggest a split” puts the most urgent aircraft first
        and spreads them evenly. Aircraft with a deadline today or soon are always included.
      </div>
      <ErrorBox error={error || roster.error || list.error} />
      {(roster.loading && !roster.data) && <Loading />}
      {roster.data && (
        <>
          <div className="row" style={{ marginBottom: 12 }}>
            <button className="btn primary" disabled={busy} onClick={() => run(() => api.rosterAuto(asOf || null))}>Suggest a split</button>
            <span className="muted">Shift date {fmtDate(roster.data.shift_date)}. {rows.length} aircraft.</span>
          </div>
          <div className="panel tablewrap">
            <table>
              <thead><tr><th>Aircraft</th><th>Open items</th><th>Needs attention</th><th>Engineer</th><th /></tr></thead>
              <tbody>
                {rows.length === 0 && <tr><td colSpan="5" className="muted">No aircraft yet. Suggest a split, or add aircraft below.</td></tr>}
                {rows.map(([reg, eng]) => {
                  const a = info[reg]
                  return (
                    <tr key={reg}>
                      <td><b style={{ fontFamily: 'var(--font-display)', fontSize: 18 }}>{reg}</b></td>
                      <td>{a ? a.open_faults : 0}</td>
                      <td>
                        {a?.expires_today > 0 && <span className="chip danger">{a.expires_today} due today</span>}{' '}
                        {a?.overdue > 0 && <span className="chip danger">{a.overdue} past deadline</span>}{' '}
                        {a?.expires_soon > 0 && <span className="chip caution">{a.expires_soon} due soon</span>}
                      </td>
                      <td>
                        <select className="select" value={eng} disabled={busy} aria-label={`Engineer for ${reg}`}
                                onChange={(e) => run(() => api.rosterSet(reg, e.target.value, asOf || null))}>
                          {engineers.map((n) => <option key={n}>{n}</option>)}
                        </select>
                      </td>
                      <td><button className="btn small" disabled={busy} onClick={() => run(() => api.rosterSet(reg, null, asOf || null))}>Remove</button></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <h2 style={{ margin: '22px 0 8px' }}>Add an aircraft</h2>
          <div className="searchbar">
            <label className="field"><span>Aircraft</span>
              <select className="select" value={add.reg} onChange={(e) => setAdd({ ...add, reg: e.target.value })}>
                <option value="">Choose</option>
                {free.map((a) => <option key={a.aircraft_reg} value={a.aircraft_reg}>{a.aircraft_reg} ({a.open_faults} open)</option>)}
              </select>
            </label>
            <label className="field"><span>Engineer</span>
              <select className="select" value={add.engineer} onChange={(e) => setAdd({ ...add, engineer: e.target.value })}>
                <option value="">Choose</option>{engineers.map((n) => <option key={n}>{n}</option>)}
              </select>
            </label>
            <button className="btn" disabled={busy || !add.reg || !add.engineer}
                    onClick={() => run(async () => { await api.rosterSet(add.reg, add.engineer, asOf || null); setAdd({ reg: '', engineer: '' }) })}>Add to shift</button>
          </div>
          <p><a href="#/brief">Open the shift brief</a></p>
        </>
      )}
      <Guard />
    </div>
  )
}
