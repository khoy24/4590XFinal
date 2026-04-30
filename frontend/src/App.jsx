import { useState, useRef, useEffect } from "react";
import AWSConnectModal from "./AWSConnectModal.jsx";

const API_BASE = import.meta.env.VITE_API_URL;

function formatActionResults(actionResults) {
  if (!actionResults || actionResults.length === 0) return null;
  return actionResults.map((ar, i) => {
    const label = `${ar.service}.${ar.operation}`;
    if (ar.ok) {
      const preview =
        ar.result != null ? JSON.stringify(ar.result, null, 2) : "(no payload)";
      return (
        <li key={i} className="mt-1 text-xs text-left">
          <span className="font-semibold text-green-800">{label}</span>
          <pre className="mt-1 whitespace-pre-wrap break-words bg-white/60 rounded-lg p-2 max-h-36 overflow-y-auto text-gray-800">
            {preview}
          </pre>
        </li>
      );
    }
    return (
      <li key={i} className="mt-1 text-xs text-left">
        <span className="font-semibold text-red-800">{label}</span>
        <span className="block text-red-700 mt-0.5">
          {ar.error || "Failed"}
        </span>
      </li>
    );
  });
}

function App() {
  const [awsStatus, setAwsStatus] = useState("disconnected");
  const [sessionId, setSessionId] = useState(null);
  const [accountId, setAccountId] = useState(null);
  const [userArn, setUserArn] = useState(null);
  const [awsRegion, setAwsRegion] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [connectSubmitting, setConnectSubmitting] = useState(false);
  const [connectError, setConnectError] = useState(null);

  const [messages, setMessages] = useState([
    {
      role: "bot",
      text: "Hello! I am your Cloud Security Architect. Please connect your AWS account to get started.",
      actionResults: null,
    },
  ]);
  const [inputText, setInputText] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const messagesEndRef = useRef(null);
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleConnectAWS = () => {
    if (awsStatus === "connected" || connectSubmitting) return;
    setConnectError(null);
    setModalOpen(true);
  };

  const handleModalClose = () => {
    if (connectSubmitting) return;
    setModalOpen(false);
    setConnectError(null);
  };

  const handleModalSubmit = async (payload) => {
    setConnectSubmitting(true);
    console.log("Submitting ARN...", payload);

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/verify-role`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );

      const data = await response.json();

      if (!response.ok) {
        setConnectError(data.detail || "Connection failed.");
      } else {
        setConnectError(null);
        setAwsStatus("connected");
        setSessionId(payload.session_id);

        setMessages((prev) => [
          ...prev,
          {
            role: "bot",
            text: "Successfully securely connected to AWS! What would you like to build today?",
            actionResults: null,
          },
        ]);

        handleModalClose();
      }
    } catch (error) {
      setConnectError("Failed to reach the server. Is the backend running?");
    } finally {
      setConnectSubmitting(false);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!inputText.trim() || awsStatus !== "connected" || !sessionId) return;

    const userMessage = { role: "user", text: inputText, actionResults: null };
    setMessages((prev) => [...prev, userMessage]);
    setInputText("");
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: userMessage.text,
          session_id: sessionId,
        }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const detailStr = (() => {
          const d = data.detail;
          if (typeof d === "string") return d;
          if (Array.isArray(d))
            return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
          return null;
        })();

        if (response.status === 401) {
          setAwsStatus("disconnected");
          setSessionId(null);
          throw new Error(
            detailStr || "Session expired. Please connect AWS again.",
          );
        }
        throw new Error(
          detailStr || `Backend request failed (${response.status}).`,
        );
      }

      setMessages((prev) => [
        ...prev,
        {
          role: "bot",
          text: data.reply,
          actionResults: data.action_results || [],
        },
      ]);
    } catch (error) {
      console.error(error);
      setMessages((prev) => [
        ...prev,
        {
          role: "bot",
          text:
            error.message ||
            "System Error: Could not reach the backend or chat failed.",
          actionResults: null,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-screen bg-white font-mono overflow-hidden">
      <AWSConnectModal
        open={modalOpen}
        onClose={handleModalClose}
        onSubmit={handleModalSubmit}
        isSubmitting={connectSubmitting}
        errorMessage={connectError}
      />

      <aside className="w-[55%] h-full flex flex-col justify-start items-center text-center pt-[5vh] px-[5vw]">
        <div className="mb-4">
          <h1 className="text-4xl md:text-5xl font-normal text-black tracking-tight">
            Cloud Deployment Assistant
          </h1>
          <p className="text-sm text-gray-500 mt-2 tracking-widest uppercase">
            Powered by Gemini
          </p>
        </div>

        <button
          onClick={handleConnectAWS}
          className={`px-10 py-2 font-medium text-xl rounded-full transition-all duration-200 shadow-sm ${
            awsStatus === "connected"
              ? "bg-green-100 text-green-800"
              : awsStatus === "pending"
                ? "bg-yellow-100 text-yellow-800 cursor-wait"
                : "bg-[#C1C4FF] text-black hover:bg-[#b8b7e8]"
          }`}
        >
          {awsStatus === "connected"
            ? "AWS Connected"
            : awsStatus === "pending"
              ? "Connecting..."
              : "Connect to AWS"}
        </button>

        {awsStatus === "connected" && accountId ? (
          <div className="mt-4 max-w-md text-xs text-gray-600 text-left space-y-1">
            <p>
              <strong>Account:</strong> {accountId}
            </p>
            {awsRegion ? (
              <p>
                <strong>Region:</strong> {awsRegion}
              </p>
            ) : null}
            {userArn ? (
              <p className="break-all">
                <strong>ARN:</strong> {userArn}
              </p>
            ) : null}
          </div>
        ) : null}

        <div className="max-w-[300px] pt-[3vh] text-xs text-gray-400 leading-relaxed mt-2 space-y-4">
          <p>
            <strong>How it works:</strong> You enter temporary or IAM user
            credentials; we validate them with AWS STS and keep them in server
            memory only for this session. You can revoke the keys anytime from
            IAM.
          </p>
          <p>
            For class demonstration, we will use a dedicated IAM user with
            minimal permissions.
          </p>
        </div>
      </aside>

      <section className="w-[45%] h-full py-[5vh] pr-[4vw] pl-[1vw]">
        <div className="w-full h-full bg-[#F0F0F0] flex flex-col relative rounded-sm">
          <main className="flex-1 overflow-y-auto p-6 scrollbar-thin">
            <div className="flex flex-col space-y-4">
              {messages.map((msg, index) => (
                <div
                  key={index}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] px-5 py-3 rounded-2xl text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-white text-black rounded-br-none shadow-sm"
                        : msg.role === "system"
                          ? "bg-gray-200 text-gray-700 w-full text-center rounded-xl font-bold text-xs uppercase tracking-wider"
                          : "bg-[#C1C4FF] text-black rounded-bl-none shadow-sm"
                    }`}
                  >
                    <div>{msg.text}</div>
                    {msg.role === "bot" && msg.actionResults?.length ? (
                      <ul className="list-none mt-3 pt-3 border-t border-black/10">
                        {formatActionResults(msg.actionResults)}
                      </ul>
                    ) : null}
                  </div>
                </div>
              ))}
              {isLoading && (
                <div className="flex justify-start">
                  <div className="bg-white px-5 py-3 rounded-2xl rounded-bl-none text-gray-500 italic shadow-sm text-sm">
                    Processing request...
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </main>

          <footer className="p-4 w-full">
            <form
              onSubmit={handleSendMessage}
              className="flex items-end bg-white rounded-2xl overflow-hidden shadow-sm"
            >
              <textarea
                value={inputText}
                onChange={(e) => {
                  setInputText(e.target.value);
                  e.target.style.height = "auto";
                  e.target.style.height = e.target.scrollHeight + "px";
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSendMessage(e);
                  }
                }}
                placeholder="Ask to list S3 buckets, describe VPCs, etc."
                disabled={awsStatus !== "connected"}
                className="flex-1 px-5 py-4 bg-transparent text-black text-sm focus:outline-none resize-none overflow-y-auto min-h-[52px] max-h-[150px] disabled:opacity-50"
                rows={1}
              />

              <div className="p-2 flex-shrink-0">
                <button
                  type="submit"
                  disabled={
                    !inputText.trim() || awsStatus !== "connected" || isLoading
                  }
                  className="p-2 bg-[#C1C4FF] rounded-xl text-black hover:bg-[#b8b7e8] transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="20"
                    height="20"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <line x1="7" y1="17" x2="17" y2="7"></line>
                    <polyline points="7 7 17 7 17 17"></polyline>
                  </svg>
                </button>
              </div>
            </form>
          </footer>
        </div>
      </section>
    </div>
  );
}

export default App;
