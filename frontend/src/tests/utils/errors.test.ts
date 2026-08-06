import { describe, expect, it } from "vitest";
import { errorMessage } from "@/utils/errors";
import { ApiError, NetworkError } from "@/models";

describe("errorMessage", () => {
  it("returns an ApiError's message", () => {
    const error = new ApiError(422, { detail: "Empty question.", error_type: "EmptyQuestionError" });
    expect(errorMessage(error)).toBe("Empty question.");
  });

  it("returns a NetworkError's message", () => {
    expect(errorMessage(new NetworkError("The request could not be sent."))).toBe(
      "The request could not be sent.",
    );
  });

  it("returns a plain Error's message", () => {
    expect(errorMessage(new Error("boom"))).toBe("boom");
  });

  it("falls back to a generic message for a non-Error throw, never leaking it raw", () => {
    expect(errorMessage("some raw string")).toBe("An unexpected error occurred.");
    expect(errorMessage(undefined)).toBe("An unexpected error occurred.");
  });
});