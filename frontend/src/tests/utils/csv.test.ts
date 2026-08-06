import { describe, expect, it } from "vitest";
import { formattedTableToCsv } from "@/utils/csv";
import type { FormattedTable } from "@/models";

function table(overrides: Partial<FormattedTable> = {}): FormattedTable {
  return {
    columns: [
      { name: "customer_id", database_type: "integer", python_type: "int", nullable: false },
      { name: "revenue", database_type: "numeric", python_type: "float", nullable: false },
    ],
    rows: [
      {
        values: [
          { original_value: 101, formatted_value: "101", detected_type: "integer" },
          { original_value: 48210.5, formatted_value: "$48,210.50", detected_type: "currency" },
        ],
      },
    ],
    ...overrides,
  };
}

describe("formattedTableToCsv", () => {
  it("renders a header row followed by one row per data row, CRLF-joined", () => {
    const csv = formattedTableToCsv(table());
    expect(csv).toBe('customer_id,revenue\r\n101,"$48,210.50"');
  });

  it("quotes and escapes a cell containing a comma, quote, or newline", () => {
    const csv = formattedTableToCsv(
      table({
        rows: [{ values: [{ original_value: 1, formatted_value: 'He said "hi", then left\nnext line', detected_type: "string" }, { original_value: 0, formatted_value: "0", detected_type: "integer" }] }],
      }),
    );
    expect(csv).toContain('"He said ""hi"", then left\nnext line"');
  });

  it("leaves a plain cell unquoted", () => {
    const csv = formattedTableToCsv(table());
    expect(csv.split("\r\n")[1]?.startsWith("101,")).toBe(true);
  });
});