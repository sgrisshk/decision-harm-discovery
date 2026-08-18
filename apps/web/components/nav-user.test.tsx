import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NavUser } from "./nav-user";

const originalFetch = global.fetch;

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
});

afterEach(() => {
  global.fetch = originalFetch;
  vi.unstubAllEnvs();
});

describe("NavUser", () => {
  it("shows a Log in link when nobody is authenticated", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not authenticated" }), { status: 401 }),
    );
    render(<NavUser />);

    expect(await screen.findByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
  });

  it("shows the logged-in user's email and a working logout button", async () => {
    global.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ id: "1", email: "reviewer@example.com", display_name: "Reviewer" }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    render(<NavUser />);

    expect(await screen.findByText("reviewer@example.com")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() => expect(screen.getByRole("link", { name: "Log in" })).toBeInTheDocument());
  });
});
