export type Language = "uk" | "ru" | "en"

export type Dictionary = {
  id: string
  name: string
  language: Language
  tag: string
  words: string[]
  word_count: number
  form_count: number
}

export type TagMatch = {
  text: string
  lemma: string
  start: number
  end: number
}

export type PhoneMatch = {
  text: string
  normalized: string
  start: number
  end: number
}

export type CoordinateMatch = {
  text: string
  format: string
  lat: number
  lon: number
  start: number
  end: number
}

export type TagGroup = {
  tag: string
  matches: TagMatch[]
}

export type EntityGroup = {
  type: string
  matches: Array<PhoneMatch | CoordinateMatch>
}

export type AnalysisItem = {
  id: string
  tags?: TagGroup[]
  entities?: EntityGroup[]
}

export type InputMessage = {
  id: string
  text: string
}
