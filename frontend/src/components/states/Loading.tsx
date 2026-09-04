export function Loading({ label = "Loading" }: { label?: string }) {
  // role="status" so a screen reader announces the wait rather than silence.
  return (
    <p className="state" role="status">
      {label}…
    </p>
  );
}
