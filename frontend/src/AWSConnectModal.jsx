import { useState, useEffect, useRef } from "react";

export default function AWSConnectModal({
  open,
  onClose,
  onSubmit,
  isSubmitting,
  errorMessage,
}) {
  const [awsLink, setAwsLink] = useState("");
  const [isPolling, setIsPolling] = useState(false);
  const sessionId = useRef(crypto.randomUUID());
  const pollingIntervalRef = useRef(null);

  // Fetch the link when the modal opens
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

    return () => clearInterval(pollingIntervalRef.current);
  }, [open]);

  // this checks the backend every 3 seconds once the user clicks the link, looking for that role to be created with the arn
  useEffect(() => {
    if (!isPolling) return;

    pollingIntervalRef.current = setInterval(async () => {
      try {
        const response = await fetch(
          `${import.meta.env.VITE_API_URL}/aws-status?session_id=${sessionId.current}`,
        );
        if (response.ok) {
          const data = await response.json();
          // webhook success
          if (data.status === "role_ready") {
            clearInterval(pollingIntervalRef.current);
            setIsPolling(false);
            // auto submit
            await onSubmit({ session_id: sessionId.current });
          }
        }
      } catch (error) {
        console.error("Polling error:", error);
      }
    }, 3000);

    return () => clearInterval(pollingIntervalRef.current);
  }, [isPolling, onSubmit]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 font-mono shadow-xl text-center">
        <h2 className="text-xl font-semibold text-black mb-2">
          Connect AWS Account securely
        </h2>

        {/* before clicking the link */}
        {!isPolling && !isSubmitting && (
          <>
            <p className="text-sm text-gray-500 mb-6 leading-relaxed">
              We'll open AWS CloudFormation to automatically create a secure,
              limited-access role for this session. Scroll to the bottom, check{" "}
              <strong>"I acknowledge"</strong>, and click{" "}
              <strong>Create stack</strong>.
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

        {/* wiat for the webhook */}
        {(isPolling || isSubmitting) && (
          <div className="flex flex-col items-center justify-center py-6">
            <div className="w-8 h-8 border-4 border-[#C1C4FF] border-t-transparent rounded-full animate-spin mb-4"></div>
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
            className="text-xs text-gray-400 hover:text-gray-600 underline"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
