function ProfilePage() {
  return (
    <section>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Candidate information</span>
          <h1>Profile</h1>
          <p>
            Manage the skills, preferences, and location used for job matching.
          </p>
        </div>
      </div>

      <article className="panel">
        <div className="empty-state">
          <strong>Profile form coming next</strong>
          <p>
            Your candidate profile will be loaded from the JobMatch API.
          </p>
        </div>
      </article>
    </section>
  );
}

export default ProfilePage;