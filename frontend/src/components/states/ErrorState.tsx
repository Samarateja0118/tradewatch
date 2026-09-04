import type { ApiError } from "../../api/types";

/**
 * One rendering for every failure, keyed off the normalised `kind`.
 *
 * The message is chosen here rather than taken from the error, so what a user
 * reads is a decision this component owns and not whatever a server happened to
 * put in a body.
 */
const MESSAGES: Record<ApiError["kind"], string> = {
  network: "Could not reach the API. It may not be running.",
  notFound: "That briefing could not be found.",
  server: "The API is having trouble. Try again shortly.",
  unknown: "Something went wrong.",
};

export function ErrorState({ error }: { error: ApiError }) {
  return (
    <p className="state state--error" role="alert">
      {MESSAGES[error.kind]}
    </p>
  );
}
