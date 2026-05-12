import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL;

/**
 * Guided S3 starter: collects inputs and requests a staged plan from the backend.
 *
 * @param {{
 *   region: string | null;
 *   disabled: boolean;
 *   onPlanCreated: (data: { plan_id: string; security_plan: string }) => void;
 * }} props
 */
export default function S3StarterCard({ region, disabled, onPlanCreated }) {
  const [bucketName, setBucketName] = useState("my-demo-bucket");
  const [enableEncryption, setEnableEncryption] = useState(true);
  const [enableVersioning, setEnableVersioning] = useState(false);
  const [blockPublicAccess, setBlockPublicAccess] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!region || disabled || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/plan-s3-starter`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          bucket_name: bucketName.trim(),
          region,
          enable_encryption: enableEncryption,
          enable_versioning: enableVersioning,
          block_public_access: blockPublicAccess,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const d = data.detail;
        const msg =
          typeof d === "string"
            ? d
            : Array.isArray(d)
              ? d.map((x) => x.msg || JSON.stringify(x)).join("; ")
              : `Request failed (${response.status})`;
        throw new Error(msg);
      }
      onPlanCreated({
        plan_id: data.plan_id,
        security_plan: data.security_plan,
      });
    } catch (err) {
      setError(err.message || "Could not create plan.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mt-6 w-full max-w-md rounded-2xl border border-gray-200 bg-gray-50/80 p-4 text-left text-xs text-gray-700 shadow-sm">
      <h3 className="text-sm font-semibold text-black mb-1">
        Guided S3 bucket starter
      </h3>
      <p className="text-[11px] text-gray-500 leading-relaxed mb-3">
        Creates an S3 bucket with security best practices. Nothing runs in AWS until you confirm the plan in the chat panel.
      </p>
      <p className="text-[11px] text-gray-600 mb-2">
        <strong>Region:</strong> {region || "— (connect AWS first)"}
      </p>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="font-medium text-gray-700">Bucket name</span>
          <input
            type="text"
            value={bucketName}
            onChange={(e) => setBucketName(e.target.value)}
            required
            disabled={disabled || submitting}
            className="rounded-lg border border-gray-200 px-3 py-2 text-black focus:outline-none focus:ring-2 focus:ring-[#C1C4FF] disabled:opacity-50"
            placeholder="e.g. my-demo-bucket"
          />
        </label>

        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={enableEncryption}
            onChange={(e) => setEnableEncryption(e.target.checked)}
            disabled={disabled || submitting}
            className="rounded border-gray-300 text-[#C1C4FF] focus:ring-[#C1C4FF]"
          />
          <span className="text-gray-700">Enable server-side encryption</span>
        </label>
        <p className="text-[10px] text-gray-500 ml-6">
          Encrypts data at rest for security.
        </p>

        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={enableVersioning}
            onChange={(e) => setEnableVersioning(e.target.checked)}
            disabled={disabled || submitting}
            className="rounded border-gray-300 text-[#C1C4FF] focus:ring-[#C1C4FF]"
          />
          <span className="text-gray-700">Enable versioning</span>
        </label>
        <p className="text-[10px] text-gray-500 ml-6">
          Protects against accidental overwrites or deletions.
        </p>

        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={blockPublicAccess}
            onChange={(e) => setBlockPublicAccess(e.target.checked)}
            disabled={disabled || submitting}
            className="rounded border-gray-300 text-[#C1C4FF] focus:ring-[#C1C4FF]"
          />
          <span className="text-gray-700">Block all public access</span>
        </label>
        <p className="text-[10px] text-gray-500 ml-6">
          Prevents accidental public exposure of data.
        </p>

        {error ? (
          <p className="text-[11px] text-red-600 bg-red-50 rounded-lg px-2 py-1.5">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={disabled || !region || submitting}
          className="mt-1 w-full rounded-full bg-black text-white py-2 text-xs font-medium hover:bg-gray-800 disabled:opacity-50 transition-colors"
        >
          {submitting ? "Building plan…" : "Preview plan in chat"}
        </button>
      </form>
    </div>
  );
}