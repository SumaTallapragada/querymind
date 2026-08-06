import type { FormattedTable } from "@/models";

function escapeCsvCell(value: string): string {
  if (/[",\n]/.test(value)) {
    return `"${value.replaceAll('"', '""')}"`;
  }
  return value;
}

/** Renders a `FormattedTable` as RFC 4180-ish CSV text -- formatted values only, matching what
 * the table itself displays (never the raw, possibly locale-dependent original values).
 */
export function formattedTableToCsv(table: FormattedTable): string {
  const header = table.columns.map((column) => escapeCsvCell(column.name)).join(",");
  const rows = table.rows.map((row) =>
    row.values.map((value) => escapeCsvCell(value.formatted_value)).join(","),
  );
  return [header, ...rows].join("\r\n");
}
