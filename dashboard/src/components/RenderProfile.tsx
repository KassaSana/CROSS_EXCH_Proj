import { Profiler, type ProfilerOnRenderCallback, type ReactNode } from "react";

declare global {
  interface Window {
    __arbProfile?: {
      samples: [string, number, number, number][];
      dropped: number;
    };
  }
}

const recordRender: ProfilerOnRenderCallback = (id, _phase, actual, base, _start, commit) => {
  const profile = window.__arbProfile;
  if (!profile) return;
  if (profile.samples.length < 200_000) {
    profile.samples.push([id, actual, base, commit]);
  } else {
    profile.dropped += 1;
  }
};

/** Callbacks are enabled only in the opt-in production profiling build. */
export function RenderProfile({ id, children }: { id: string; children: ReactNode }) {
  return import.meta.env.MODE === "profile"
    ? <Profiler id={id} onRender={recordRender}>{children}</Profiler>
    : <>{children}</>;
}
