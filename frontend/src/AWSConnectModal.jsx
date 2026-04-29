import { useState } from "react";

const DEFAULT_REGIONS = [
  "us-east-1",
  "us-east-2",
  "us-west-1",
  "us-west-2",
  "ca-central-1",
  "eu-west-1",
  "eu-west-2",
  "eu-central-1",
  "ap-northeast-1",
  "ap-southeast-1",
  "ap-southeast-2",
];

/**
 * @param {{
 *   open: boolean;
 *   onClose: () => void;
 *   onSubmit: (payload: {
 *     access_key: string;
 *     secret_key: string;
 *     session_token: string | null;
 *     region: string;
 *   }) => Promise<void>;
 *   isSubmitting: boolean;
 *   errorMessage: string | null;
 * }} props
 */
export default function AWSConnectModal({
  open,
  onClose,
  onSubmit,
  isSubmitting,
  errorMessage,
}) {
  const [accessKey, setAccessKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [sessionToken, setSessionToken] = useState("");
  const [region, setRegion] = useState("us-east-1");

  if (!open) return null;

  async function handleSubmit(e) {
    e.preventDefault();
    await onSubmit({
      access_key: accessKey.trim(),
      secret_key: secretKey,
      session_token: sessionToken.trim() || null,
      region: region.trim(),
    });
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="aws-modal-title"
    >
      <div className="w-full max-w-md rounded-2xl bg-white p-6 font-mono shadow-xl">
        <h2
          id="aws-modal-title"
          className="text-lg font-semibold text-black mb-1"
        >
          Connect AWS account
        </h2>
        <p className="text-xs text-gray-500 mb-4 leading-relaxed">
          Credentials are sent once to this app&apos;s backend, validated with
          AWS STS, and kept in memory only for your session. Use a{" "}
          <strong>least-privilege IAM user</strong> or temporary keys. Never use
          your root account keys.
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3 text-sm">
          <label className="flex flex-col gap-1 text-left">
            <span className="text-gray-600">Access Key ID</span>
            <input
              type="text"
              autoComplete="off"
              value={accessKey}
              onChange={(e) => setAccessKey(e.target.value)}
              className="rounded-lg border border-gray-200 px-3 py-2 text-black focus:outline-none focus:ring-2 focus:ring-[#C1C4FF]"
              required
              disabled={isSubmitting}
            />
          </label>
          <label className="flex flex-col gap-1 text-left">
            <span className="text-gray-600">Secret Access Key</span>
            <input
              type="password"
              autoComplete="off"
              value={secretKey}
              onChange={(e) => setSecretKey(e.target.value)}
              className="rounded-lg border border-gray-200 px-3 py-2 text-black focus:outline-none focus:ring-2 focus:ring-[#C1C4FF]"
              required
              disabled={isSubmitting}
            />
          </label>
          <label className="flex flex-col gap-1 text-left">
            <span className="text-gray-600">Session token (optional)</span>
            <input
              type="password"
              autoComplete="off"
              value={sessionToken}
              onChange={(e) => setSessionToken(e.target.value)}
              className="rounded-lg border border-gray-200 px-3 py-2 text-black focus:outline-none focus:ring-2 focus:ring-[#C1C4FF]"
              placeholder="Only if using temporary credentials"
              disabled={isSubmitting}
            />
          </label>
          <label className="flex flex-col gap-1 text-left">
            <span className="text-gray-600">Region</span>
            <select
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="rounded-lg border border-gray-200 px-3 py-2 text-black focus:outline-none focus:ring-2 focus:ring-[#C1C4FF]"
              disabled={isSubmitting}
            >
              {DEFAULT_REGIONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>

          {errorMessage ? (
            <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">
              {errorMessage}
            </p>
          ) : null}

          <div className="flex gap-2 justify-end mt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 rounded-full text-gray-600 hover:bg-gray-100 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-2 rounded-full bg-[#C1C4FF] text-black hover:bg-[#b8b7e8] disabled:opacity-50"
            >
              {isSubmitting ? "Validating…" : "Connect"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
