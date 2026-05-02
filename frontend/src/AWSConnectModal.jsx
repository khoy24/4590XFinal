import { useState, useEffect, useRef } from "react";

const API_BASE = import.meta.env.VITE_API_URL;

/**
 * CloudFormation quick-create + poll + verify-role (cookie-auth user).
 *
 * @param {{
 *   open: boolean;
 *   onClose: () => void;
 *   onSubmit: () => Promise<void>;
 *   isSubmitting: boolean;
 *   errorMessage: string | null;
 *   awsRegion?: string;
 * }} props
 */
export default function AWSConnectModal({
  open,
  onClose,
  onSubmit,
  isSubmitting,
  errorMessage,
  awsRegion = "us-east-1",
}) {
  const [awsLink, setAwsLink] = useState("");
  const [isPolling, setIsPolling] = useState(false);
  const pollingIntervalRef = useRef(null);

  useEffect(() => {
    if (!open) return;

    async function fetchLink() {
      try {
        const response = await fetch(`${API_BASE}/generate-aws-link`, {
          credentials: "include",
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          setAwsLink("");
          console.error("generate-aws-link:", data.detail || response.status);
          return;
        }
        setAwsLink(data.link);
      } catch (error) {
        console.error("Failed to load AWS link", error);
      }
    }

    fetchLink();
    return () => clearInterval(pollingIntervalRef.current);
  }, [open]);

  useEffect(() => {
    if (!isPolling) return;

    pollingIntervalRef.current = setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE}/aws-status`, {
          credentials: "include",
        });
        if (response.ok) {
          const data = await response.json();
          if (data.status === "role_ready") {
            clearInterval(pollingIntervalRef.current);
            setIsPolling(false);
            await onSubmit();
          }
        }
      } catch (error) {
        console.error("Polling error:", error);
      }
    }, 3000);

    return () => clearInterval(pollingIntervalRef.current);
  }, [isPolling, onSubmit, awsRegion]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 font-mono shadow-xl text-center">
        <h2 className="text-xl font-semibold text-black mb-2">
          Connect AWS account securely
        </h2>

        {!isPolling && !isSubmitting && (
          <>
            <p className="text-sm text-gray-500 mb-2 leading-relaxed">
              We'll open AWS CloudFormation to create a secure, limited-access role
              in your account ({awsRegion}). Use the stack name{' '}
              <strong>CloudAssistant</strong> from the generated link when needed.
              Scroll to the bottom, check <strong>I acknowledge</strong>, and click{' '}
              <strong>Create stack</strong>.
            </p>
            <p className="text-xs text-gray-400 mb-4">
              Your connection persists after you log in again; you only recreate the
              stack if you revoke it in AWS or use &quot;Forget AWS&quot; here.
            </p>

            <a
              href={awsLink}
              target="_blank"
              rel="noreferrer"
              onClick={() => setIsPolling(true)}
              className={`flex justify-center items-center w-full rounded-lg px-4 py-3 text-base font-medium transition-colors ${
                awsLink
                  ? "bg-[#C1C4FF] text-black hover:bg-[#b8b7e8]"
                  : "bg-gray-100 text-gray-400 cursor-not-allowed"
              }`}
            >
              {awsLink ? "Open AWS to Connect ↗" : "Generating secure link..."}
            </a>
          </>
        )}

        {(isPolling || isSubmitting) && (
          <div className="flex flex-col items-center justify-center py-6">
            <div className="w-8 h-8 border-4 border-[#C1C4FF] border-t-transparent rounded-full animate-spin mb-4" />
            <p className="text-sm font-medium text-gray-700">
              {isSubmitting
                ? "Finalizing connection..."
                : "Waiting for AWS to create the role..."}
            </p>
            <p className="text-xs text-gray-400 mt-2">
              This usually takes about 15 seconds.
            </p>
          </div>
        )}

        {errorMessage && (
          <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2 mt-4">
            {errorMessage}
          </p>
        )}

        <div className="flex justify-center mt-6">
          <button
            type="button"
            onClick={() => {
              clearInterval(pollingIntervalRef.current);
              setIsPolling(false);
              onClose();
            }}
            disabled={isSubmitting}
            className="text-xs text-gray-400 hover:text-gray-600 underline disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
