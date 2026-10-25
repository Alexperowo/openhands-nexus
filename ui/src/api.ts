export async function requestJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const timeout = AbortSignal.timeout(15000);
  const response = await fetch(path, {
    ...options,
    signal: options.signal ? AbortSignal.any([options.signal, timeout]) : timeout,
    headers: options.headers,
  });
  if (!response.ok) throw new Error(`Сервер вернул HTTP ${response.status}`);
  return response.json();
}

export { errorMessage } from "./errors.ts";
