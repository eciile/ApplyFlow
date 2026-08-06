import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import {
  calculateJobMatch,
  getJob,
  type Job,
  type JobMatchResult,
} from "../lib/api";
import ApplicationTrackingPanel from "../components/ApplicationTrackingPanel";

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

type MatchSkillGroupProps = {
  title: string;
  items: string[];
  positive?: boolean;
};

function MatchSkillGroup({
  title,
  items,
  positive = false,
}: MatchSkillGroupProps) {
  return (
    <section className="match-skill-group">
      <h3>{title}</h3>

      {items.length > 0 ? (
        <div className="tag-list">
          {items.map((item) => (
            <span
              className={
                positive
                  ? "match-tag match-tag-positive"
                  : "match-tag match-tag-missing"
              }
              key={item}
            >
              {item}
            </span>
          ))}
        </div>
      ) : (
        <p className="muted-text">None</p>
      )}
    </section>
  );
}

type CompatibilityItemProps = {
  label: string;
  value: string;
  matched: boolean | null;
};

function CompatibilityItem({
  label,
  value,
  matched,
}: CompatibilityItemProps) {
  const className =
    matched === true
      ? "compatibility-item compatibility-positive"
      : matched === false
        ? "compatibility-item compatibility-negative"
        : "compatibility-item compatibility-unknown";

  return (
    <div className={className}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatRecommendation(value: string): string {
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatCompatibility(value: boolean | null): string {
  if (value === true) {
    return "Compatible";
  }

  if (value === false) {
    return "Not compatible";
  }

  return "Unavailable";
}

function formatLocationMatch(result: JobMatchResult): string {
  if (
    result.location_match_method === "distance" &&
    result.location_distance_km !== null
  ) {
    return `${result.location_distance_km.toFixed(1)} km away`;
  }

  if (result.location_match_method === "remote") {
    return "Remote compatible";
  }

  return formatCompatibility(result.location_match);
}

function JobDetailsPage() {
  const { jobId } = useParams();
  const numericJobId = Number(jobId);

  const [job, setJob] = useState<Job | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [matchResult, setMatchResult] =
    useState<JobMatchResult | null>(null);

  const [isMatching, setIsMatching] = useState(false);
  const [matchError, setMatchError] = useState<string | null>(null);

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

  async function handleCalculateMatch() {
    setIsMatching(true);
    setMatchError(null);

    try {
      const result = await calculateJobMatch(numericJobId);
      setMatchResult(result);
    } catch (calculateError) {
      setMatchError(
        calculateError instanceof Error
          ? calculateError.message
          : "Could not calculate the match.",
      );
    } finally {
      setIsMatching(false);
    }
  }

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
              {job.employment_types.join(", ") ||
                "Employment type unavailable"}
            </span>
          </div>
        </div>

        <div className="job-detail-actions">
          <button
            type="button"
            className="primary-button"
            onClick={handleCalculateMatch}
            disabled={isMatching}
          >
            {isMatching ? "Calculating…" : "Calculate match"}
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

      {matchError && (
        <div className="alert alert-error" role="alert">
          {matchError}
        </div>
      )}

      {matchResult && (
        <article className="match-panel">
          <div className="match-summary">
            <div
              className="match-score"
              aria-label={`Match score ${matchResult.score} out of 100`}
            >
              <strong>{matchResult.score}</strong>
              <span>/ 100</span>
            </div>

            <div>
              <span className="eyebrow">Job compatibility</span>
              <h2>{formatRecommendation(matchResult.recommendation)}</h2>
              <p>
                This score compares the job requirements with your saved
                candidate profile.
              </p>
            </div>
          </div>

          <div className="match-breakdown">
            <MatchSkillGroup
              title="Matching required skills"
              items={matchResult.matching_required_skills}
              positive
            />

            <MatchSkillGroup
              title="Missing required skills"
              items={matchResult.missing_required_skills}
            />

            <MatchSkillGroup
              title="Matching preferred skills"
              items={matchResult.matching_preferred_skills}
              positive
            />

            <MatchSkillGroup
              title="Missing preferred skills"
              items={matchResult.missing_preferred_skills}
            />
          </div>

          <div className="compatibility-grid">
            <CompatibilityItem
              label="Location"
              value={formatLocationMatch(matchResult)}
              matched={matchResult.location_match}
            />

            <CompatibilityItem
              label="Employment type"
              value={formatCompatibility(matchResult.employment_type_match)}
              matched={matchResult.employment_type_match}
            />
          </div>
        </article>
      )}

      <ApplicationTrackingPanel jobId={job.id} />

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
