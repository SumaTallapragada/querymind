import { beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { RouteObject } from "react-router-dom";
import { LoginPage } from "@/pages/Login";
import { useAuthStore } from "@/store/authStore";
import { renderWithRouter } from "@/tests/testUtils";
import { server } from "@/tests/mocks/server";
import { tokenPairFixture, userReadFixture } from "@/tests/mocks/fixtures";

const INITIAL_STATE = {
  status: "unauthenticated" as const,
  accessToken: null,
  refreshToken: null,
  user: null,
  error: null,
};

beforeEach(() => {
  useAuthStore.setState(INITIAL_STATE);
});

const ROUTES: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  { path: "/", element: <div>Dashboard Home</div> },
  { path: "/diagnostics", element: <div>Diagnostics Home</div> },
];

describe("LoginPage", () => {
  it("shows validation errors and does not submit when fields are empty", async () => {
    const user = userEvent.setup();
    renderWithRouter(ROUTES, { initialEntries: ["/login"] });

    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Enter your username.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(useAuthStore.getState().status).toBe("unauthenticated");
  });

  it("logs in successfully and redirects to / by default", async () => {
    const user = userEvent.setup();
    renderWithRouter(ROUTES, { initialEntries: ["/login"] });

    await user.type(screen.getByLabelText("Username"), "alice");
    await user.type(screen.getByLabelText("Password"), "correct-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(screen.getByText("Dashboard Home")).toBeInTheDocument());
    expect(useAuthStore.getState().status).toBe("authenticated");
    expect(useAuthStore.getState().user).toEqual(userReadFixture);
  });

  it("redirects to the originally requested page after login", async () => {
    const user = userEvent.setup();
    renderWithRouter(ROUTES, {
      initialEntries: [{ pathname: "/login", state: { from: "/diagnostics" } }],
    });

    await user.type(screen.getByLabelText("Username"), "alice");
    await user.type(screen.getByLabelText("Password"), "correct-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(screen.getByText("Diagnostics Home")).toBeInTheDocument());
  });

  it("shows the backend's error message on invalid credentials and does not navigate", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(
          { detail: "Incorrect username or password.", error_type: "InvalidCredentialsError" },
          { status: 401 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithRouter(ROUTES, { initialEntries: ["/login"] });

    await user.type(screen.getByLabelText("Username"), "alice");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect username or password.");
    expect(screen.queryByText("Dashboard Home")).not.toBeInTheDocument();
    expect(useAuthStore.getState().status).toBe("unauthenticated");
  });

  it("disables the submit button while a login request is pending, preventing duplicate submits", async () => {
    let loginCallCount = 0;
    server.use(
      http.post("/api/v1/auth/login", async () => {
        loginCallCount += 1;
        await new Promise((resolve) => setTimeout(resolve, 30));
        return HttpResponse.json(tokenPairFixture);
      }),
    );
    const user = userEvent.setup();
    renderWithRouter(ROUTES, { initialEntries: ["/login"] });

    await user.type(screen.getByLabelText("Username"), "alice");
    await user.type(screen.getByLabelText("Password"), "correct-password");
    const submitButton = screen.getByRole("button", { name: "Sign in" });

    await user.click(submitButton);
    expect(submitButton).toBeDisabled();
    await user.click(submitButton);

    await waitFor(() => expect(screen.getByText("Dashboard Home")).toBeInTheDocument());
    expect(loginCallCount).toBe(1);
  });

  it("redirects immediately without showing the form if already authenticated", () => {
    useAuthStore.setState({
      status: "authenticated",
      user: userReadFixture,
      accessToken: "a",
      refreshToken: "r",
    });
    renderWithRouter(ROUTES, { initialEntries: ["/login"] });

    expect(screen.getByText("Dashboard Home")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it("never renders the access or refresh token anywhere in the DOM", async () => {
    const user = userEvent.setup();
    renderWithRouter(ROUTES, { initialEntries: ["/login"] });

    await user.type(screen.getByLabelText("Username"), "alice");
    await user.type(screen.getByLabelText("Password"), "correct-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(screen.getByText("Dashboard Home")).toBeInTheDocument());
    expect(document.body.innerHTML).not.toContain(tokenPairFixture.access_token);
    expect(document.body.innerHTML).not.toContain(tokenPairFixture.refresh_token);
  });
});