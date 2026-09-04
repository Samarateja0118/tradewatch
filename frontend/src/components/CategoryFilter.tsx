import type { CategoryCount } from "../api/types";

/**
 * Presentational: it is told the categories and which one is selected, and
 * reports clicks upward. It holds no state of its own, so the selection cannot
 * disagree with what the list is showing.
 */
export function CategoryFilter({
  categories,
  selected,
  onSelect,
}: {
  categories: CategoryCount[];
  selected: string | null;
  onSelect: (slug: string | null) => void;
}) {
  const total = categories.reduce((sum, c) => sum + c.count, 0);

  return (
    <nav className="filter" aria-label="Filter by category">
      <button
        type="button"
        className={selected === null ? "chip chip--on" : "chip"}
        aria-pressed={selected === null}
        onClick={() => onSelect(null)}
      >
        All <span className="chip__count">{total}</span>
      </button>

      {categories.map((category) => (
        <button
          key={category.slug}
          type="button"
          className={selected === category.slug ? "chip chip--on" : "chip"}
          aria-pressed={selected === category.slug}
          onClick={() => onSelect(category.slug)}
        >
          {category.label} <span className="chip__count">{category.count}</span>
        </button>
      ))}
    </nav>
  );
}
