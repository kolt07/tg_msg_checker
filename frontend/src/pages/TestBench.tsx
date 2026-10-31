import { useState } from "react"
import { analyzeMessages } from "../api"
import type { AnalysisItem, CoordinateMatch, EntityGroup, InputMessage, TagGroup } from "../types"

type Mode = "text" | "json" | "lines"

type Span = {
  start: number
  end: number
  kind: string
  label: string
}

export function TestBench() {
  const [mode, setMode] = useState<Mode>("text")
  const [raw, setRaw] = useState("Побачив гранату біля X = 5179365 Y = 6500127")
  const [error, setError] = useState("")
  const [running, setRunning] = useState(false)
  const [elapsedMs, setElapsedMs] = useState<number | null>(null)
  const [submitted, setSubmitted] = useState(0)
  const [results, setResults] = useState<AnalysisItem[] | null>(null)
  const [copied, setCopied] = useState(false)

  async function onFile(file: File | undefined) {
    if (!file) return
    const text = await file.text()
    setRaw(text)
    setMode(file.name.toLowerCase().endsWith(".json") ? "json" : "lines")
    setError("")
  }

  async function run() {
    setError("")
    let messages: InputMessage[]
    try {
      messages = parseInput(mode, raw)
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Не вдалося прочитати повідомлення")
      return
    }
    if (messages.length === 0) {
      setError("Немає повідомлень для перевірки")
      return
    }
    setRunning(true)
    try {
      const response = await analyzeMessages(messages)
      setResults(response.results)
      setCopied(false)
      setElapsedMs(response.elapsedMs)
      setSubmitted(messages.length)
    } catch (reason: unknown) {
      setResults(null)
      setError(reason instanceof Error ? reason.message : "Помилка")
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="bench">
      <section className="panel">
        <div className="row spread">
          <h2>Повідомлення</h2>
          <label className="inline">
            Формат
            <select value={mode} onChange={(event) => setMode(event.target.value as Mode)}>
              <option value="text">Одне повідомлення</option>
              <option value="json">JSON-масив</option>
              <option value="lines">Рядки файлу</option>
            </select>
          </label>
        </div>
        <textarea className="mono" rows={12} value={raw} onChange={(event) => setRaw(event.target.value)} />
        <div className="row">
          <label className="file">
            Файл .json або .txt
            <input
              type="file"
              accept=".json,.txt,application/json,text/plain"
              onChange={(event) => void onFile(event.target.files?.[0])}
            />
          </label>
          <button type="button" onClick={() => void run()} disabled={running}>
            {running ? "Обробка…" : "Проаналізувати"}
          </button>
        </div>
        <p className="hint">
          JSON: масив або об’єкт з полем messages. У текстовому файлі один рядок — одне повідомлення, id дорівнює
          номеру рядка.
        </p>
        {error ? <p className="error">{error}</p> : null}
      </section>

      {results ? (
        <section className="panel">
          <div className="stats">
            <span>Час обробки: {formatMs(elapsedMs)}</span>
            <span>
              Зі знахідками: {results.length} із {submitted}
            </span>
          </div>
          {results.length === 0 ? <p className="hint">Нічого не знайдено.</p> : null}
          <div className="results">
            {results.map((item, index) => (
              <article key={`${item.id}-${index}`} className="result">
                <header>
                  <span className="id">id {item.id}</span>
                </header>
                <p className="message">
                  <Highlight text={textOf(item, raw, mode)} item={item} />
                </p>
                <MatchList item={item} />
              </article>
            ))}
          </div>
        </section>
      ) : null}
      {results ? (
        <section className="panel">
          <div className="row spread">
            <h2>Вивантаження</h2>
            <div className="row">
              <button type="button" className="ghost" onClick={() => downloadFindings(results)}>
                Завантажити
              </button>
              <button type="button" className="ghost" onClick={() => void copyFindings(results, setCopied)}>
                {copied ? "Скопійовано" : "Копіювати"}
              </button>
            </div>
          </div>
          <p className="hint">Лише теги і сутності знайдених повідомлень.</p>
          <pre className="mono">{JSON.stringify(results, null, 2)}</pre>
        </section>
      ) : null}
    </div>
  )
}

function parseInput(mode: Mode, raw: string): InputMessage[] {
  if (mode === "text") return [{ id: "1", text: raw }]
  if (mode === "lines") {
    return raw.split(/\r?\n/).flatMap((line, index) => (line.trim() ? [{ id: String(index + 1), text: line }] : []))
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    throw new Error("JSON не розібрано")
  }
  const list = Array.isArray(parsed)
    ? parsed
    : parsed && typeof parsed === "object" && Array.isArray((parsed as { messages?: unknown }).messages)
      ? (parsed as { messages: unknown[] }).messages
      : null
  if (!list) throw new Error("Очікується масив повідомлень або об’єкт з полем messages")
  return list.map((item, index) => {
    if (!item || typeof item !== "object") throw new Error(`Елемент ${index + 1} не є об’єктом`)
    const record = item as Record<string, unknown>
    if (typeof record.text !== "string") throw new Error(`У елемента ${index + 1} немає текстового поля text`)
    return {
      id: record.id === undefined ? String(index + 1) : String(record.id),
      text: record.text,
    }
  })
}

function findingsJson(results: AnalysisItem[]): string {
  return JSON.stringify(results, null, 2)
}

function downloadFindings(results: AnalysisItem[]) {
  const blob = new Blob([findingsJson(results)], { type: "application/json;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = "findings.json"
  link.click()
  URL.revokeObjectURL(url)
}

async function copyFindings(results: AnalysisItem[], setCopied: (value: boolean) => void) {
  await navigator.clipboard.writeText(findingsJson(results))
  setCopied(true)
}

function textOf(item: AnalysisItem, raw: string, mode: Mode): string {
  if (mode === "text") return raw
  try {
    return parseInput(mode, raw).find((message) => message.id === item.id)?.text ?? raw
  } catch {
    return raw
  }
}

function Highlight({ text, item }: { text: string; item: AnalysisItem }) {
  const spans = collectSpans(item)
  const parts = segments(text, spans)
  return (
    <>
      {parts.map((part, index) => {
        if (part.active.length === 0) return <span key={index}>{part.text}</span>
        const kinds = new Set(part.active.map((span) => span.kind))
        const kind = kinds.size === 1 ? [...kinds][0] : "mixed"
        return (
          <mark key={index} className={kind} title={part.active.map((span) => span.label).join(", ")}>
            {part.text}
          </mark>
        )
      })}
    </>
  )
}

function collectSpans(item: AnalysisItem): Span[] {
  const spans: Span[] = []
  for (const tag of item.tags ?? []) {
    for (const match of tag.matches) {
      spans.push({ start: match.start, end: match.end, kind: "tag", label: tag.tag })
    }
  }
  for (const entity of item.entities ?? []) {
    for (const match of entity.matches) {
      spans.push({
        start: match.start,
        end: match.end,
        kind: entity.type,
        label: `координати ${match.lat}, ${match.lon}`,
      })
    }
  }
  return spans
}

function segments(text: string, spans: Span[]) {
  const safe = spans.filter((span) => span.start >= 0 && span.end > span.start && span.start < text.length)
  const points = new Set<number>([0, text.length])
  for (const span of safe) {
    points.add(span.start)
    points.add(Math.min(text.length, span.end))
  }
  const cuts = [...points].sort((left, right) => left - right)
  const parts: { text: string; active: Span[] }[] = []
  for (let index = 0; index < cuts.length - 1; index += 1) {
    const start = cuts[index]
    const end = cuts[index + 1]
    if (start === end) continue
    parts.push({
      text: text.slice(start, end),
      active: safe.filter((span) => span.start <= start && span.end >= end),
    })
  }
  return parts
}

function MatchList({ item }: { item: AnalysisItem }) {
  return (
    <ul className="matches">
      {(item.tags ?? []).map((tag) => (
        <TagLine key={tag.tag} tag={tag} />
      ))}
      {(item.entities ?? []).map((entity) => (
        <EntityLine key={entity.type} entity={entity} />
      ))}
    </ul>
  )
}

function TagLine({ tag }: { tag: TagGroup }) {
  return (
    <li>
      <span className="pill tag">тег {tag.tag}</span>
      {tag.matches.map((match, index) => (
        <span key={`${match.start}-${index}`}>
          {match.text} <em>({match.lemma})</em>
        </span>
      ))}
    </li>
  )
}

function EntityLine({ entity }: { entity: EntityGroup }) {
  return (
    <li>
      <span className={`pill ${entity.type}`}>{entityTitle(entity.type)}</span>
      {entity.matches.map((match, index) => (
        <span key={`${match.start}-${index}`}>{formatEntity(match)}</span>
      ))}
    </li>
  )
}

function entityTitle(type: string): string {
  if (type === "coordinates") return "координати"
  return type
}

function formatEntity(match: CoordinateMatch): string {
  return `${match.text} → ${match.lat}, ${match.lon} (${match.format})`
}

function formatMs(value: number | null): string {
  if (value === null) return "немає"
  return `${value.toLocaleString("uk-UA", { maximumFractionDigits: 2 })} мс`
}
