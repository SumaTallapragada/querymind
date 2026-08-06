import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { LoadingIndicator } from "@/components/LoadingIndicator";

describe("LoadingIndicator", () => {
  it("announces a default 'Loading' label via role=status", () => {
    render(<LoadingIndicator />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
  });

  it("shows a custom label when given one", () => {
    render(<LoadingIndicator label="Loading settings..." />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading settings...");
  });
});