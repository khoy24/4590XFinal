import { useState, useEffect, useRef } from "react";

/**
 * @param {{
 * open: boolean;
 * onClose: () => void;
 * onSubmit: (payload: { role_arn: string; session_id: string }) => Promise<void>;
 * isSubmitting: boolean;
 * errorMessage: string | null;
 * }} props
 */
export default function AWSConnectModal({
  open,
  onClose,
  onSubmit,
  isSubmitting,
  errorMessage,
}) {
  const [roleArn, setRoleArn] = useState("");
  const [awsLink, setAwsLink] = useState("");

  // unique session ID for this browser tab
  const sessionId = useRef(crypto.randomUUID());

  useEffect(() => {
    if (!open) return;

    const fetchLink = async () => {
      try {
        const response = await fetch(
          `${import.meta.env.VITE_API_URL}/generate-aws-link?user_id=${sessionId.current}`,
        );
        const data = await response.json();
        setAwsLink(data.link);
      } catch (error) {
        console.error("Failed to load AWS link", error);
      }
    };
    fetchLink();
  }, [open]);

  if (!open) return null;

  async function handleSubmit(e) {
    e.preventDefault();
    await onSubmit({
      role_arn: roleArn.trim(),
      session_id: sessionId.current,
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
          Connect AWS Account securely
        </h2>
        <p className="text-xs text-gray-500 mb-6 leading-relaxed">
          When AWS opens, scroll to the bottom, check the 'I acknowledge' box,
          and click Create stack.
        </p>

        {/* link*/}
        <div className="mb-6 flex flex-col gap-2">
          <span className="text-sm font-medium text-gray-700">
            1. Create the connection
          </span>
          <a
            href={awsLink}
            target="_blank"
            rel="noreferrer"
            className={`flex justify-center items-center w-full rounded-lg border border-gray-200 px-4 py-3 text-sm font-medium transition-colors ${
              awsLink
                ? "bg-gray-50 text-black hover:bg-gray-100"
                : "bg-gray-100 text-gray-400 cursor-not-allowed"
            }`}
          >
            {awsLink ? "Open AWS Quick-Create ↗" : "Generating secure link..."}
          </a>
        </div>

        {/* input form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4 text-sm">
          <label className="flex flex-col gap-1 text-left">
            <span className="font-medium text-gray-700">2. Paste Role ARN</span>
            <input
              type="text"
              autoComplete="off"
              value={roleArn}
              onChange={(e) => setRoleArn(e.target.value)}
              className="rounded-lg border border-gray-200 px-3 py-2 text-black focus:outline-none focus:ring-2 focus:ring-[#C1C4FF]"
              placeholder="arn:aws:iam::123456789012:role/CloudAssistant..."
              required
              disabled={isSubmitting}
            />
          </label>

          {errorMessage ? (
            <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">
              {errorMessage}
            </p>
          ) : null}

          <div className="flex gap-2 justify-end mt-4">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 rounded-full text-gray-600 hover:bg-gray-100 disabled:opacity-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !roleArn}
              className="px-4 py-2 rounded-full bg-[#C1C4FF] text-black hover:bg-[#b8b7e8] disabled:opacity-50 transition-colors font-medium"
            >
              {isSubmitting ? "Validating…" : "Connect"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
