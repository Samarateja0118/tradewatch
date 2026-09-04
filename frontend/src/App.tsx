import { useState } from "react";
import { CategoryFilter } from "./components/CategoryFilter";
import { DocumentDetail } from "./components/DocumentDetail";
import { DocumentList } from "./components/DocumentList";
import { Empty } from "./components/states/Empty";
import { ErrorState } from "./components/states/ErrorState";
import { Loading } from "./components/states/Loading";
import { useCategories } from "./hooks/useCategories";
import { useDocument } from "./hooks/useDocument";
import { useDocuments } from "./hooks/useDocuments";

/**
 * Two pieces of state live here — the selected category and the selected
 * document id — because both are read by siblings that cannot see each other:
 * the filter sets the category the list reads, and the list sets the id the
 * detail panel reads. The nearest common parent is the right home for exactly
 * those two, and nothing else needs lifting.
 *
 * No Redux, no Zustand. A store would add indirection without removing any:
 * there is no state shared across distant branches, no cross-cutting update,
 * and two `useState` calls are already the smallest thing that works.
 */
export default function App() {
  const [category, setCategory] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const categories = useCategories();
  const documents = useDocuments(category);
  const detail = useDocument(selectedId);

  return (
    <div className="app">
      <header className="app__head">
        <h1>TradeWatch</h1>
        <p>India–US trade &amp; technology policy, briefed daily.</p>
      </header>

      {categories.loading && <Loading label="Loading categories" />}
      {categories.error && <ErrorState error={categories.error} />}
      {categories.data && (
        <CategoryFilter
          categories={categories.data}
          selected={category}
          onSelect={(slug) => {
            setCategory(slug);
            // The open briefing may not be in the new category; keeping it
            // would leave the panel showing something the list no longer lists.
            setSelectedId(null);
          }}
        />
      )}

      <main className="app__body">
        <section className="app__list" aria-label="Briefings">
          {documents.loading && <Loading label="Loading briefings" />}
          {documents.error && <ErrorState error={documents.error} />}
          {documents.data && (
            <DocumentList
              documents={documents.data.items}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          )}
        </section>

        <aside className="app__detail" aria-label="Briefing detail">
          {detail.loading && <Loading label="Loading briefing" />}
          {detail.error && <ErrorState error={detail.error} />}
          {detail.data && <DocumentDetail document={detail.data} onClose={() => setSelectedId(null)} />}
          {!selectedId && !detail.loading && <Empty message="Select a briefing to read it." />}
        </aside>
      </main>
    </div>
  );
}
