import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ApplicationsPage from "./ApplicationsPage";
import { getApplications } from "../lib/api";

vi.mock("../lib/api", async () => {
  const actual =
    await vi.importActual<typeof import("../lib/api")>("../lib/api");

  return {
    ...actual,
    getApplications: vi.fn(),
  };
});

const mockedGetApplications = vi.mocked(getApplications);

describe("ApplicationsPage", () => {
  beforeEach(() => {
    mockedGetApplications.mockReset();
  });

  it("shows a ghosting warning only for flagged applications", async () => {
    mockedGetApplications.mockResolvedValue([
      {
        application_id: 1,
        job_id: 3,
        job_title: "AI Engineer",
        company: "DataDome",
        status: "applied",
        applied_at: "2026-07-01",
        follow_up_at: null,
        last_follow_up_sent_at: null,
        last_activity_at: "2026-07-25T10:00:00",
        last_employer_response_at: null,
        next_action: "Send another follow-up",
        days_without_response: 24,
        possibly_ghosted: true,
        ghosting_threshold_days: 21,
      },
      {
        application_id: 2,
        job_id: 4,
        job_title: "Backend Engineer",
        company: "Example Company",
        status: "interview",
        applied_at: "2026-07-10",
        follow_up_at: null,
        last_follow_up_sent_at: null,
        last_activity_at: "2026-07-20T10:00:00",
        last_employer_response_at: "2026-07-20T10:00:00",
        next_action: "Prepare for interview",
        days_without_response: null,
        possibly_ghosted: false,
        ghosting_threshold_days: 21,
      },
    ]);

    render(
      <MemoryRouter>
        <ApplicationsPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { name: "AI Engineer" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Possible ghosting: no response for 24 days"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Possible ghosting: no response for null days/i),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Backend Engineer" }),
    ).toBeInTheDocument();
  });

  it("shows the empty state when no applications exist", async () => {
    mockedGetApplications.mockResolvedValue([]);

    render(
      <MemoryRouter>
        <ApplicationsPage />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("No applications found"),
    ).toBeInTheDocument();
  });

  it("shows an API error", async () => {
    mockedGetApplications.mockRejectedValue(
      new Error("Could not reach JobMatch API"),
    );

    render(
      <MemoryRouter>
        <ApplicationsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not reach JobMatch API",
    );
  });
});
