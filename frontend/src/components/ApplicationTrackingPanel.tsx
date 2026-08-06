import {
  type FormEvent,
  useEffect,
  useState,
} from "react";

import {
  addApplicationEvent,
  getJobApplication,
  saveJobApplication,
  type ApplicationEventType,
  type ApplicationStatus,
  type JobApplication,
  type JobApplicationInput,
} from "../lib/api";

type ApplicationTrackingPanelProps = {
  jobId: number;
};

type ApplicationForm = {
  status: ApplicationStatus;
  appliedAt: string;
  followUpAt: string;
  nextAction: string;
  notes: string;
};

const emptyApplicationForm: ApplicationForm = {
  status: "saved",
  appliedAt: "",
  followUpAt: "",
  nextAction: "",
  notes: "",
};

const statusOptions: ApplicationStatus[] = [
  "saved",
  "preparing",
  "applied",
  "interview",
  "offer",
  "rejected",
  "withdrawn",
];

const eventOptions: ApplicationEventType[] = [
  "follow_up_sent",
  "employer_response",
  "interview",
  "offer",
  "rejection",
  "note_added",
];

function formatLabel(value: string): string {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return "Not recorded";
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function applicationToForm(
  application: JobApplication,
): ApplicationForm {
  return {
    status: application.status,
    appliedAt: application.applied_at ?? "",
    followUpAt: application.follow_up_at ?? "",
    nextAction: application.next_action ?? "",
    notes: application.notes ?? "",
  };
}

function ApplicationTrackingPanel({
  jobId,
}: ApplicationTrackingPanelProps) {
  const [application, setApplication] =
    useState<JobApplication | null>(null);

  const [form, setForm] =
    useState<ApplicationForm>(emptyApplicationForm);

  const [eventType, setEventType] =
    useState<ApplicationEventType>("employer_response");

  const [eventNotes, setEventNotes] = useState("");

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isAddingEvent, setIsAddingEvent] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function loadApplication() {
      try {
        const loadedApplication = await getJobApplication(
          jobId,
          controller.signal,
        );

        setApplication(loadedApplication);

        if (loadedApplication) {
          setForm(applicationToForm(loadedApplication));
        }
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
            : "Could not load application tracking.",
        );
      } finally {
        setIsLoading(false);
      }
    }

    void loadApplication();

    return () => {
      controller.abort();
    };
  }, [jobId]);

  async function refreshApplication() {
    const refreshedApplication = await getJobApplication(jobId);

    setApplication(refreshedApplication);

    if (refreshedApplication) {
      setForm(applicationToForm(refreshedApplication));
    }
  }

  async function handleSave(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    setIsSaving(true);
    setError(null);
    setMessage(null);

    const payload: JobApplicationInput = {
      status: form.status,
      applied_at: form.appliedAt || null,
      follow_up_at: form.followUpAt || null,
      next_action: form.nextAction.trim() || null,
      notes: form.notes.trim() || null,
    };

    try {
      const savedApplication = await saveJobApplication(
        jobId,
        payload,
      );

      setApplication(savedApplication);
      setForm(applicationToForm(savedApplication));
      setMessage("Application tracking saved.");
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Could not save application tracking.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  async function handleAddEvent(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    if (!application) {
      setError("Save application tracking before adding events.");
      return;
    }

    setIsAddingEvent(true);
    setError(null);
    setMessage(null);

    try {
      await addApplicationEvent(jobId, {
        event_type: eventType,
        notes: eventNotes.trim() || null,
      });

      await refreshApplication();

      setEventNotes("");
      setMessage("Application event added.");
    } catch (eventError) {
      setError(
        eventError instanceof Error
          ? eventError.message
          : "Could not add the application event.",
      );
    } finally {
      setIsAddingEvent(false);
    }
  }

  if (isLoading) {
    return (
      <article className="panel tracking-panel">
        <div className="empty-state">
          <strong>Loading application tracking…</strong>
          <p>Retrieving this job’s status and event history.</p>
        </div>
      </article>
    );
  }

  return (
    <article className="panel tracking-panel">
      <div className="panel-heading tracking-heading">
        <div>
          <span className="eyebrow">Application tracking</span>
          <h2>
            {application
              ? "Manage application"
              : "Start tracking this job"}
          </h2>
        </div>

        {application && (
          <span
            className={`status-badge status-${application.status}`}
          >
            {formatLabel(application.status)}
          </span>
        )}
      </div>

      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}

      {message && (
        <div className="alert alert-success" role="status">
          {message}
        </div>
      )}

      {application?.possibly_ghosted && (
        <div className="ghosting-warning">
          Possible ghosting: no employer response for{" "}
          {application.days_without_response} days.
        </div>
      )}

      <form className="tracking-form" onSubmit={handleSave}>
        <div className="form-grid">
          <label className="form-field">
            <span>Status</span>

            <select
              value={form.status}
              onChange={(event) =>
                setForm((currentForm) => ({
                  ...currentForm,
                  status: event.target.value as ApplicationStatus,
                }))
              }
            >
              {statusOptions.map((status) => (
                <option value={status} key={status}>
                  {formatLabel(status)}
                </option>
              ))}
            </select>
          </label>

          <label className="form-field">
            <span>Applied date</span>

            <input
              type="date"
              value={form.appliedAt}
              onChange={(event) =>
                setForm((currentForm) => ({
                  ...currentForm,
                  appliedAt: event.target.value,
                }))
              }
            />
          </label>

          <label className="form-field">
            <span>Next follow-up</span>

            <input
              type="date"
              value={form.followUpAt}
              onChange={(event) =>
                setForm((currentForm) => ({
                  ...currentForm,
                  followUpAt: event.target.value,
                }))
              }
            />
          </label>

          <label className="form-field">
            <span>Next action</span>

            <input
              value={form.nextAction}
              onChange={(event) =>
                setForm((currentForm) => ({
                  ...currentForm,
                  nextAction: event.target.value,
                }))
              }
              placeholder="Prepare for interview"
            />
          </label>
        </div>

        <label className="form-field">
          <span>Application notes</span>

          <textarea
            rows={3}
            value={form.notes}
            onChange={(event) =>
              setForm((currentForm) => ({
                ...currentForm,
                notes: event.target.value,
              }))
            }
            placeholder="Add useful context about this application"
          />
        </label>

        <div className="form-actions">
          <button
            type="submit"
            className="primary-button"
            disabled={isSaving}
          >
            {isSaving
              ? "Saving…"
              : application
                ? "Update tracking"
                : "Start tracking"}
          </button>
        </div>
      </form>

      {application && (
        <>
          <section className="tracking-summary">
            <div>
              <span>Last employer response</span>
              <strong>
                {formatDateTime(
                  application.last_employer_response_at,
                )}
              </strong>
            </div>

            <div>
              <span>Last follow-up sent</span>
              <strong>
                {formatDateTime(
                  application.last_follow_up_sent_at,
                )}
              </strong>
            </div>

            <div>
              <span>Last activity</span>
              <strong>
                {formatDateTime(application.last_activity_at)}
              </strong>
            </div>
          </section>

          <section className="event-section">
            <div className="event-section-heading">
              <div>
                <span className="eyebrow">Response history</span>
                <h3>Add an event</h3>
              </div>
            </div>

            <form
              className="event-form"
              onSubmit={handleAddEvent}
            >
              <label className="form-field">
                <span>Event type</span>

                <select
                  value={eventType}
                  onChange={(event) =>
                    setEventType(
                      event.target.value as ApplicationEventType,
                    )
                  }
                >
                  {eventOptions.map((eventOption) => (
                    <option value={eventOption} key={eventOption}>
                      {formatLabel(eventOption)}
                    </option>
                  ))}
                </select>
              </label>

              <label className="form-field event-notes-field">
                <span>Notes</span>

                <input
                  value={eventNotes}
                  onChange={(event) =>
                    setEventNotes(event.target.value)
                  }
                  placeholder="Recruiter requested interview availability"
                />
              </label>

              <button
                type="submit"
                className="secondary-button"
                disabled={isAddingEvent}
              >
                {isAddingEvent ? "Adding…" : "Add event"}
              </button>
            </form>

            {application.events.length === 0 ? (
              <div className="empty-state compact-empty-state">
                <strong>No events recorded</strong>
                <p>
                  Follow-ups and employer responses will appear here.
                </p>
              </div>
            ) : (
              <ol className="event-timeline">
                {[...application.events]
                  .sort(
                    (left, right) =>
                      new Date(right.occurred_at).getTime() -
                      new Date(left.occurred_at).getTime(),
                  )
                  .map((applicationEvent) => (
                    <li key={applicationEvent.id}>
                      <span className="event-marker" />

                      <div>
                        <div className="event-title-row">
                          <strong>
                            {formatLabel(
                              applicationEvent.event_type,
                            )}
                          </strong>

                          <time>
                            {formatDateTime(
                              applicationEvent.occurred_at,
                            )}
                          </time>
                        </div>

                        {applicationEvent.notes && (
                          <p>{applicationEvent.notes}</p>
                        )}
                      </div>
                    </li>
                  ))}
              </ol>
            )}
          </section>
        </>
      )}
    </article>
  );
}

export default ApplicationTrackingPanel;