import {
  type FormEvent,
  useCallback,
  useEffect,
  useState,
} from "react";

import {
  getJobs,
  importJob,
  type Job,
} from "../lib/api";

function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobUrl, setJobUrl] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isImporting, setIsImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadJobs = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    setError(null);

    try {
      const loadedJobs = await getJobs(signal);
      setJobs(loadedJobs);
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
          : "Could not load jobs.",
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();

    void loadJobs(controller.signal);

    return () => {
      controller.abort();
    };
  }, [loadJobs]);

  async function handleImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const normalizedUrl = jobUrl.trim();

    if (!normalizedUrl) {
      setError("Enter a job-posting URL.");
      return;
    }

    setIsImporting(true);
    setError(null);

    try {
      const { job: importedJob } = await importJob(normalizedUrl);

      setJobs((currentJobs) => {
        const withoutDuplicate = currentJobs.filter(
          (job) => job.id !== importedJob.id,
        );

        return [importedJob, ...withoutDuplicate];
      });

      setJobUrl("");
    } catch (importError) {
      setError(
        importError instanceof Error
          ? importError.message
          : "Could not import the job.",
      );
    } finally {
      setIsImporting(false);
    }
  }

  return (
    <section>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Opportunities</span>
          <h1>Jobs</h1>
          <p>
            Import job postings and review their extracted information.
          </p>
        </div>
      </div>

      <article className="panel import-panel">
        <form className="import-form" onSubmit={handleImport}>
          <div className="form-field">
            <label htmlFor="job-url">Job-posting URL</label>

            <input
              id="job-url"
              type="url"
              value={jobUrl}
              onChange={(event) => setJobUrl(event.target.value)}
              placeholder="https://company.com/jobs/..."
              disabled={isImporting}
              required
            />
          </div>

          <button
            type="submit"
            className="primary-button"
            disabled={isImporting}
          >
            {isImporting ? "Importing…" : "Import job"}
          </button>
        </form>

        <p className="form-help">
          Job extraction can take longer when JobMatch uses the local
          Ollama model.
        </p>
      </article>

      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}

      {isLoading ? (
        <article className="panel">
          <div className="empty-state">
            <strong>Loading jobs…</strong>
            <p>Retrieving saved opportunities from JobMatch.</p>
          </div>
        </article>
      ) : jobs.length === 0 ? (
        <article className="panel">
          <div className="empty-state">
            <strong>No jobs imported</strong>
            <p>Paste a job-posting URL above to import your first job.</p>
          </div>
        </article>
      ) : (
        <div className="jobs-grid">
          {jobs.map((job) => (
            <article className="job-card" key={job.id}>
              <div className="job-card-heading">
                <div>
                  <span className="job-company">
                    {job.company || "Unknown company"}
                  </span>

                  <h2>{job.title || "Untitled position"}</h2>
                </div>

                <span className="job-id">#{job.id}</span>
              </div>

              <div className="job-metadata">
                <span>{job.location || "Location unavailable"}</span>
                <span>
                  {job.employment_types.join(", ") ||
                    "Employment type unavailable"}
                </span>
              </div>

              <a
                className="secondary-link"
                href={job.source_url}
                target="_blank"
                rel="noreferrer"
              >
                View original posting
              </a>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export default JobsPage;
