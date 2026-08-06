import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";

import {
  getApplications,
  getJobs,
  type ApplicationListItem,
  type Job,
} from "../lib/api";

function formatDate(value: string | null): string {
  if (!value) {
    return "No date set";
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
  }).format(new Date(`${value}T00:00:00`));
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatStatus(value: string): string {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function DashboardPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [applications, setApplications] = useState<
    ApplicationListItem[]
  >([]);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function loadDashboard() {
      try {
        const [loadedJobs, loadedApplications] = await Promise.all([
          getJobs(controller.signal),
          getApplications(controller.signal),
        ]);

        setJobs(loadedJobs);
        setApplications(loadedApplications);
      } catch (loadError) {
        if (
          loadError instanceof DOMException &&
          loadError.name === "AbortError"
        ) {
          return;
        }

        setError(
          loadError instanceof Error
            ? loadError.message
            : "Could not load the dashboard.",
        );
      } finally {
        setIsLoading(false);
      }
    }

    void loadDashboard();

    return () => {
      controller.abort();
    };
  }, []);

  const awaitingResponseCount = applications.filter(
    (application) =>
      application.status === "applied" &&
      application.last_employer_response_at === null,
  ).length;

  const interviewCount = applications.filter(
    (application) => application.status === "interview",
  ).length;

  const priorityApplications = useMemo(
    () =>
      applications
        .filter(
          (application) =>
            application.next_action ||
            application.follow_up_at ||
            application.possibly_ghosted,
        )
        .sort((left, right) => {
          if (left.possibly_ghosted !== right.possibly_ghosted) {
            return left.possibly_ghosted ? -1 : 1;
          }

          if (!left.follow_up_at) {
            return 1;
          }

          if (!right.follow_up_at) {
            return -1;
          }

          return left.follow_up_at.localeCompare(right.follow_up_at);
        })
        .slice(0, 5),
    [applications],
  );

  const recentApplications = useMemo(
    () =>
      [...applications]
        .sort(
          (left, right) =>
            new Date(right.last_activity_at).getTime() -
            new Date(left.last_activity_at).getTime(),
        )
        .slice(0, 5),
    [applications],
  );

  const summaryCards = [
    {
      label: "Saved jobs",
      value: jobs.length,
      description: "Imported job opportunities",
    },
    {
      label: "Applications",
      value: applications.length,
      description: "Applications being tracked",
    },
    {
      label: "Awaiting response",
      value: awaitingResponseCount,
      description: "Applied without an employer reply",
    },
    {
      label: "Interviews",
      value: interviewCount,
      description: "Active interview processes",
    },
  ];

  if (isLoading) {
    return (
      <article className="panel">
        <div className="empty-state">
          <strong>Loading dashboard…</strong>
          <p>Retrieving your JobMatch workspace.</p>
        </div>
      </article>
    );
  }

  return (
    <section>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Overview</span>
          <h1>Dashboard</h1>
          <p>
            Review your jobs, applications, follow-ups, and recent
            activity.
          </p>
        </div>

        <Link className="primary-button button-link" to="/jobs">
          Import a job
        </Link>
      </div>

      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}

      <div className="summary-grid">
        {summaryCards.map((card) => (
          <article className="summary-card" key={card.label}>
            <span>{card.label}</span>
            <strong>{card.value}</strong>
            <p>{card.description}</p>
          </article>
        ))}
      </div>

      <div className="dashboard-grid">
        <article className="panel dashboard-panel">
          <div className="panel-heading dashboard-panel-heading">
            <div>
              <span className="eyebrow">Next actions</span>
              <h2>Application priorities</h2>
            </div>

            <Link className="secondary-link" to="/applications">
              View all
            </Link>
          </div>

          {priorityApplications.length === 0 ? (
            <div className="empty-state">
              <strong>No application actions yet</strong>
              <p>
                Follow-ups and interview preparation tasks will appear
                here.
              </p>
            </div>
          ) : (
            <div className="dashboard-list">
              {priorityApplications.map((application) => (
                <Link
                  className="dashboard-list-item"
                  to={`/jobs/${application.job_id}`}
                  key={application.application_id}
                >
                  <div>
                    <strong>
                      {application.job_title || "Untitled position"}
                    </strong>

                    <span>
                      {application.company || "Unknown company"}
                    </span>
                  </div>

                  <div className="dashboard-list-meta">
                    {application.possibly_ghosted && (
                      <span className="dashboard-warning">
                        Possible ghosting
                      </span>
                    )}

                    <span>
                      {application.next_action ||
                        `Follow up: ${formatDate(
                          application.follow_up_at,
                        )}`}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </article>

        <article className="panel dashboard-panel">
          <div className="panel-heading dashboard-panel-heading">
            <div>
              <span className="eyebrow">Recent activity</span>
              <h2>Latest updates</h2>
            </div>
          </div>

          {recentApplications.length === 0 ? (
            <div className="empty-state">
              <strong>No recent activity</strong>
              <p>Import and track a job to begin your history.</p>
            </div>
          ) : (
            <div className="dashboard-list">
              {recentApplications.map((application) => (
                <Link
                  className="dashboard-list-item"
                  to={`/jobs/${application.job_id}`}
                  key={application.application_id}
                >
                  <div>
                    <strong>
                      {application.job_title || "Untitled position"}
                    </strong>

                    <span>
                      {application.company || "Unknown company"}
                    </span>
                  </div>

                  <div className="dashboard-list-meta">
                    <span
                      className={`status-badge status-${application.status}`}
                    >
                      {formatStatus(application.status)}
                    </span>

                    <span>
                      {formatDateTime(application.last_activity_at)}
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </article>
      </div>
    </section>
  );
}

export default DashboardPage;