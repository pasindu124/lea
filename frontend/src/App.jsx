import { useEffect, useState } from 'react'
import { api, getUser, setUser } from './api'
import { AppContext } from './context'
import Aircraft from './pages/Aircraft'
import Audit from './pages/Audit'
import Brief from './pages/Brief'
import Parts from './pages/Parts'
import Shift from './pages/Shift'
import Tools from './pages/Tools'
import { fmtDate, useHash } from './util'

const NAV = [
  ['brief', 'Shift brief'], ['aircraft', 'Aircraft'], ['parts', 'Parts finder'],
  ['tools', 'Tools'], ['shift', 'Shift setup'], ['audit', 'Audit log'],
]

function Assumptions({ meta, onClose }) {
  return (
    <div className="assumptions" role="dialog" aria-modal="true" aria-label="Assumptions" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}>
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 10 }}>
          <h2>What this app assumes</h2>
          <button className="btn small" onClick={onClose}>Close</button>
        </div>
        <p className="muted" style={{ marginBottom: 12 }}>These are guesses the team made because the information was not in the data pack. Confirm them with Air Arabia before real use.</p>
        <ul>{meta.assumptions.map((a) => <li key={a.id}>{a.text}</li>)}</ul>
        {meta.load_summary && (
          <>
            <h3 style={{ margin: '16px 0 6px' }}>Data loaded</h3>
            <p className="muted small">{meta.load_summary.loaded_at}</p>
            <ul className="small">{Object.entries(meta.load_summary.counts).map(([k, v]) => <li key={k}>{k.replace('_', ' ')}: {Number(v).toLocaleString('en-GB')} rows</li>)}</ul>
          </>
        )}
      </div>
    </div>
  )
}

export default function App() {
  const hash = useHash()
  const [asOf, setAsOf] = useState('')
  const [user, setUserState] = useState(getUser())
  const [meta, setMeta] = useState(null)
  const [metaError, setMetaError] = useState(null)
  const [showAssumptions, setShowAssumptions] = useState(false)

  useEffect(() => {
    let alive = true
    api.meta(asOf || null).then((m) => alive && (setMeta(m), setMetaError(null)), (e) => alive && setMetaError(e))
    return () => { alive = false }
  }, [asOf])

  const [page, ...rest] = hash.split('/')
  const param = decodeURIComponent(rest.join('/'))

  let view
  switch (page) {
    case 'aircraft': view = <Aircraft selected={param} />; break
    case 'parts': view = <Parts key={param} initialQuery={param} />; break
    case 'tools': view = <Tools />; break
    case 'shift': view = <Shift />; break
    case 'audit': view = <Audit />; break
    default: view = <Brief />
  }

  return (
    <AppContext.Provider value={{ asOf, meta, user }}>
      <div className="shell">
        <aside className="rail">
          <div className="brand"><b>Line Engineer Agent</b><span>Sharjah night shift · live demo</span></div>
          <nav className="nav" aria-label="Main">
            {NAV.map(([id, label]) => (
              <a key={id} href={`#/${id}`} aria-current={(page || 'brief') === id ? 'page' : undefined}>{label}</a>
            ))}
          </nav>
          <div className="rail-foot">Read only. Never signs, defers or releases.</div>
        </aside>
        <div className="main">
          <div className="topbar">
            <span>
              {meta
                ? <>Data as of <b>{fmtDate(meta.as_of)}</b> <span className="muted">({meta.as_of_source})</span></>
                : metaError ? <span style={{ color: 'var(--danger)' }}>{metaError.message}</span> : 'Loading'}
            </span>
            <label>Change date <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} aria-label="Change the as-of date" /></label>
            {asOf && <button className="btn quiet small" onClick={() => setAsOf('')}>Use newest data</button>}
            <span className="grow" />
            {meta && <span className={`chip ${meta.ai_enabled ? 'ok' : ''}`} title={meta.ai_enabled ? `Model ${meta.ai_model}` : 'Add OPENAI_API_KEY to turn AI on'}>{meta.ai_enabled ? 'AI on' : 'AI off'}</span>}
            <label>Your name <input type="text" value={user} placeholder="For the audit log" maxLength={40}
                   onChange={(e) => { setUserState(e.target.value); setUser(e.target.value) }} /></label>
            {meta && <button className="btn small" onClick={() => setShowAssumptions(true)}>Assumptions ({meta.assumptions.length})</button>}
          </div>
          {view}
        </div>
      </div>
      {showAssumptions && meta && <Assumptions meta={meta} onClose={() => setShowAssumptions(false)} />}
    </AppContext.Provider>
  )
}
