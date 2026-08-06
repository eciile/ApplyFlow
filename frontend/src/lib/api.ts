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
