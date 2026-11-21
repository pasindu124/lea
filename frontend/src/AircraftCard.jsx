import { useEffect, useState } from 'react'
import { api } from './api'
import AmmPanel from './AmmPanel'
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
          <p className="muted small">
            Source: {rec.source.file}, row {rec.source.row}. State: {rec.wo_state}
            {rec.date_closed ? `, closed ${fmtDate(rec.date_closed)}` : ''}.
            {rec.completion && ` Marked as done in this app by ${rec.completion.completed_by} on ${fmtDateTime(rec.completion.completed_at)}; the last work-log entry is their note.`}
            {rec.closed_by_cutoff && ` Treated as closed: deadline before ${fmtDate(rec.cutoff_date)} (see Assumptions).`}
          </p>
        </>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ one recent work-log entry */
function NoteItem({ note: n }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="item">
      <div className="title">{n.fault || n.text}</div>
      {n.fault && <div className="meta"><b>Work done:</b> {n.text}</div>}
      <div className="meta">
        {fmtDate(n.date)}, {n.wo_type}{n.done_by ? `, marked done by ${n.done_by}` : ''}. <SourceTag source={n.source} />
        {n.wo_state === 'Closed' && !n.done_by && <> <span className="chip">Closed</span></>}
      </div>
      {n.has_amm_ref && (
        <div className="actions">
          <button className="btn small" aria-expanded={open} onClick={() => setOpen(!open)}>AMM details: parts and tools</button>
        </div>
      )}
      {open && n.has_amm_ref && <AmmPanel woNumber={n.wo_number} />}
    </div>
  )
}

/* ------------------------------------------------------------------ one fault or deferral */
export function FaultItem({ item, onChanged }) {
  const [panel, setPanel] = useState(null) // 'amm' | 'parts' | 'record' | 'done'
  const [error, setError] = useState(null)
  const d = item.deferral
  const tone = d ? STATUS[d.status].tone : ''
  const toggle = (name) => setPanel(panel === name ? null : name)

  const { asOf } = useApp()
  const [doneNote, setDoneNote] = useState('')
  const saveDone = async () => {
    try {
      await api.markDone(item.wo_number, doneNote.trim(), asOf || null)
      setPanel(null); setDoneNote(''); onChanged && onChanged()
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
      {d && <WhyDeferral item={item} />}
      <div className="actions">
        {item.has_amm_ref && <button className="btn small" aria-expanded={panel === 'amm'} onClick={() => toggle('amm')}>Parts used (AMM)</button>}
        <button className="btn small" aria-expanded={panel === 'parts'} onClick={() => toggle('parts')}>Check parts</button>
        <button className="btn small" aria-expanded={panel === 'record'} onClick={() => toggle('record')}>Full record</button>
        <button className="btn small" aria-expanded={panel === 'done'} onClick={() => toggle('done')}>Mark as done</button>
      </div>
      {panel === 'done' && (
        <div className="why" style={{ marginTop: 8 }}>
          <p>Write what was done, as you would in the work log. The item then closes and the note appears under Recent work.</p>
          <textarea className="input" rows={3} style={{ width: '100%', margin: '8px 0' }} maxLength={2000} aria-label="Work done"
                    placeholder="For example: placards #506, #513, #517 installed IAW AMM 11-00-00-400-021-A. Checked OK."
                    value={doneNote} onChange={(e) => setDoneNote(e.target.value)} />
          <button className="btn small primary" disabled={doneNote.trim().length < 3} onClick={saveDone}>Save and close</button>
          <ErrorBox error={error} />
        </div>
      )}
      {panel === 'amm' && item.has_amm_ref && <AmmPanel woNumber={item.wo_number} />}
      {panel === 'parts' && <PartsCheck woNumber={item.wo_number} />}
      {panel === 'record' && <FullRecord woNumber={item.wo_number} />}
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
function Pane({ title, hint, children }) {
  return (
    <div className="pane">
      <div className="pane-head"><h3>{title}</h3>{hint && <p className="muted small">{hint}</p>}</div>
      {children}
    </div>
  )
}

export default function AircraftCard({ detail, defaultOpen = false, onChanged }) {
  const [open, setOpen] = useState(defaultOpen)
  const c = detail.counts
  const av = detail.aviatar
  const dated = detail.deferrals.filter((i) => i.deferral.expires_on)
  const undated = detail.deferrals.filter((i) => !i.deferral.expires_on)
  const flaggedN = c.expires_today + c.overdue + c.expires_soon

  // One section is shown at a time. Tone on a tab is status only.
  const sections = [
    { id: 'defer', label: 'Can wait', count: detail.deferrals.length, tone: flaggedN ? 'danger' : '' },
    { id: 'faults', label: 'Open faults', count: detail.other_faults.length, tone: '' },
    { id: 'pha', label: 'Predictive', count: detail.pha.length, tone: '' },
    { id: 'msgs', label: 'Aircraft messages', count: av.groups.length, tone: '' },
    { id: 'work', label: 'Recent work', count: detail.notes.length, tone: '' },
  ]
  const storeKey = `lea.tab.${detail.aircraft_reg}`
  const [tab, setTabState] = useState(() => {
    const saved = localStorage.getItem(storeKey)
    if (sections.some((x) => x.id === saved)) return saved
    return detail.deferrals.length ? 'defer' : detail.other_faults.length ? 'faults' : 'defer'
  })
  const setTab = (id) => { setTabState(id); localStorage.setItem(storeKey, id) }
  const urgent = detail.deferrals.filter((i) => ['OVERDUE', 'EXPIRES_TODAY', 'EXPIRES_SOON'].includes(i.deferral.status))
  const onKey = (e) => {
    const k = { ArrowRight: 1, ArrowLeft: -1 }[e.key]
    if (!k) return
    const i = sections.findIndex((x) => x.id === tab)
    setTab(sections[(i + k + sections.length) % sections.length].id)
  }

  return (
    <section className="panel ac" aria-label={`Aircraft ${detail.aircraft_reg}`}>
      <button className="panel-head ac-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="reg">{detail.aircraft_reg}</span>
        <span className="ac-stats">
          <span className="chip">{c.open_faults} open</span>
          {c.expires_today > 0 && <span className="chip danger">{c.expires_today} due today</span>}
          {c.overdue > 0 && <span className="chip danger">{c.overdue} past deadline</span>}
          {c.expires_soon > 0 && <span className="chip caution">{c.expires_soon} due soon</span>}
          {c.pha_open > 0 && <span className="chip brand">{c.pha_open} predictive</span>}
        </span>
        <span className="caret">{open ? 'Hide' : 'Show'}</span>
      </button>

      {open && (
        <>
          <AiSummary reg={detail.aircraft_reg} />

          {urgent.length > 0 && (
            <div className={`urgent ${urgent.some((i) => i.deferral.status !== 'EXPIRES_SOON') ? 'danger' : 'caution'}`} role="region" aria-label="Needs attention">
              <b>Needs attention ({urgent.length})</b>
              <ul>
                {urgent.slice(0, 3).map((i) => (
                  <li key={i.wo_number}>
                    <StatusChip status={i.deferral.status} />
                    <span className="u-title">{i.title}</span>
                    <span className="muted small">{deadlineLine(i.deferral)}</span>
                  </li>
                ))}
              </ul>
              <button className="btn small" onClick={() => setTab('defer')}>
                {urgent.length > 3 ? `See all ${urgent.length} under Can wait` : 'See details under Can wait'}
              </button>
            </div>
          )}

          <div className="seg" role="tablist" aria-label="Brief sections" onKeyDown={onKey}>
            {sections.map((x) => (
              <button key={x.id} role="tab" id={`tab-${detail.aircraft_reg}-${x.id}`} aria-selected={tab === x.id}
                      tabIndex={tab === x.id ? 0 : -1} onClick={() => setTab(x.id)}>
                {x.label}
                <span className={`chip ${x.tone}`}>{x.count}</span>
              </button>
            ))}
          </div>

          <div className="pane-wrap" role="tabpanel" aria-labelledby={`tab-${detail.aircraft_reg}-${tab}`}>
            {tab === 'defer' && (
              <Pane title="Deferred items that can wait" hint={`${dated.length} with a calculated deadline, most urgent first.`}>
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
              </Pane>
            )}

            {tab === 'faults' && (
              <Pane title="Other open faults">
                {detail.other_faults.length === 0 && <p className="muted small">None.</p>}
                {detail.other_faults.map((i) => <FaultItem key={i.wo_number} item={i} onChanged={onChanged} />)}
              </Pane>
            )}

            {tab === 'pha' && (
              <Pane title="Predictive cases" hint="Early warnings from flight data, not confirmed faults. Read only.">
                {detail.pha.length === 0 && <p className="muted small">No open predictive cases.</p>}
                {detail.pha.map((p) => (
                  <div key={p.source_row} className={`item ${p.max_severity === 'Alert' ? 'caution' : ''}`}>
                    <div className="top"><span className="title">{p.title}</span><span className="chip caution">{p.max_severity}</span></div>
                    <div className="meta">
                      ATA {p.ata}, impact {p.impact}, classification {p.classification}. Opened {fmtDateTime(p.opened)}.{' '}
                      {p.case_link && <SourceTag source={{ url: p.case_link }} label="Open case in AVIATAR" />}
                    </div>
                    <div className="meta">This tool cannot change a case.</div>
                  </div>
                ))}
              </Pane>
            )}

            {tab === 'msgs' && (
              <Pane title="Aircraft messages (AVIATAR)"
                    hint={`${fmtDate(av.window_from)} to ${fmtDate(av.window_to)}, ${av.total_messages} messages in total.`}>
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
                <p className="muted small" style={{ margin: '8px 0 0' }}>Shows the 12 most serious groups. A message is a symptom to check, not a confirmed fault. Source: AVIATAR faults export.</p>
              </Pane>
            )}

            {tab === 'work' && (
              <Pane title="Recent work logged" hint="Derived: no handover records were provided, so these are work-log entries from the last two days.">
                {detail.notes.length === 0 && <p className="muted small">No entries in the last two days.</p>}
                {detail.notes.map((n, i) => <NoteItem key={i} note={n} />)}
              </Pane>
            )}
          </div>
        </>
      )}
    </section>
  )
}
