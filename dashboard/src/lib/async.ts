/** Loading, ready and failed are three distinct states and must render distinctly. */
export type Async<T> =
  | { state: "loading" }
  | { state: "ready"; data: T }
  | { state: "failed"; error: string };

export function loading<T>(): Async<T> {
  return { state: "loading" };
}

export function ready<T>(data: T): Async<T> {
  return { state: "ready", data };
}

export function failed<T>(error: unknown): Async<T> {
  return {
    state: "failed",
    error: error instanceof Error ? error.message : "Request failed",
  };
}
