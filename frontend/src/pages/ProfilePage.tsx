import {
  type ChangeEvent,
  type FormEvent,
  useEffect,
  useState,
} from "react";

import {
  getProfile,
  saveProfile,
  type CandidateProfile,
} from "../lib/api";

type ProfileForm = {
  fullName: string;
  headline: string;
  location: string;
  latitude: string;
  longitude: string;
  maximumCommuteDistanceKm: string;
  yearsOfExperience: string;
  skills: string;
  languages: string;
  preferredLocations: string;
  preferredEmploymentTypes: string;
};

const emptyForm: ProfileForm = {
  fullName: "",
  headline: "",
  location: "",
  latitude: "",
  longitude: "",
  maximumCommuteDistanceKm: "30",
  yearsOfExperience: "",
  skills: "",
  languages: "",
  preferredLocations: "",
  preferredEmploymentTypes: "",
};

function listToText(items: string[]): string {
  return items.join(", ");
}

function textToList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function languagesToText(
  languages: CandidateProfile["languages"],
): string {
  return languages
    .map((language) =>
      language.level
        ? `${language.name} | ${language.level}`
        : language.name,
    )
    .join("\n");
}

function textToLanguages(
  value: string,
): CandidateProfile["languages"] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [name, level] = line.split("|").map((part) => part.trim());

      return {
        name,
        level: level || null,
      };
    });
}

function nullableNumber(value: string): number | null {
  const normalizedValue = value.trim();

  if (!normalizedValue) {
    return null;
  }

  const numberValue = Number(normalizedValue);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function profileToForm(profile: CandidateProfile): ProfileForm {
  return {
    fullName: profile.full_name ?? "",
    headline: profile.headline ?? "",
    location: profile.location ?? "",
    latitude: profile.latitude?.toString() ?? "",
    longitude: profile.longitude?.toString() ?? "",
    maximumCommuteDistanceKm:
      profile.max_commute_distance_km.toString(),
    yearsOfExperience:
      profile.years_of_experience?.toString() ?? "",
    skills: listToText(profile.skills),
    languages: languagesToText(profile.languages),
    preferredLocations: listToText(profile.preferred_locations),
    preferredEmploymentTypes: listToText(
      profile.preferred_employment_types,
    ),
  };
}

function ProfilePage() {
  const [form, setForm] = useState<ProfileForm>(emptyForm);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] =
    useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function loadProfile() {
      try {
        const profile = await getProfile(controller.signal);

        if (profile) {
          setForm(profileToForm(profile));
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
            : "Could not load the profile.",
        );
      } finally {
        setIsLoading(false);
      }
    }

    void loadProfile();

    return () => {
      controller.abort();
    };
  }, []);

  function handleChange(
    event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
  ) {
    const { name, value } = event.target;

    setForm((currentForm) => ({
      ...currentForm,
      [name]: value,
    }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const maximumCommuteDistanceKm = Number(
      form.maximumCommuteDistanceKm,
    );

    if (
      !Number.isFinite(maximumCommuteDistanceKm) ||
      maximumCommuteDistanceKm < 0
    ) {
      setError("Maximum commute distance must be a positive number.");
      return;
    }

    setIsSaving(true);
    setError(null);
    setSuccessMessage(null);

    const profile: CandidateProfile = {
      full_name: form.fullName.trim() || null,
      headline: form.headline.trim() || null,
      location: form.location.trim() || null,
      latitude: nullableNumber(form.latitude),
      longitude: nullableNumber(form.longitude),
      max_commute_distance_km: maximumCommuteDistanceKm,
      years_of_experience: nullableNumber(form.yearsOfExperience),
      skills: textToList(form.skills),
      languages: textToLanguages(form.languages),
      preferred_locations: textToList(form.preferredLocations),
      preferred_employment_types: textToList(
        form.preferredEmploymentTypes,
      ),
    };

    try {
      const savedProfile = await saveProfile(profile);
      setForm(profileToForm(savedProfile));
      setSuccessMessage("Candidate profile saved.");
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Could not save the profile.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) {
    return (
      <article className="panel">
        <div className="empty-state">
          <strong>Loading profile…</strong>
          <p>Retrieving your candidate information.</p>
        </div>
      </article>
    );
  }

  return (
    <section>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Candidate information</span>
          <h1>Profile</h1>
          <p>
            Manage the skills, preferences, and location used for job
            matching.
          </p>
        </div>
      </div>

      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}

      {successMessage && (
        <div className="alert alert-success" role="status">
          {successMessage}
        </div>
      )}

      <form className="profile-form" onSubmit={handleSubmit}>
        <article className="panel profile-section">
          <div className="panel-heading">
            <span className="eyebrow">About you</span>
            <h2>Candidate details</h2>
          </div>

          <div className="form-grid">
            <label className="form-field">
              <span>Full name</span>
              <input
                name="fullName"
                value={form.fullName}
                onChange={handleChange}
                placeholder="Your name"
              />
            </label>

            <label className="form-field">
              <span>Professional headline</span>
              <input
                name="headline"
                value={form.headline}
                onChange={handleChange}
                placeholder="Junior AI Engineer"
              />
            </label>

            <label className="form-field">
              <span>Years of experience</span>
              <input
                name="yearsOfExperience"
                type="number"
                min="0"
                step="0.5"
                value={form.yearsOfExperience}
                onChange={handleChange}
              />
            </label>
          </div>
        </article>

        <article className="panel profile-section">
          <div className="panel-heading">
            <span className="eyebrow">Capabilities</span>
            <h2>Skills and languages</h2>
          </div>

          <div className="form-grid form-grid-single">
            <label className="form-field">
              <span>Skills</span>
              <textarea
                name="skills"
                value={form.skills}
                onChange={handleChange}
                rows={4}
                placeholder="Python, FastAPI, PyTorch, LLM Engineering"
              />
              <small>Separate skills with commas.</small>
            </label>

            <label className="form-field">
              <span>Languages</span>
              <textarea
                name="languages"
                value={form.languages}
                onChange={handleChange}
                rows={4}
                placeholder={"English | Professional\nFrench | Native"}
              />
              <small>
                Enter one language per line using: Language | Level
              </small>
            </label>
          </div>
        </article>

        <article className="panel profile-section">
          <div className="panel-heading">
            <span className="eyebrow">Location</span>
            <h2>Commute preferences</h2>
          </div>

          <div className="form-grid">
            <label className="form-field">
              <span>Current location</span>
              <input
                name="location"
                value={form.location}
                onChange={handleChange}
                placeholder="Cesson-Sévigné, France"
              />
            </label>

            <label className="form-field">
              <span>Latitude</span>
              <input
                name="latitude"
                type="number"
                step="any"
                value={form.latitude}
                onChange={handleChange}
              />
            </label>

            <label className="form-field">
              <span>Longitude</span>
              <input
                name="longitude"
                type="number"
                step="any"
                value={form.longitude}
                onChange={handleChange}
              />
            </label>

            <label className="form-field">
              <span>Maximum commute distance (km)</span>
              <input
                name="maximumCommuteDistanceKm"
                type="number"
                min="0"
                step="1"
                value={form.maximumCommuteDistanceKm}
                onChange={handleChange}
                required
              />
            </label>
          </div>
        </article>

        <article className="panel profile-section">
          <div className="panel-heading">
            <span className="eyebrow">Preferences</span>
            <h2>Target roles</h2>
          </div>

          <div className="form-grid form-grid-single">
            <label className="form-field">
              <span>Preferred locations</span>
              <input
                name="preferredLocations"
                value={form.preferredLocations}
                onChange={handleChange}
                placeholder="Rennes, Paris, Remote"
              />
              <small>Separate locations with commas.</small>
            </label>

            <label className="form-field">
              <span>Preferred employment types</span>
              <input
                name="preferredEmploymentTypes"
                value={form.preferredEmploymentTypes}
                onChange={handleChange}
                placeholder="PERMANENT, CONTRACT"
              />
              <small>Separate employment types with commas.</small>
            </label>
          </div>
        </article>

        <div className="form-actions">
          <button
            type="submit"
            className="primary-button"
            disabled={isSaving}
          >
            {isSaving ? "Saving…" : "Save profile"}
          </button>
        </div>
      </form>
    </section>
  );
}

export default ProfilePage;