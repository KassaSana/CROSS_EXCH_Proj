import { NavLink } from "react-router-dom";

const linkClasses = ({ isActive }: { isActive: boolean }): string =>
  [
    "rounded-2xl px-5 py-2 text-sm uppercase tracking-[0.25em] transition-colors",
    isActive
      ? "bg-ink text-white shadow-sm"
      : "border border-stone-300 bg-white/70 text-stone-600 hover:bg-white",
  ].join(" ");

export function Nav() {
  return (
    <nav className="mb-6 flex gap-3">
      <NavLink to="/" end className={linkClasses}>
        Dashboard
      </NavLink>
      <NavLink to="/stats" className={linkClasses}>
        Statistics
      </NavLink>
    </nav>
  );
}
