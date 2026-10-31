import type { AnalysisItem, Dictionary, InputMessage } from "./types"

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === "string") return body.detail
  } catch {
    return response.statusText || "Помилка запиту"
  }
  return "Перевірте поля форми"
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    })
  } catch {
    throw new Error("Немає зв'язку з сервером. Запустіть бекенд на порті 8000.")
  }
  if (!response.ok) throw new Error(await readError(response))
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export function listDictionaries(): Promise<Dictionary[]> {
  return request("/api/dictionaries")
}

export function createDictionary(body: Omit<Dictionary, "id" | "word_count" | "form_count">): Promise<Dictionary> {
  return request("/api/dictionaries", { method: "POST", body: JSON.stringify(body) })
}

export function updateDictionary(
  id: string,
  body: Omit<Dictionary, "id" | "word_count" | "form_count">,
): Promise<Dictionary> {
  return request(`/api/dictionaries/${id}`, { method: "PUT", body: JSON.stringify(body) })
}

export function deleteDictionary(id: string): Promise<void> {
  return request(`/api/dictionaries/${id}`, { method: "DELETE" })
}

export async function analyzeMessages(messages: InputMessage[]): Promise<{ results: AnalysisItem[]; elapsedMs: number | null }> {
  let response: Response
  try {
    response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
    })
  } catch {
    throw new Error("Немає зв'язку з сервером. Запустіть бекенд на порті 8000.")
  }
  if (!response.ok) throw new Error(await readError(response))
  const header = response.headers.get("X-Elapsed-Ms")
  const elapsedMs = header === null ? null : Number(header)
  return {
    results: (await response.json()) as AnalysisItem[],
    elapsedMs: Number.isFinite(elapsedMs) ? elapsedMs : null,
  }
}
