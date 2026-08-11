import { beforeEach, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Topbar } from "@/components/Layout/Topbar";
import { useAuthStore } from "@/store/authStore";
import { useUiStore } from "@/store/uiStore";
import { renderWithProviders } from "@/tests/testUtils";
import { userReadFixture } from "@/tests/mocks/fixtures";

const REAL_ACCESS_TOKEN = "a-real-access-token";
const REAL_REFRESH_TOKEN = "a-real-refresh-token";

beforeEach(() => {
  useAuthStore.setState({
    status: "authenticated",
    accessToken: REAL_ACCESS_TOKEN,
    refreshToken: REAL_REFRESH_TOKEN,
    user: userReadFixture,
    error: null,
  });
  useUiStore.setState({ theme: "system", sidebarOpen: false, streamingTransport: "sse" });
});

describe("Topbar (user menu)", () => {
  it("shows the authenticated user's username and role", () => {
    renderWithProviders(<Topbar title="Dashboard" />);

    expect(screen.getByText(userReadFixture.username)).toBeInTheDocument();
    expect(screen.getByText(userReadFixture.role)).toBeInTheDocument();
  });

  it("never renders the access or refresh token", () => {
    renderWithProviders(<Topbar title="Dashboard" />);

    expect(document.body.innerHTML).not.toContain(REAL_ACCESS_TOKEN);
    expect(document.body.innerHTML).not.toContain(REAL_REFRESH_TOKEN);
  });

  it("logging out clears the session", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Topbar title="Dashboard" />);

    await user.click(screen.getByRole("button", { name: "Log out" }));

    expect(useAuthStore.getState().status).toBe("unauthenticated");
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it("does not show a user menu when unauthenticated", () => {
    useAuthStore.setState({ status: "unauthenticated", user: null, accessToken: null, refreshToken: null });
    renderWithProviders(<Topbar title="Dashboard" />);

    expect(screen.queryByRole("button", { name: "Log out" })).not.toBeInTheDocument();
  });
});