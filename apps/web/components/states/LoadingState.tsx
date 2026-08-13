type LoadingStateProps = {
  label?: string;
};

/**
 * Reusable loading primitive. `role="status"` + `aria-live="polite"` so
 * screen readers announce it without interrupting; no visual motion beyond a
 * CSS pulse (respects `prefers-reduced-motion` globally, see styles.css).
 */
export function LoadingState({ label = "Loading…" }: LoadingStateProps) {
  return (
    <div className="stateBlock stateBlock--loading" role="status" aria-live="polite">
      <span className="stateBlock-pulse" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}
