import { notFound } from "next/navigation";
import { StatusCheck } from "./status-check";

export const metadata = {
  title: "Dev: API status — Signal Foundry",
};

/**
 * Dev-only view of the backend's /health and /ready endpoints. Not a
 * product surface — guarded out of production builds entirely.
 */
export default function DevStatusPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return (
    <>
      <div className="appPageHeader">
        <h1>API status</h1>
        <p>Development-only check of the backend&apos;s /health and /ready endpoints against the configured API URL.</p>
      </div>
      <StatusCheck />
    </>
  );
}
