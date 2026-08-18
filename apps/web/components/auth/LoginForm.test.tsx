import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LoginForm } from "./LoginForm";

const push = vi.fn();
const refresh = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
  useSearchParams: () => new URLSearchParams(),
}));

const originalFetch = global.fetch;

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
  push.mockClear();
  refresh.mockClear();
});

afterEach(() => {
  global.fetch = originalFetch;
  vi.unstubAllEnvs();
});

function fillAndSubmit(email: string, password: string) {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: /log in/i }));
}

describe("LoginForm", () => {
  it("redirects to /findings on a successful login", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "1", email: "a@example.com", display_name: "A" }), {
        status: 200,
      }),
    );
    render(<LoginForm />);

    fillAndSubmit("a@example.com", "correct password");

    await waitFor(() => expect(push).toHaveBeenCalledWith("/findings"));
  });

  it("shows the API's error message on a failed login without navigating", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Invalid email or password" }), { status: 401 }),
    );
    render(<LoginForm />);

    fillAndSubmit("a@example.com", "wrong password");

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
    expect(push).not.toHaveBeenCalled();
  });
});
