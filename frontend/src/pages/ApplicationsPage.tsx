import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";

import {
  getApplications,
  type ApplicationListItem,
  type ApplicationStatus,
} from "../lib/api";

type StatusFilter = "all" | ApplicationStatus;

const statusLabels: Record<ApplicationStatus, string> = {
  saved: "Saved",
  preparing: "Preparing",
  applied: "Applied",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

const statusOptions: StatusFilter[] = [
  "all",
  "saved",
  "preparing",
  "applied",
  "interview",
  "offer",
  "rejected",
  "withdrawn",
];

function formatDate(value: string | null): string {
  if (!value) {
    return "Not set";
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

function ApplicationsPage() {
  const [applications, setApplications] = useState<
    ApplicationListItem[]
  >([]);
  const [statusFilter, setStatusFilter] =
    useState<StatusFilter>("all");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function loadApplications() {
      try {
        const loadedApplications = await getApplications(
          controller.signal,
        );

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
            : "Could not load applications.",
        );
      } finally {
        setIsLoading(false);
      }
    }

    void loadApplications();

    return () => {
      controller.abort();
    };
  }, []);

  const filteredApplications = useMemo(() => {
    if (statusFilter === "all") {
      return applications;
    }

    return applications.filter(
      (application) => application.status === statusFilter,
    );
  }, [applications, statusFilter]);

  return (
    <section>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Pipeline</span>
          <h1>Applications</h1>
          <p>
            Track statuses, employer responses, follow-ups, and next
            actions.
          </p>
        </div>
      </div>

      <div className="application-toolbar">
        <label className="filter-field">
          <span>Status</span>

          <select
            value={statusFilter}
            onChange={(event) =>
              setStatusFilter(event.target.value as StatusFilter)
            }
          >
            {statusOptions.map((status) => (
              <option value={status} key={status}>
                {status === "all"
                  ? "All statuses"
                  : statusLabels[status]}
              </option>
            ))}
          </select>
        </label>

        <span className="result-count">
          {filteredApplications.length} application
          {filteredApplications.length === 1 ? "" : "s"}
        </span>
      </div>

      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}

      {isLoading ? (
        <article className="panel">
          <div className="empty-state">
            <strong>Loading applications…</strong>
            <p>Retrieving your JobMatch application pipeline.</p>
          </div>
        </article>
      ) : filteredApplications.length === 0 ? (
        <article className="panel">
          <div className="empty-state">
            <strong>No applications found</strong>
            <p>
              Track an imported job or choose a different status
              filter.
            </p>
          </div>
        </article>
      ) : (
        <div className="application-list">
          {filteredApplications.map((application) => (
            <article
              className="application-card"
              key={application.application_id}
            >
              <div className="application-card-header">
                <div>
                  <span className="application-company">
                    {application.company || "Unknown company"}
                  </span>

                  <h2>
                    {application.job_title || "Untitled position"}
                  </h2>
                </div>

                <span
                  className={`status-badge status-${application.status}`}
                >
                  {statusLabels[application.status]}
                </span>
              </div>

              {application.possibly_ghosted && (
                <div className="ghosting-warning">
                  Possible ghosting: no response for{" "}
                  {application.days_without_response} days
                </div>
              )}

              <dl className="application-metadata">
                <div>
                  <dt>Applied</dt>
                  <dd>{formatDate(application.applied_at)}</dd>
                </div>

                <div>
                  <dt>Next follow-up</dt>
                  <dd>{formatDate(application.follow_up_at)}</dd>
                </div>

                <div>
                  <dt>Days without response</dt>
                  <dd>
                    {application.days_without_response ?? "Not applicable"}
                  </dd>
                </div>

                <div>
                  <dt>Last activity</dt>
                  <dd>
                    {formatDateTime(application.last_activity_at)}
                  </dd>
                </div>
              </dl>

              <div className="next-action">
                <span>Next action</span>
                <strong>
                  {application.next_action || "No next action set"}
                </strong>
              </div>

              <div className="application-card-actions">
                <Link
                  className="secondary-link"
                  to={`/jobs/${application.job_id}`}
                >
                  View job
                </Link>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export default ApplicationsPage;