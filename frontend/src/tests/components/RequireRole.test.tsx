import { beforeEach, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { RequireRole } from "@/components/Auth";
import { useAuthStore } from "@/store/authStore";
import { renderWithProviders } from "@/tests/testUtils";
import { adminUserReadFixture, userReadFixture, viewerUserReadFixture } from "@/tests/mocks/fixtures";

beforeEach(() => {
  useAuthStore.setState({ status: "authenticated", accessToken: "a", refreshToken: "r", user: null, error: null });
});

describe("RequireRole", () => {
  it("renders its children when the user's role satisfies the minimum exactly", () => {
    useAuthStore.setState({ user: userReadFixture }); // analyst
    renderWithProviders(
      <RequireRole minRole="analyst">
        <div>Analyst Content</div>
      </RequireRole>,
    );

    expect(screen.getByText("Analyst Content")).toBeInTheDocument();
  });

  it("a higher-ranked role satisfies a lower requirement", () => {
    useAuthStore.setState({ user: adminUserReadFixture });
    renderWithProviders(
      <RequireRole minRole="analyst">
        <div>Analyst Content</div>
      </RequireRole>,
    );

    expect(screen.getByText("Analyst Content")).toBeInTheDocument();
  });

  it("shows an access-restricted message, not the content, when the role falls short", () => {
    useAuthStore.setState({ user: viewerUserReadFixture });
    renderWithProviders(
      <RequireRole minRole="admin">
        <div>Admin Content</div>
      </RequireRole>,
    );

    expect(screen.getByText("Access restricted")).toBeInTheDocument();
    expect(screen.queryByText("Admin Content")).not.toBeInTheDocument();
  });
});