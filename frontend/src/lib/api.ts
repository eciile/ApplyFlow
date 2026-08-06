const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL;

export const API_BASE_URL =
  configuredApiBaseUrl?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

export type HealthResponse = {
  status: string;
};

export type Job = {
  id: number;
  title: string | null;
  company: string | null;
  location: string | null;
  employment_types: string[];
  source_url: string;
  application_url?: string | null;
  description?: string | null;
  required_skills?: string[];
  preferred_skills?: string[];
  qualifications?: string[];
  soft_skills?: string[];
  languages?: string[];
  created_at?: string;
};

export type JobImportResponse = {
  created: boolean;
  job: Job;
};

type ApiErrorBody = {
  detail?: string;
};

async function getErrorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    return body.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export async function getHealth(
  signal?: AbortSignal,
): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`, {
    headers: {
      Accept: "application/json",
    },
    signal,
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }

  return response.json() as Promise<HealthResponse>;
}

export async function getJobs(signal?: AbortSignal): Promise<Job[]> {
  const response = await fetch(`${API_BASE_URL}/jobs`, {
    headers: {
      Accept: "application/json",
    },
    signal,
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }

  return response.json() as Promise<Job[]>;
}

export async function getJob(
  jobId: number,
  signal?: AbortSignal,
): Promise<Job> {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}`, {
    headers: {
      Accept: "application/json",
    },
    signal,
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }

  return response.json() as Promise<Job>;
}

export async function importJob(url: string): Promise<JobImportResponse> {
  const response = await fetch(`${API_BASE_URL}/jobs/import`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ url }),
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }

  return response.json() as Promise<JobImportResponse>;
}

export type JobMatchResult = {
  job_id: number;
  profile_id: number;
  score: number;
  recommendation: string;

  matching_required_skills: string[];
  missing_required_skills: string[];
  matching_preferred_skills: string[];
  missing_preferred_skills: string[];

  location_match: boolean | null;
  location_distance_km: number | null;
  maximum_commute_distance_km: number | null;
  location_match_method: string;

  employment_type_match: boolean | null;

  required_skills_score?: number | null;
  preferred_skills_score?: number | null;
  location_score?: number | null;
  employment_type_score?: number | null;
};

export async function calculateJobMatch(
  jobId: number,
): Promise<JobMatchResult> {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/match`, {
    method: "POST",
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }

  return response.json() as Promise<JobMatchResult>;
}

export type CandidateLanguage = {
  name: string;
  level: string | null;
};

export type CandidateProfile = {
  id?: number;
  full_name: string | null;
  headline: string | null;
  location: string | null;
  latitude: number | null;
  longitude: number | null;
  max_commute_distance_km: number;
  years_of_experience: number | null;
  skills: string[];
  languages: CandidateLanguage[];
  preferred_locations: string[];
  preferred_employment_types: string[];
};

export async function getProfile(
  signal?: AbortSignal,
): Promise<CandidateProfile | null> {
  const response = await fetch(`${API_BASE_URL}/profile`, {
    headers: {
      Accept: "application/json",
    },
    signal,
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }

  return response.json() as Promise<CandidateProfile>;
}

export async function saveProfile(
  profile: CandidateProfile,
): Promise<CandidateProfile> {
  const response = await fetch(`${API_BASE_URL}/profile`, {
    method: "PUT",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(profile),
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }

  return response.json() as Promise<CandidateProfile>;
}

export type ApplicationStatus =
  | "saved"
  | "preparing"
  | "applied"
  | "interview"
  | "offer"
  | "rejected"
  | "withdrawn";

export type ApplicationListItem = {
  application_id: number;
  job_id: number;
  job_title: string | null;
  company: string | null;
  status: ApplicationStatus;
  applied_at: string | null;
  follow_up_at: string | null;
  last_follow_up_sent_at: string | null;
  last_activity_at: string;
  last_employer_response_at: string | null;
  next_action: string | null;
  days_without_response: number | null;
  possibly_ghosted: boolean;
  ghosting_threshold_days: number;
};

export async function getApplications(
  signal?: AbortSignal,
): Promise<ApplicationListItem[]> {
  const response = await fetch(`${API_BASE_URL}/applications`, {
    headers: {
      Accept: "application/json",
    },
    signal,
  });

  if (!response.ok) {
    throw new Error(await getErrorMessage(response));
  }

  return response.json() as Promise<ApplicationListItem[]>;
}