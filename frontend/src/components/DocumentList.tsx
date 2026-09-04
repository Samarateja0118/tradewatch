import type { DocumentSummary } from "../api/types";
import { DocumentCard } from "./DocumentCard";
import { Empty } from "./states/Empty";

export function DocumentList({
  documents,
  selectedId,
  onSelect,
}: {
  documents: DocumentSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (documents.length === 0) {
    // An empty filter result is a normal outcome, not a failure — it reads
    // differently from an error and is rendered differently.
    return <Empty message="No briefings in this category yet." />;
  }

  return (
    <div className="list">
      {documents.map((document) => (
        <DocumentCard
          key={document.id}
          document={document}
          selected={document.id === selectedId}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}
