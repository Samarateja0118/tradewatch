import { useState } from "react";
import { CategoryFilter } from "./components/CategoryFilter";
import { SignificanceFilter } from "./components/SignificanceFilter";
import { StatBar } from "./components/StatBar";
import { DocumentDetail } from "./components/DocumentDetail";
import { DocumentList } from "./components/DocumentList";
import { Empty } from "./components/states/Empty";
import { ErrorState } from "./components/states/ErrorState";
import { Loading } from "./components/states/Loading";
import { useCategories } from "./hooks/useCategories";
import { useDocument } from "./hooks/useDocument";
import { useDocuments } from "./hooks/useDocuments";

/**
 * Three pieces of state live here — the two filters and the selected document
 * id — because each is set by one component and read by a sibling that cannot
 * see it: the filters set what the list requests, and the list sets the id the
 * detail panel reads. The nearest common parent is the right home for exactly
 * those three, and nothing else needs lifting.
 *
 * No Redux, no Zustand. A store would add indirection without removing any:
 * there is no state shared across distant branches, no cross-cutting update,
 * and two `useState` calls are already the smallest thing that works.
 */
export default function App() {
  const [category, setCategory] = useState<string | null>(null);
  const [minSignificance, setMinSignificance] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const categories = useCategories();
  const documents = useDocuments(category, minSignificance);
  const detail = useDocument(selectedId);

  return (
    <div className="app">
      <header className="app__head">
        <h1>
          Trade<span className="app__head-accent">Watch</span>
        </h1>
        <p>
          India–US trade &amp; technology policy, read daily and briefed by significance.
        </p>
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

      <SignificanceFilter
        selected={minSignificance}
        onSelect={(value) => {
          setMinSignificance(value);
          setSelectedId(null);
        }}
      />

      {documents.data && categories.data && (
        <StatBar
          documents={documents.data.items}
          categories={categories.data}
          total={documents.data.total}
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
