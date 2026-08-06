import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { AnswerCard } from "@/components/AnswerCard";
import { businessAnswerFixture } from "@/tests/mocks/fixtures";

describe("AnswerCard", () => {
  it("shows a prompt to ask a question when there is no answer yet", () => {
    render(<AnswerCard businessAnswer={null} />);
    expect(screen.getByText(/No answer yet/)).toBeInTheDocument();
  });

  it("renders the answer's type, title, and description", () => {
    render(<AnswerCard businessAnswer={businessAnswerFixture} />);

    expect(screen.getByText("Table")).toBeInTheDocument();
    expect(screen.getByText("Top 5 customers by revenue")).toBeInTheDocument();
    expect(screen.getByText(businessAnswerFixture.summary.description)).toBeInTheDocument();
  });
});