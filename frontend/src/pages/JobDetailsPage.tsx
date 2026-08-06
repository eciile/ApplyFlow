import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import { getJob, type Job } from "../lib/api";

type SkillListProps = {
  title: string;
  items?: string[];
  emptyMessage: string;
};

function SkillList({
  title,
  items = [],
  emptyMessage,
}: SkillListProps) {
  return (
    <section className="detail-section">
      <h2>{title}</h2>

      {items.length > 0 ? (
        <div className="tag-list">
          {items.map((item) => (
            <span className="detail-tag" key={item}>
              {item}
            </span>
          ))}
        </div>
      ) : (
        <p className="muted-text">{emptyMessage}</p>
      )}
    </section>
  );
}

function JobDetailsPage() {
  const { jobId } = useParams();
  const numericJobId = Number(jobId);

  const [job, setJob] = useState<Job | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!Number.isInteger(numericJobId) || numericJobId <= 0) {
      setError("Invalid job ID.");
      setIsLoading(false);
      return;
    }

    const controller = new AbortController();

    async function loadJob() {
      try {
        const loadedJob = await getJob(
          numericJobId,
          controller.signal,
        );

        setJob(loadedJob);
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
            : "Could not load the job.",
        );
      } finally {
        setIsLoading(false);
      }
    }

    void loadJob();

    return () => {
      controller.abort();
    };
  }, [numericJobId]);

  if (isLoading) {
    return (
      <article className="panel">
        <div className="empty-state">
          <strong>Loading job…</strong>
          <p>Retrieving the extracted job information.</p>
        </div>
      </article>
    );
  }

  if (error || !job) {
    return (
      <section>
        <Link className="back-link" to="/jobs">
          ← Back to jobs
        </Link>

        <div className="alert alert-error" role="alert">
          {error ?? "Job not found."}
        </div>
      </section>
    );
  }

  return (
    <section>
      <Link className="back-link" to="/jobs">
        ← Back to jobs
      </Link>

      <div className="job-detail-header">
        <div>
          <span className="eyebrow">
            {job.company || "Unknown company"}
          </span>

          <h1>{job.title || "Untitled position"}</h1>

          <div className="job-metadata">
            <span>{job.location || "Location unavailable"}</span>
            <span>
              {job.employment_types ||
                "Employment type unavailable"}
            </span>
          </div>
        </div>

        <div className="job-detail-actions">
          <button type="button" className="primary-button">
            Calculate match
          </button>

          <a
            className="secondary-button"
            href={job.application_url || job.source_url}
            target="_blank"
            rel="noreferrer"
          >
            View posting
          </a>
        </div>
      </div>

      <div className="job-detail-grid">
        <article className="panel job-description-panel">
          <section className="detail-section">
            <h2>Description</h2>

            <p className="job-description">
              {job.description || "No description was extracted."}
            </p>
          </section>
        </article>

        <aside className="panel job-requirements-panel">
          <SkillList
            title="Required skills"
            items={job.required_skills}
            emptyMessage="No required skills were extracted."
          />

          <SkillList
            title="Preferred skills"
            items={job.preferred_skills}
            emptyMessage="No preferred skills were extracted."
          />

          <SkillList
            title="Qualifications"
            items={job.qualifications}
            emptyMessage="No qualifications were extracted."
          />

          <SkillList
            title="Soft skills"
            items={job.soft_skills}
            emptyMessage="No soft skills were extracted."
          />

          <SkillList
            title="Languages"
            items={job.languages}
            emptyMessage="No language requirements were extracted."
          />
        </aside>
      </div>
    </section>
  );
}

export default JobDetailsPage;