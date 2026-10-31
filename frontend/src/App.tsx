import { useEffect, useState } from "react"
import { DictionariesPage } from "./pages/Dictionaries"
import { TestBench } from "./pages/TestBench"

type Page = "dictionaries" | "test"

function pageFromHash(): Page {
  return window.location.hash === "#test" ? "test" : "dictionaries"
}

export function App() {
  const [page, setPage] = useState<Page>(pageFromHash)

  useEffect(() => {
    const onHash = () => setPage(pageFromHash())
    window.addEventListener("hashchange", onHash)
    return () => window.removeEventListener("hashchange", onHash)
  }, [])

  return (
    <div className="app">
      <header className="top">
        <div>
          <p className="eyebrow">Модуль перевірки</p>
          <h1>Аналіз повідомлень</h1>
        </div>
        <nav>
          <a className={page === "dictionaries" ? "active" : ""} href="#dictionaries">
            Словники
          </a>
          <a className={page === "test" ? "active" : ""} href="#test">
            Перевірка
          </a>
        </nav>
      </header>
      <main>{page === "dictionaries" ? <DictionariesPage /> : <TestBench />}</main>
    </div>
  )
}
