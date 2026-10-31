import { useEffect, useState } from "react"
import { createDictionary, deleteDictionary, listDictionaries, updateDictionary } from "../api"
import type { Dictionary, Language } from "../types"

const LANGUAGES: { value: Language; label: string }[] = [
  { value: "uk", label: "Українська" },
  { value: "ru", label: "Російська" },
  { value: "en", label: "Англійська" },
]

const emptyForm = {
  id: "",
  name: "",
  language: "uk" as Language,
  tag: "",
  words: "",
}

export function DictionariesPage() {
  const [items, setItems] = useState<Dictionary[]>([])
  const [form, setForm] = useState(emptyForm)
  const [error, setError] = useState("")
  const [status, setStatus] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  async function reload() {
    setItems(await listDictionaries())
  }

  useEffect(() => {
    reload()
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Помилка"))
      .finally(() => setLoading(false))
  }, [])

  function edit(item: Dictionary) {
    setForm({
      id: item.id,
      name: item.name,
      language: item.language,
      tag: item.tag,
      words: item.words.join("\n"),
    })
    setStatus("")
    setError("")
  }

  async function save() {
    setSaving(true)
    setError("")
    setStatus("")
    const body = {
      name: form.name.trim(),
      language: form.language,
      tag: form.tag.trim(),
      words: form.words.split(/\r?\n/).map((line) => line.trim()).filter(Boolean),
    }
    try {
      const saved = form.id ? await updateDictionary(form.id, body) : await createDictionary(body)
      await reload()
      setForm({ ...form, id: saved.id })
      setStatus(`Збережено: ${ukCount(saved.word_count, "слово", "слова", "слів")}, ${ukCount(saved.form_count, "словоформа", "словоформи", "словоформ")}.`)
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Помилка")
    } finally {
      setSaving(false)
    }
  }

  async function remove(item: Dictionary) {
    if (!window.confirm(`Видалити словник «${item.name}»?`)) return
    setError("")
    try {
      await deleteDictionary(item.id)
      if (form.id === item.id) setForm(emptyForm)
      await reload()
      setStatus("Словник видалено.")
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Помилка")
    }
  }

  return (
    <div className="split">
      <section className="panel">
        <h2>{form.id ? "Редагувати словник" : "Новий словник"}</h2>
        <label>
          Назва
          <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
        </label>
        <label>
          Мова
          <select
            value={form.language}
            onChange={(event) => setForm({ ...form, language: event.target.value as Language })}
          >
            {LANGUAGES.map((language) => (
              <option key={language.value} value={language.value}>
                {language.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Тег
          <input value={form.tag} onChange={(event) => setForm({ ...form, tag: event.target.value })} />
        </label>
        <label>
          Слова в називному відмінку
          <textarea
            rows={10}
            value={form.words}
            onChange={(event) => setForm({ ...form, words: event.target.value })}
            placeholder={"граната\nбойова машина"}
          />
        </label>
        <p className="hint">Кожен рядок — слово або термін до 4 слів. У тексті шукаємо їхні словоформи.</p>
        {error ? <p className="error">{error}</p> : null}
        {status ? <p className="status">{status}</p> : null}
        <div className="row">
          <button type="button" onClick={() => void save()} disabled={saving}>
            {saving ? "Збереження…" : "Зберегти"}
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => {
              setForm(emptyForm)
              setStatus("")
              setError("")
            }}
          >
            Новий
          </button>
        </div>
      </section>
      <section className="panel">
        <h2>Словники</h2>
        {loading ? <p className="hint">Завантаження…</p> : null}
        {!loading && items.length === 0 ? <p className="hint">Словників ще немає.</p> : null}
        <ul className="cards">
          {items.map((item) => (
            <li key={item.id} className={item.id === form.id ? "card selected" : "card"}>
              <button type="button" className="card-main" onClick={() => edit(item)}>
                <strong>{item.name}</strong>
                <span className="tag">{item.tag}</span>
                <span className="meta">
                  {languageLabel(item.language)} · {ukCount(item.word_count, "слово", "слова", "слів")} ·{" "}
                  {ukCount(item.form_count, "словоформа", "словоформи", "словоформ")}
                </span>
              </button>
              <button type="button" className="ghost danger" onClick={() => void remove(item)}>
                Видалити
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

function languageLabel(language: Language): string {
  return LANGUAGES.find((item) => item.value === language)?.label ?? language
}

function ukCount(count: number, one: string, few: string, many: string): string {
  const abs = Math.abs(count) % 100
  const last = abs % 10
  if (abs > 10 && abs < 20) return `${count} ${many}`
  if (last === 1) return `${count} ${one}`
  if (last >= 2 && last <= 4) return `${count} ${few}`
  return `${count} ${many}`
}
