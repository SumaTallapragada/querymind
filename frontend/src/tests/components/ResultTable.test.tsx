import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ResultTable } from "@/components/ResultTable";
import { businessAnswerFixture } from "@/tests/mocks/fixtures";

describe("ResultTable", () => {
  it("shows an empty state when there is no table yet", () => {
    render(<ResultTable table={null} />);
    expect(screen.getByText("No results to display yet.")).toBeInTheDocument();
  });

  it("shows a no-rows message when the table has zero rows", () => {
    render(<ResultTable table={{ ...businessAnswerFixture.formatted_table, rows: [] }} />);
    expect(screen.getByText("The query returned no rows.")).toBeInTheDocument();
  });

  it("renders every column header and every row's formatted values", () => {
    render(<ResultTable table={businessAnswerFixture.formatted_table} />);

    expect(screen.getByRole("columnheader", { name: /customer_id/ })).toBeInTheDocument();
    expect(screen.getByText("$48,210.50")).toBeInTheDocument();
    expect(screen.getByText("$39,120.00")).toBeInTheDocument();
  });

  it("sorts rows ascending then descending when a column header is clicked twice", async () => {
    const user = userEvent.setup();
    render(<ResultTable table={businessAnswerFixture.formatted_table} />);

    const sortButton = screen.getByRole("button", { name: "Sort by revenue" });
    const rows = () => screen.getAllByRole("row").slice(1); // drop header row

    await user.click(sortButton);
    expect(within(rows()[0]!).getByText("$39,120.00")).toBeInTheDocument();

    await user.click(sortButton);
    expect(within(rows()[0]!).getByText("$48,210.50")).toBeInTheDocument();
  });

  it("shows the row/column count summary", () => {
    render(<ResultTable table={businessAnswerFixture.formatted_table} />);
    expect(screen.getByText("2 rows · 2 columns")).toBeInTheDocument();
  });
});