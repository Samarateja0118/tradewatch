/**
 * A floor, not a band. "Show me anything that matters" is the question a reader
 * has; "show me exactly the 3s" is not, and an exact filter would hide the 5s
 * from someone asking for 3.
 *
 * Presentational, like CategoryFilter — it is told the current floor and
 * reports changes upward, so it cannot disagree with what the list shows.
 */
const LEVELS = [
  { value: null, label: "Any" },
  { value: 3, label: "3+" },
  { value: 4, label: "4+" },
  { value: 5, label: "Only 5" },
] as const;

export function SignificanceFilter({
  selected,
  onSelect,
}: {
  selected: number | null;
  onSelect: (value: number | null) => void;
}) {
  return (
    <nav className="filter filter--sig" aria-label="Filter by significance">
      <span className="filter__label">Significance</span>
      {LEVELS.map((level) => (
        <button
          key={level.label}
          type="button"
          className={selected === level.value ? "chip chip--on" : "chip"}
          aria-pressed={selected === level.value}
          onClick={() => onSelect(level.value)}
        >
          {level.label}
        </button>
      ))}
    </nav>
  );
}
