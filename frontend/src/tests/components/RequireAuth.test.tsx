import { beforeEach, describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import type { RouteObject } from "react-router-dom";
import { RequireAuth } from "@/components/Auth";
import { useAuthStore } from "@/store/authStore";
import { renderWithRouter } from "@/tests/testUtils";
import { userReadFixture } from "@/tests/mocks/fixtures";

const INITIAL_STATE = {
  status: "idle" as const,
  accessToken: null,
  refreshToken: null,
  user: null,
  error: null,
};

beforeEach(() => {
  useAuthStore.setState(INITIAL_STATE);
});

const ROUTES: RouteObject[] = [
  { path: "/login", element: <div>Login Page</div> },
  {
    element: <RequireAuth />,
    children: [{ path: "/", element: <div>Protected Content</div> }],
  },
];

describe("RequireAuth", () => {
  it("shows a loading state while idle/authenticating (session restoration in flight)", () => {
    useAuthStore.setState({ status: "authenticating" });
    renderWithRouter(ROUTES, { initialEntries: ["/"] });

    expect(screen.getByRole("status")).toHaveTextContent("Restoring your session...");
    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
    expect(screen.queryByText("Login Page")).not.toBeInTheDocument();
  });

  it("redirects unauthenticated users to /login", () => {
    useAuthStore.setState({ status: "unauthenticated" });
    renderWithRouter(ROUTES, { initialEntries: ["/"] });

    expect(screen.getByText("Login Page")).toBeInTheDocument();
    expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
  });

  it("renders the protected content for an authenticated user", () => {
    useAuthStore.setState({ status: "authenticated", user: userReadFixture, accessToken: "a", refreshToken: "r" });
    renderWithRouter(ROUTES, { initialEntries: ["/"] });

    expect(screen.getByText("Protected Content")).toBeInTheDocument();
  });
});