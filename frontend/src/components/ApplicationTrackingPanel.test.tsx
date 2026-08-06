import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ApplicationTrackingPanel from "./ApplicationTrackingPanel";
import { getJobApplication } from "../lib/api";

vi.mock("../lib/api", async () => {
  const actual =
    await vi.importActual<typeof import("../lib/api")>("../lib/api");

  return {
    ...actual,
    getJobApplication: vi.fn(),
  };
});

const mockedGetJobApplication = vi.mocked(getJobApplication);

describe("ApplicationTrackingPanel", () => {
  beforeEach(() => {
    mockedGetJobApplication.mockReset();
  });

  it("displays a possible ghosting warning", async () => {
    mockedGetJobApplication.mockResolvedValue({
      id: 1,
      job_id: 3,
      status: "applied",
      applied_at: "2026-07-01",
      follow_up_at: null,
      last_follow_up_sent_at: "2026-07-15T09:00:00",
      last_activity_at: "2026-07-15T09:00:00",
      last_employer_response_at: null,
      next_action: "Send another follow-up",
      notes: null,
      days_without_response: 24,
      possibly_ghosted: true,
      ghosting_threshold_days: 21,
      events: [],
    });

    render(<ApplicationTrackingPanel jobId={3} />);

    expect(
      await screen.findByText(
        "Possible ghosting: no employer response for 24 days.",
      ),
    ).toBeInTheDocument();
  });
});
