import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SQLViewer } from "@/components/SQLViewer";
import { generatedSqlFixture, invalidValidationResultFixture, sqlRepairResultFixture, sqlValidationResultFixture } from "@/tests/mocks/fixtures";

describe("SQLViewer", () => {
  it("shows a placeholder when there is no SQL yet", () => {
    render(<SQLViewer sql={null} />);
    expect(screen.getByText("No SQL generated yet.")).toBeInTheDocument();
  });

  it("renders the SQL text and a Valid badge for a passing validation result", () => {
    render(<SQLViewer sql={generatedSqlFixture.sql} validationResult={sqlValidationResultFixture} />);

    expect(screen.getByText("Valid")).toBeInTheDocument();
    // The highlighter splits SQL across per-token <span>s, so match on the <code> ancestor's
    // full text rather than a single text node.
    expect(document.querySelector("code")).toHaveTextContent("SELECT customer_id");
  });

  it("shows an error-count badge for a failing validation result", () => {
    render(<SQLViewer sql={generatedSqlFixture.sql} validationResult={invalidValidationResultFixture} />);
    expect(screen.getByText("1 error")).toBeInTheDocument();
  });

  it("shows a repair status badge when a repair result is present", () => {
    render(<SQLViewer sql={generatedSqlFixture.sql} repairResult={sqlRepairResultFixture} />);
    expect(screen.getByText("Repaired")).toBeInTheDocument();
  });

  it("copies the SQL to the clipboard and shows a Copied confirmation", async () => {
    const user = userEvent.setup();
    // `userEvent.setup()` installs its own clipboard stub, replacing the plain vi.fn() from
    // tests/setup.ts -- spy on whatever is live at this point rather than the original mock.
    const writeTextSpy = vi.spyOn(navigator.clipboard, "writeText");
    render(<SQLViewer sql={generatedSqlFixture.sql} />);

    await user.click(screen.getByRole("button", { name: "Copy SQL to clipboard" }));

    expect(writeTextSpy).toHaveBeenCalledWith(generatedSqlFixture.sql);
    expect(await screen.findByText("Copied")).toBeInTheDocument();
  });

  it("triggers a file download when Download is clicked", async () => {
    const user = userEvent.setup();
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<SQLViewer sql={generatedSqlFixture.sql} />);

    await user.click(screen.getByRole("button", { name: "Download SQL file" }));

    expect(clickSpy).toHaveBeenCalled();
    clickSpy.mockRestore();
  });
});