import { useMemo, useRef, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, Download } from "lucide-react";
import { Button, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui";
import { cn } from "@/lib/utils";
import { downloadTextFile } from "@/utils/download";
import { formattedTableToCsv } from "@/utils/csv";
import type { FormattedRow, FormattedTable } from "@/models";

export interface ResultTableProps {
  table: FormattedTable | null;
}

type SortDirection = "asc" | "desc";
interface SortState {
  columnIndex: number;
  direction: SortDirection;
}

const DEFAULT_COLUMN_WIDTH = 160;
const MIN_COLUMN_WIDTH = 80;
const PAGE_SIZE_OPTIONS = [10, 25, 50, 100] as const;

function compareRows(a: FormattedRow, b: FormattedRow, sort: SortState): number {
  const left = a.values[sort.columnIndex];
  const right = b.values[sort.columnIndex];
  if (!left || !right) return 0;

  let result: number;
  if (typeof left.original_value === "number" && typeof right.original_value === "number") {
    result = left.original_value - right.original_value;
  } else {
    result = left.formatted_value.localeCompare(right.formatted_value);
  }
  return sort.direction === "asc" ? result : -result;
}

export function ResultTable({ table }: ResultTableProps) {
  const [sort, setSort] = useState<SortState | null>(null);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState<number>(10);
  const [columnWidths, setColumnWidths] = useState<number[]>([]);
  const resizingRef = useRef<{ columnIndex: number; startX: number; startWidth: number } | null>(null);

  const widths = table
    ? table.columns.map((_, index) => columnWidths[index] ?? DEFAULT_COLUMN_WIDTH)
    : [];

  const sortedRows = useMemo(() => {
    if (!table) return [];
    if (!sort) return table.rows;
    return [...table.rows].sort((a, b) => compareRows(a, b, sort));
  }, [table, sort]);

  const pageCount = table ? Math.max(1, Math.ceil(sortedRows.length / pageSize)) : 1;
  const clampedPage = Math.min(page, pageCount - 1);
  const pageRows = sortedRows.slice(clampedPage * pageSize, clampedPage * pageSize + pageSize);

  function toggleSort(columnIndex: number): void {
    setSort((current) => {
      if (!current || current.columnIndex !== columnIndex) return { columnIndex, direction: "asc" };
      if (current.direction === "asc") return { columnIndex, direction: "desc" };
      return null;
    });
    setPage(0);
  }

  function startResize(columnIndex: number, event: React.MouseEvent): void {
    resizingRef.current = {
      columnIndex,
      startX: event.clientX,
      startWidth: widths[columnIndex] ?? DEFAULT_COLUMN_WIDTH,
    };
    document.addEventListener("mousemove", handleResizeMove);
    document.addEventListener("mouseup", stopResize);
  }

  function handleResizeMove(event: MouseEvent): void {
    const resizing = resizingRef.current;
    if (!resizing) return;
    const delta = event.clientX - resizing.startX;
    const nextWidth = Math.max(MIN_COLUMN_WIDTH, resizing.startWidth + delta);
    setColumnWidths((current) => {
      const next = [...current];
      next[resizing.columnIndex] = nextWidth;
      return next;
    });
  }

  function stopResize(): void {
    resizingRef.current = null;
    document.removeEventListener("mousemove", handleResizeMove);
    document.removeEventListener("mouseup", stopResize);
  }

  if (table === null) {
    return <p className="text-sm text-muted-foreground">No results to display yet.</p>;
  }

  if (table.rows.length === 0) {
    return <p className="text-sm text-muted-foreground">The query returned no rows.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {table.rows.length} row{table.rows.length === 1 ? "" : "s"} &middot; {table.columns.length}{" "}
          column{table.columns.length === 1 ? "" : "s"}
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => downloadTextFile("result.csv", formattedTableToCsv(table), "text/csv;charset=utf-8")}
        >
          <Download />
          Export CSV
        </Button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              {table.columns.map((column, columnIndex) => (
                <TableHead
                  key={column.name}
                  style={{ width: widths[columnIndex], position: "relative" }}
                  className="select-none"
                >
                  <button
                    type="button"
                    onClick={() => toggleSort(columnIndex)}
                    className="flex items-center gap-1 hover:text-foreground"
                    aria-label={`Sort by ${column.name}`}
                  >
                    {column.name}
                    {sort?.columnIndex === columnIndex ? (
                      sort.direction === "asc" ? (
                        <ArrowUp className="h-3 w-3" aria-hidden="true" />
                      ) : (
                        <ArrowDown className="h-3 w-3" aria-hidden="true" />
                      )
                    ) : (
                      <ArrowUpDown className="h-3 w-3 opacity-40" aria-hidden="true" />
                    )}
                  </button>
                  <span
                    role="separator"
                    aria-orientation="vertical"
                    onMouseDown={(event) => startResize(columnIndex, event)}
                    className={cn(
                      "absolute right-0 top-0 h-full w-1.5 cursor-col-resize",
                      "hover:bg-primary/40",
                    )}
                  />
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {pageRows.map((row, rowIndex) => (
              <TableRow key={rowIndex}>
                {row.values.map((value, columnIndex) => (
                  <TableCell key={columnIndex} style={{ width: widths[columnIndex] }} className="truncate">
                    {value.formatted_value}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <div className="flex items-center gap-2">
          <label htmlFor="page-size" className="text-xs text-muted-foreground">
            Rows per page
          </label>
          <select
            id="page-size"
            value={pageSize}
            onChange={(event) => {
              setPageSize(Number(event.target.value));
              setPage(0);
            }}
            className="rounded-md border border-input bg-background px-2 py-1 text-xs"
          >
            {PAGE_SIZE_OPTIONS.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={clampedPage === 0}
            onClick={() => setPage((current) => Math.max(0, current - 1))}
          >
            Previous
          </Button>
          <span className="text-xs text-muted-foreground">
            Page {clampedPage + 1} of {pageCount}
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={clampedPage >= pageCount - 1}
            onClick={() => setPage((current) => Math.min(pageCount - 1, current + 1))}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
