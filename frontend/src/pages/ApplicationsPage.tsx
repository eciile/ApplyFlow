function ApplicationsPage() {
  return (
    <section>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Pipeline</span>
          <h1>Applications</h1>
          <p>
            Track statuses, employer responses, follow-ups, and next actions.
          </p>
        </div>
      </div>

      <article className="panel">
        <div className="empty-state">
          <strong>No applications tracked</strong>
          <p>Start tracking an imported job to see it here.</p>
        </div>
      </article>
    </section>
  );
}

export default ApplicationsPage;