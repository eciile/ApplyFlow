function JobsPage() {
  return (
    <section>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Opportunities</span>
          <h1>Jobs</h1>
          <p>Import jobs and review their extracted requirements.</p>
        </div>

        <button type="button" className="primary-button">
          Import a job
        </button>
      </div>

      <article className="panel">
        <div className="empty-state">
          <strong>No jobs imported</strong>
          <p>Your saved job opportunities will appear here.</p>
        </div>
      </article>
    </section>
  );
}

export default JobsPage;