import { useEffect, useState } from 'react'
import { api } from './api'
import { useApp } from './context'
import { SourceTag, StatusChip, WhyDeferral, ErrorBox, Loading } from './ui'
import { KIND, STATUS, deadlineLine, fmtDate, fmtDateTime, num } from './util'

/* ------------------------------------------------------------------ parts check inside a fault */
function PartsCheck({ woNumber }) {
  const [words, setWords] = useState('')
  const [method, setMethod] = useState('')
  const [result, setResult] = useState(null)
  const [state, setState] = useState({ loading: true, error: null })

  const [shown, setShown] = useState('')

  // If nothing matches, drop the last word and try again, so a long phrase still finds something.
  const search = async (q) => {
    setState({ loading: true, error: null })
    try {
      const tokens = q.trim().split(/\s+/).filter(Boolean)
      let res = null
      while (tokens.length) {
        res = await api.partsSearch(tokens.join(' '))
        if (res.parts.length) break
        tokens.pop()
      }
      setShown(tokens.join(' '))
      setResult(res)
      setState({ loading: false, error: null })
    } catch (error) {
      setState({ loading: false, error })
    }
  }

  // Load the suggested words once, when the panel opens.
  useEffect(() => {
    let alive = true
    api.keywords(woNumber).then(
      (k) => {
        if (!alive) return
        const text = k.keywords.join(' ')
        setWords(text); setMethod(k.method)
        if (text) search(text); else setState({ loading: false, error: null })
      },
      (error) => alive && setState({ loading: false, error }),
    )
    return () => { alive = false }
  }, [woNumber]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="why" style={{ marginTop: 8 }}>
      <p><b>Parts check.</b> {method === 'ai' ? 'Words suggested by AI.' : 'Words taken from the fault text.'} They are a suggestion only: change them if they are wrong.</p>
      <div className="searchbar" style={{ margin: '8px 0' }}>
        <input className="input grow" value={words} onChange={(e) => setWords(e.target.value)} aria-label="Search words"
               onKeyDown={(e) => e.key === 'Enter' && words.trim() && search(words)} />
        <button className="btn small primary" disabled={!words.trim()} onClick={() => search(words)}>Search parts</button>
      </div>
      <ErrorBox error={state.error} />
      {state.loading && <Loading text="Searching the parts list" />}
      {result && !state.loading && (
        result.parts.length === 0 ? <p>No stock rows match these words. Try a shorter word or the part name.</p> : (
          <>
            {shown !== words.trim() && <p className="muted small">Nothing matched all the words, so these results are for “{shown}”.</p>}
            {result.parts.slice(0, 5).map((p) => (
              <p key={p.part_no} style={{ margin: '4px 0' }}>
                <span className={`chip ${p.tone}`}>{p.label}</span>{' '}
                <b>{p.part_no}</b> {p.description}. Line store {num(p.line_usable)}, main store {num(p.main_usable)}.
              </p>
            ))}
            <p><a href={`#/parts/${encodeURIComponent(shown || words)}`}>See all {result.parts_found} part numbers in the Parts Finder</a></p>
          </>
        )
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ full work-order text */
function FullRecord({ woNumber }) {
  const [rec, setRec] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    let alive = true
    api.workOrder(woNumber).then((r) => alive && setRec(r), (e) => alive && setError(e))
    return () => { alive = false }
  }, [woNumber])
  return (
    <div className="why" style={{ marginTop: 8 }}>
      <ErrorBox error={error} />
      {!rec && !error && <Loading />}
      {rec && (
        <>
          <p><b>Description.</b></p><p className="quote">{rec.wo_description || 'Nothing recorded'}</p>
          <p><b>Work log.</b></p><p className="quote">{rec.wo_actions || 'Nothing recorded'}</p>
        </>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ one fault or deferral */
export function FaultItem({ item, onChanged }) {
  const [panel, setPanel] = useState(null) // 'parts' | 'record' | 'seen'
  const [note, setNote] = useState('')
  const [error, setError] = useState(null)
  const d = item.deferral
  const tone = d ? STATUS[d.status].tone : ''
  const flagged = d && ['OVERDUE', 'EXPIRES_TODAY', 'EXPIRES_SOON'].includes(d.status)
  const toggle = (name) => setPanel(panel === name ? null : name)

  const saveSeen = async () => {
    try {
      await api.ack(item.wo_number, note)
      setPanel(null); setNote(''); onChanged && onChanged()
    } catch (e) { setError(e) }
  }

  return (
    <div className={`item ${tone}`}>
      <div className="top">
        <span className="title">{item.title}</span>
        {d && <StatusChip status={d.status} />}
      </div>
      <div className="meta">
        <SourceTag source={item.source} /> {item.wo_type}, ATA {item.ata || 'not recorded'}, opened {fmtDate(item.date_opened)}.
        {d && <> {KIND[d.kind]}. {deadlineLine(d)}</>}
      </div>
      {item.ack && <div className="meta"><span className="chip brand">Seen</span> by {item.ack.actor} on {fmtDateTime(item.ack.ts)}{item.ack.note ? `: ${item.ack.note}` : ''}</div>}
      {d && <WhyDeferral item={item} />}
      <div className="actions">
        <button className="btn small" aria-expanded={panel === 'parts'} onClick={() => toggle('parts')}>Check parts</button>
        <button className="btn small" aria-expanded={panel === 'record'} onClick={() => toggle('record')}>Full record</button>
        {flagged && <button className="btn small" aria-expanded={panel === 'seen'} onClick={() => toggle('seen')}>Mark as seen</button>}
      </div>
      {panel === 'parts' && <PartsCheck woNumber={item.wo_number} />}
      {panel === 'record' && <FullRecord woNumber={item.wo_number} />}
      {panel === 'seen' && (
        <div className="why" style={{ marginTop: 8 }}>
          <p>Record that you have seen this flag. The item stays open: only the licensed engineer can act on it.</p>
          <div className="searchbar" style={{ margin: '8px 0 0' }}>
            <input className="input grow" placeholder="Note (optional), for example: checked with MCC" value={note} maxLength={500}
                   onChange={(e) => setNote(e.target.value)} aria-label="Note" />
            <button className="btn small primary" onClick={saveSeen}>Save</button>
          </div>
          <ErrorBox error={error} />
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ AI summary */
function AiSummary({ reg }) {
  const { meta, asOf } = useApp()
  const [state, setState] = useState({ loading: false, error: null, result: null })
  const [question, setQuestion] = useState('')
  const ask = async () => {
    setState({ loading: true, error: null, result: null })
    try {
      setState({ loading: false, error: null, result: await api.aiAircraft(reg, question.trim() || null, asOf || null) })
    } catch (error) { setState({ loading: false, error, result: null }) }
  }
  const on = meta?.ai_enabled
  return (
    <div className="section">
      <div className="searchbar" style={{ margin: 0 }}>
        <input className="input grow" placeholder="Ask about this aircraft (optional)" value={question} disabled={!on}
               maxLength={500} onChange={(e) => setQuestion(e.target.value)} aria-label="Question about this aircraft"
               onKeyDown={(e) => e.key === 'Enter' && on && ask()} />
        <button className="btn small primary" disabled={!on || state.loading} onClick={ask}
                title={on ? '' : 'Add OPENAI_API_KEY to the .env file and restart the backend'}>
          {question.trim() ? 'Ask AI' : 'Summarise with AI'}
        </button>
      </div>
      {!on && <p className="muted small" style={{ marginTop: 6 }}>AI is off. Add your OpenAI key to the .env file to turn it on. Everything else works without it.</p>}
      {state.loading && <Loading text="Reading the records" />}
      <ErrorBox error={state.error} />
      {state.result && (
        <div className="ai-box">
          <div className="answer">{state.result.answer}</div>
          {!state.result.citations.ok && <div className="callout" style={{ margin: '6px 0' }}>{state.result.citations.note}</div>}
          <div className="muted small">
            Written by AI from {state.result.records_sent.length} records. Tags like [WO123] point to the records. Information only.
          </div>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ the card */
export default function AircraftCard({ detail, defaultOpen = false, onChanged }) {
  const [open, setOpen] = useState(defaultOpen)
  const c = detail.counts
  const av = detail.aviatar
  const dated = detail.deferrals.filter((i) => i.deferral.expires_on)
  const undated = detail.deferrals.filter((i) => !i.deferral.expires_on)
  return (
    <section className="panel" aria-label={`Aircraft ${detail.aircraft_reg}`}>
      <button className="panel-head ac-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="reg">{detail.aircraft_reg}</span>
        <span className="chip">{c.open_faults} open</span>
        {c.expires_today > 0 && <span className="chip danger">{c.expires_today} due today</span>}
        {c.overdue > 0 && <span className="chip danger">{c.overdue} past deadline</span>}
        {c.expires_soon > 0 && <span className="chip caution">{c.expires_soon} due soon</span>}
        {c.pha_open > 0 && <span className="chip brand">{c.pha_open} predictive</span>}
        <span className="caret">{open ? 'Hide' : 'Show'}</span>
      </button>

      {open && (
        <>
          <AiSummary reg={detail.aircraft_reg} />

          <div className="section">
            <h3>Deferred items that can wait <span className="chip">{dated.length} with a deadline</span></h3>
            {detail.deferrals.length === 0 && <p className="muted small">No deferred items found in the open work orders.</p>}
            {detail.deferrals.length > 0 && dated.length === 0 && <p className="muted small">None of the deferred items has a deadline that could be worked out.</p>}
            {dated.map((i) => <FaultItem key={i.wo_number} item={i} onChanged={onChanged} />)}
            {undated.length > 0 && (
              <details>
                <summary>{undated.length} deferred item{undated.length === 1 ? '' : 's'} with no calculated date</summary>
                <p className="muted small" style={{ margin: '6px 0 8px' }}>
                  The record does not give a time limit in days, or the limit is in flight cycles or hours. Check the source for each.
                </p>
                {undated.map((i) => <FaultItem key={i.wo_number} item={i} onChanged={onChanged} />)}
              </details>
            )}
          </div>

          <div className="section">
            <h3>Other open faults <span className="chip">{detail.other_faults.length}</span></h3>
            {detail.other_faults.length === 0 && <p className="muted small">None.</p>}
            {detail.other_faults.map((i) => <FaultItem key={i.wo_number} item={i} onChanged={onChanged} />)}
          </div>

          <div className="section">
            <h3>Predictive cases <span className="chip brand">Read only</span></h3>
            {detail.pha.length === 0 && <p className="muted small">No open predictive cases.</p>}
            {detail.pha.map((p) => (
              <div key={p.source_row} className={`item ${p.max_severity === 'Alert' ? 'caution' : ''}`}>
                <div className="top"><span className="title">{p.title}</span><span className="chip caution">{p.max_severity}</span></div>
                <div className="meta">
                  ATA {p.ata}, impact {p.impact}, classification {p.classification}. Opened {fmtDateTime(p.opened)}.{' '}
                  {p.case_link && <SourceTag source={{ url: p.case_link }} label="Open case in AVIATAR" />}
                </div>
                <div className="meta">An early warning from flight data, not a confirmed fault. This tool cannot change a case.</div>
              </div>
            ))}
          </div>

          <div className="section">
            <h3>Aircraft messages (AVIATAR), {fmtDate(av.window_from)} to {fmtDate(av.window_to)} <span className="chip">{av.total_messages} total</span></h3>

            {av.groups.length === 0 && <p className="muted small">No high or medium priority messages from this aircraft in this period.</p>}
            {av.groups.length > 0 && (
              <div className="tablewrap">
                <table>
                  <thead><tr><th>Message from aircraft</th><th>Priority</th><th title="System chapter number">ATA (system)</th><th className="num" title="How many times this message was sent">Times sent</th><th className="num" title="On how many different flights">Flights affected</th><th>Last seen</th></tr></thead>
                  <tbody>
                    {av.groups.map((g) => (
                      <tr key={g.tag}>
                        <td>{g.message}</td>
                        <td><span className={`chip ${g.prio === 'HIGH' ? 'danger' : 'caution'}`}>{g.prio === 'HIGH' ? 'High' : 'Medium'}</span></td>
                        <td>{g.ata}</td><td className="num">{g.n}</td><td className="num">{g.flights}</td><td>{fmtDateTime(g.last_seen)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="muted small" style={{ margin: '6px 0 4px' }}>Shows the 12 most serious groups. A message is a symptom to check, not a confirmed fault. Read only. Source: AVIATAR faults export.</p>
          </div>

          <div className="section">
            <h3>Recent work logged <span className="chip">Derived</span></h3>
            <p className="muted small" style={{ marginBottom: 8 }}>
              No handover records were provided, so these are work-log entries from the last two days. They are not formal handover notes.
            </p>
            {detail.notes.length === 0 && <p className="muted small">No entries in the last two days.</p>}
            {detail.notes.map((n, i) => (
              <div key={i} className="item">
                <div className="title">{n.text}</div>
                <div className="meta">{fmtDate(n.date)}, {n.wo_type}. <SourceTag source={n.source} /></div>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
