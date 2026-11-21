import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApp } from '../context'
import { Empty, ErrorBox, Guard, Loading } from '../ui'
import { fmtDate, num } from '../util'

function AskAi({ query }) {
  const { meta } = useApp()
  const [question, setQuestion] = useState('')
  const [state, setState] = useState({ loading: false, error: null, result: null })
  const on = meta?.ai_enabled
  const ask = async () => {
    setState({ loading: true, error: null, result: null })
    try { setState({ loading: false, error: null, result: await api.aiParts(query, question) }) }
    catch (error) { setState({ loading: false, error, result: null }) }
  }
  return (
    <section className="panel" style={{ marginBottom: 14 }}>
      <div className="panel-head"><h2>Ask about these results</h2>{!on && <span className="chip">AI is off</span>}</div>
      <div className="panel-body">
        <div className="searchbar" style={{ margin: 0 }}>
          <input className="input grow" disabled={!on} value={question} maxLength={500} onChange={(e) => setQuestion(e.target.value)}
                 placeholder="For example: which of these can I use tonight, and where is it?" aria-label="Question"
                 onKeyDown={(e) => e.key === 'Enter' && on && question.trim() && ask()} />
          <button className="btn primary" disabled={!on || !question.trim() || state.loading} onClick={ask}>Ask AI</button>
        </div>
        {!on && <p className="muted small" style={{ marginTop: 6 }}>Add your OpenAI key to the .env file and restart the backend to turn this on.</p>}
        {state.loading && <Loading text="Reading the stock rows" />}
        <ErrorBox error={state.error} />
        {state.result && (
          <div className="ai-box">
            <div className="answer">{state.result.answer}</div>
            {!state.result.citations.ok && <div className="callout" style={{ margin: '6px 0' }}>{state.result.citations.note}</div>}
            <div className="muted small">Based only on {state.result.records_sent.length} stock rows. Tags like [R1234] are Excel row numbers in the stores file. Information only.</div>
          </div>
        )}
      </div>
    </section>
  )
}

function PartCard({ p }) {
  return (
    <section className={`panel verdict ${p.tone}`}>
      <div className="head">
        <span className="pn">{p.part_no}</span>
        <span>{p.description}</span>
        <span className={`chip ${p.tone}`}>{p.label}</span>
      </div>
      <p className="muted small" style={{ marginTop: 4 }}>{p.why}</p>
      <div className="qtys">
        <div className="qty"><b>{num(p.line_usable)}</b><span>Usable at line store</span></div>
        <div className="qty"><b>{num(p.main_usable)}</b><span>Usable at main store</span></div>
        <div className="qty"><b>{num(p.other_owner_usable)}</b><span>Usable, other owners</span></div>
        <div className="qty"><b>{num(p.unserviceable)}</b><span>Unserviceable</span></div>
      </div>
      <details>
        <summary>Stock rows (showing {p.rows_shown} of {p.rows_total}{p.rows_hidden_by_filters ? `, ${p.rows_hidden_by_filters} hidden by filters` : ''})</summary>
        <div className="tablewrap">
          <table>
            <thead><tr><th>Row</th><th>Store</th><th>Location</th><th>Serial</th><th>Class</th><th className="num">Qty</th><th>Condition</th><th>Owner</th><th>Received</th></tr></thead>
            <tbody>
              {p.rows.map((r) => (
                <tr key={r.source_row}>
                  <td title="Excel row in Inventory_List.xlsx">{r.source_row}</td><td>{r.store}</td><td>{r.location}</td><td>{r.serial}</td>
                  <td>{r.mat_class}</td><td className="num">{num(r.qty)}</td>
                  <td>{r.cond || 'none'}{!r.usable && <> <span className="chip danger">Unserviceable</span></>}</td>
                  <td>{r.owner}{!r.own && <> <span className="chip caution">Not ours</span></>}</td><td>{r.rec_date ? fmtDate(r.rec_date) : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  )
}

export default function Parts({ initialQuery = '' }) {
  const [input, setInput] = useState(initialQuery)
  const [query, setQuery] = useState(initialQuery)
  const [stores, setStores] = useState(['SHJLINE', 'SHJMAIN'])
  const [ownOnly, setOwnOnly] = useState(false)
  const [includeUs, setIncludeUs] = useState(true)
  const [state, setState] = useState({ loading: false, error: null, data: null })

  useEffect(() => {
    if (!query) return
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    api.partsSearch(query, { stores, ownOnly, includeUnserviceable: includeUs }).then(
      (data) => alive && setState({ loading: false, error: null, data }),
      (error) => alive && setState({ loading: false, error, data: null }),
    )
    return () => { alive = false }
  }, [query, stores.join(','), ownOnly, includeUs]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggleStore = (s) => setStores(stores.includes(s) ? stores.filter((x) => x !== s) : [...stores, s])
  const { data } = state

  return (
    <div className="page">
      <div className="page-head">
        <h1>Parts finder</h1>
        <p>Search the spare parts list by part number, serial number or description. For each part you get a clear answer on where it can be used from.</p>
      </div>
      <form className="searchbar" onSubmit={(e) => { e.preventDefault(); setQuery(input.trim()) }}>
        <label className="field grow" style={{ flex: '1 1 320px' }}>
          <span>Part number, serial number or words</span>
          <input className="input" value={input} onChange={(e) => setInput(e.target.value)} placeholder="For example: brake assy, 1152682-3, thermocouple" autoFocus />
        </label>
        <button className="btn primary" type="submit" disabled={!input.trim()}>Search</button>
      </form>
      <div className="filters">
        <span>Show rows from:</span>
        {['SHJLINE', 'SHJMAIN'].map((s) => (
          <label key={s}><input type="checkbox" checked={stores.includes(s)} onChange={() => toggleStore(s)} /> {s}</label>
        ))}
        <label><input type="checkbox" checked={ownOnly} onChange={(e) => setOwnOnly(e.target.checked)} /> Only parts owned by Air Arabia</label>
        <label><input type="checkbox" checked={includeUs} onChange={(e) => setIncludeUs(e.target.checked)} /> Show unserviceable</label>
      </div>
      <ErrorBox error={state.error} />
      {state.loading && <Loading text="Searching" />}
      {!query && <Empty>Type a part number or a few words from the description to start.</Empty>}
      {data && query && (
        <>
          {data.parts.length === 0
            ? <Empty>No stock rows match “{data.query}”. Try fewer words, or part of the part number.</Empty>
            : (
              <>
                <p className="muted" style={{ marginBottom: 12 }}>
                  {data.parts_found} part number{data.parts_found === 1 ? '' : 's'} found
                  {data.parts_found > data.parts.length ? `, showing the first ${data.parts.length} (best availability first)` : ''}.
                  The answer for each part uses all its stock rows. The filters only change which rows are listed.
                  {data.truncated && ' Very many rows matched: add more words to narrow the search.'}
                </p>
                <AskAi query={query} />
                {data.parts.map((p) => <PartCard key={p.part_no} p={p} />)}
              </>
            )}
        </>
      )}
      <Guard />
    </div>
  )
}
