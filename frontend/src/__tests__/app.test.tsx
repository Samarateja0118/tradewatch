import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type DocumentSummary } from "../api/types";

/**
 * The API client is mocked, not `fetch`.
 *
 * Tests then depend on the contract — three functions returning typed data —
 * rather than on how those functions happen to travel. Swapping transport, or
 * putting a cache in front of it, leaves every one of these passing. It is the
 * same principle as the pipeline's fake LLM client: mock the seam you designed,
 * not the library underneath it.
 */
vi.mock("../api/client", () => ({
  api: {
    listDocuments: vi.fn(),
    getDocument: vi.fn(),
    listCategories: vi.fn(),
  },
}));

import { api } from "../api/client";
import App from "../App";
import { CategoryFilter } from "../components/CategoryFilter";
import { DocumentCard } from "../components/DocumentCard";
import { DocumentList } from "../components/DocumentList";
import { SignificanceFilter } from "../components/SignificanceFilter";

const mocked = vi.mocked(api);

const doc = (over: Partial<DocumentSummary> = {}): DocumentSummary => ({
  id: "abc123",
  title: "Steel duty review",
  url: "https://example.test/steel",
  source: "federal_register",
  source_label: "Federal Register",
  published: "2026-08-01",
  category: "ad_cvd",
  category_label: "Anti-Dumping / Countervailing Duty",
  significance: 4,
  excerpt: "Commerce opens a review of steel duties.",
  ...over,
});

const categories = [
  { slug: "ad_cvd", label: "Anti-Dumping / Countervailing Duty", count: 2 },
  { slug: "tariff", label: "Tariff", count: 1 },
];

beforeEach(() => {
  vi.clearAllMocks();
  mocked.listCategories.mockResolvedValue(categories);
  mocked.listDocuments.mockResolvedValue({ items: [doc()], total: 1 });
});

describe("CategoryFilter", () => {
  it("reports the slug of the category that was clicked", async () => {
    const onSelect = vi.fn();
    render(<CategoryFilter categories={categories} selected={null} onSelect={onSelect} />);

    await userEvent.click(screen.getByRole("button", { name: /Tariff/ }));

    expect(onSelect).toHaveBeenCalledWith("tariff");
  });

  it("reports null for All, so the caller can clear the filter", async () => {
    const onSelect = vi.fn();
    render(<CategoryFilter categories={categories} selected="tariff" onSelect={onSelect} />);

    await userEvent.click(screen.getByRole("button", { name: /^All/ }));

    expect(onSelect).toHaveBeenCalledWith(null);
  });
});

describe("DocumentList", () => {
  it("renders one card per document", () => {
    const documents = [doc({ id: "a", title: "First" }), doc({ id: "b", title: "Second" }), doc({ id: "c", title: "Third" })];

    render(<DocumentList documents={documents} selectedId={null} onSelect={vi.fn()} />);

    expect(screen.getAllByRole("article")).toHaveLength(3);
  });
});

describe("DocumentCard", () => {
  it("shows the title, the date and the category", () => {
    render(<DocumentCard document={doc()} selected={false} onSelect={vi.fn()} />);

    expect(screen.getByText("Steel duty review")).toBeInTheDocument();
    expect(screen.getByText("Anti-Dumping / Countervailing Duty")).toBeInTheDocument();
    // Rendered through toLocaleDateString, so assert on the year rather than a
    // format that depends on the machine's locale.
    expect(screen.getByText(/2026/)).toBeInTheDocument();
  });
});

describe("the list's non-happy paths", () => {
  it("shows the empty state when a filter matches nothing", async () => {
    mocked.listDocuments.mockResolvedValue({ items: [], total: 0 });

    render(<App />);

    expect(await screen.findByText(/No briefings in this category/i)).toBeInTheDocument();
  });

  it("shows the error state when the request fails", async () => {
    mocked.listDocuments.mockRejectedValue(new ApiError("network", "boom"));

    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/Could not reach the API/i);
  });

  it("asks the API for the selected category when the filter changes", async () => {
    render(<App />);
    await screen.findByText("Steel duty review");

    await userEvent.click(await screen.findByRole("button", { name: /Tariff/ }));

    await waitFor(() =>
      expect(mocked.listDocuments).toHaveBeenLastCalledWith({
        category: "tariff",
        min_significance: undefined,
      }),
    );
  });
});


describe("SignificanceFilter", () => {
  it("reports the floor that was clicked", async () => {
    const onSelect = vi.fn();
    render(<SignificanceFilter selected={null} onSelect={onSelect} />);

    await userEvent.click(screen.getByRole("button", { name: "4+" }));

    expect(onSelect).toHaveBeenCalledWith(4);
  });

  it("reports null for Any, so the caller can clear the floor", async () => {
    const onSelect = vi.fn();
    render(<SignificanceFilter selected={4} onSelect={onSelect} />);

    await userEvent.click(screen.getByRole("button", { name: "Any" }));

    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it("sends the floor to the API rather than filtering the page in the browser", async () => {
    render(<App />);
    await screen.findByText("Steel duty review");

    await userEvent.click(screen.getByRole("button", { name: "4+" }));

    // Filtering client-side would narrow one page instead of the result set —
    // indistinguishable on seven documents, wrong on seven hundred.
    await waitFor(() =>
      expect(mocked.listDocuments).toHaveBeenLastCalledWith({
        category: undefined,
        min_significance: 4,
      }),
    );
  });

  it("composes with the category filter", async () => {
    render(<App />);
    await screen.findByText("Steel duty review");

    await userEvent.click(screen.getByRole("button", { name: /Tariff/ }));
    await userEvent.click(screen.getByRole("button", { name: "Only 5" }));

    await waitFor(() =>
      expect(mocked.listDocuments).toHaveBeenLastCalledWith({
        category: "tariff",
        min_significance: 5,
      }),
    );
  });
});
