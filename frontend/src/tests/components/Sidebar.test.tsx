import { beforeEach, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { Sidebar } from "@/components/Layout/Sidebar";
import { useAuthStore } from "@/store/authStore";
import { renderWithProviders } from "@/tests/testUtils";
import { adminUserReadFixture, userReadFixture, viewerUserReadFixture } from "@/tests/mocks/fixtures";

beforeEach(() => {
  useAuthStore.setState({ status: "authenticated", accessToken: "a", refreshToken: "r", user: null, error: null });
});

describe("Sidebar (role-aware navigation)", () => {
  it("shows only the Health link for a viewer", () => {
    useAuthStore.setState({ user: viewerUserReadFixture });
    renderWithProviders(<Sidebar />);

    expect(screen.getByRole("link", { name: /Health/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Dashboard/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Diagnostics/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Metrics/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Settings/ })).not.toBeInTheDocument();
  });

  it("shows Dashboard and Health for an analyst, but hides admin-only links", () => {
    useAuthStore.setState({ user: userReadFixture }); // analyst
    renderWithProviders(<Sidebar />);

    expect(screen.getByRole("link", { name: /Dashboard/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Health/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Diagnostics/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Metrics/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Settings/ })).not.toBeInTheDocument();
  });

  it("shows every nav item for an admin", () => {
    useAuthStore.setState({ user: adminUserReadFixture });
    renderWithProviders(<Sidebar />);

    for (const name of [/Dashboard/, /Diagnostics/, /Health/, /Metrics/, /Settings/]) {
      expect(screen.getByRole("link", { name })).toBeInTheDocument();
    }
  });
});