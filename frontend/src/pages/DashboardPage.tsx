const summaryCards = [
  {
    label: "Saved jobs",
    value: "—",
    description: "Imported job opportunities",
  },
  {
    label: "Applications",
    value: "—",
    description: "Applications being tracked",
  },
  {
    label: "Awaiting response",
    value: "—",
    description: "Applications without a reply",
  },
  {
    label: "Interviews",
    value: "—",
    description: "Active interview processes",
  },
];

function DashboardPage() {
  return (
    <section>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Overview</span>
          <h1>Dashboard</h1>
          <p>
            Review your jobs, matches, applications, and upcoming actions.
          </p>
        </div>

        <button type="button" className="primary-button">
          Import a job
        </button>
      </div>

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
        <article className="panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">Next actions</span>
              <h2>Application priorities</h2>
            </div>
          </div>

          <div className="empty-state">
            <strong>No application actions yet</strong>
            <p>
              Application follow-ups and interview preparation tasks will
              appear here.
            </p>
          </div>
        </article>

        <article className="panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">Recent activity</span>
              <h2>Latest updates</h2>
            </div>
          </div>

          <div className="empty-state">
            <strong>No recent activity</strong>
            <p>Import a job to begin building your JobMatch history.</p>
          </div>
        </article>
      </div>
    </section>
  );
}

export default DashboardPage;