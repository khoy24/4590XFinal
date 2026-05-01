import { useState, useRef, useEffect } from "react";
import AWSConnectModal from "./AWSConnectModal.jsx";
import VPCStarterCard from "./VPCStarterCard.jsx";

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
      pendingActions: [],
      pendingPlan: null,
    },
  ]);
  const [inputText, setInputText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [confirmingActionId, setConfirmingActionId] = useState(null);
  const [confirmingPlanId, setConfirmingPlanId] = useState(null);

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
        setAccountId(data.account_id ?? null);
        setUserArn(data.user_arn ?? null);
        setAwsRegion(data.region ?? null);

        setMessages((prev) => [
          ...prev,
          {
            role: "bot",
            text: "Successfully securely connected to AWS! What would you like to build today?",
            actionResults: null,
            pendingActions: [],
            pendingPlan: null,
          },
        ]);

        handleModalClose();
      }
    } catch {
      setConnectError("Failed to reach the server. Is the backend running?");
    } finally {
      setConnectSubmitting(false);
    }
  };

  const handleVpcPlanCreated = ({ plan_id, security_plan }) => {
    setMessages((prev) => [
      ...prev,
      {
        role: "bot",
        text: security_plan,
        actionResults: [],
        pendingActions: [],
        pendingPlan: { plan_id, status: "open" },
      },
    ]);
  };

  const handleCancelPlan = (messageIndex) => {
    setMessages((prev) =>
      prev.map((m, i) => {
        if (i !== messageIndex || m.role !== "bot" || !m.pendingPlan) return m;
        return {
          ...m,
          pendingPlan: { ...m.pendingPlan, status: "cancelled" },
        };
      }),
    );
  };

  const handleConfirmPlan = async (messageIndex, planPayload) => {
    if (
      !sessionId ||
      confirmingActionId ||
      confirmingPlanId ||
      !planPayload?.plan_id
    )
      return;
    setConfirmingPlanId(planPayload.plan_id);
    try {
      const response = await fetch(`${API_BASE}/confirm-plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          plan_id: planPayload.plan_id,
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
          setAccountId(null);
          setUserArn(null);
          setAwsRegion(null);
        }
        throw new Error(detailStr || `Confirm plan failed (${response.status}).`);
      }

      const results = data.results || [];
      const okOverall =
        results.length > 0 && results.every((r) => r.ok === true);

      setMessages((prev) => {
        const next = prev.map((m, i) => {
          if (i !== messageIndex || m.role !== "bot") return m;
          return {
            ...m,
            pendingPlan: m.pendingPlan
              ? { ...m.pendingPlan, status: "confirmed" }
              : null,
          };
        });
        return [
          ...next,
          {
            role: "bot",
            text: okOverall
              ? "VPC starter run finished. Resource details are below."
              : "VPC starter run encountered errors before completion.",
            actionResults: results,
            pendingActions: [],
            pendingPlan: null,
          },
        ];
      });
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        {
          role: "bot",
          text: err.message || "Could not confirm that plan.",
          actionResults: null,
          pendingActions: [],
          pendingPlan: null,
        },
      ]);
    } finally {
      setConfirmingPlanId(null);
    }
  };

  const confirmingBusy = !!confirmingActionId || !!confirmingPlanId;

  const handleCancelPending = (messageIndex, pa) => {
    setMessages((prev) =>
      prev.map((m, i) => {
        if (i !== messageIndex || m.role !== "bot") return m;
        return {
          ...m,
          pendingActions: (m.pendingActions || []).map((p) =>
            p.action_id === pa.action_id ? { ...p, status: "cancelled" } : p,
          ),
        };
      }),
    );
  };

  const handleConfirmPending = async (messageIndex, pa) => {
    if (!sessionId || confirmingBusy) return;
    setConfirmingActionId(pa.action_id);
    try {
      const response = await fetch(`${API_BASE}/confirm-action`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          action_id: pa.action_id,
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
          setAccountId(null);
          setUserArn(null);
          setAwsRegion(null);
        }
        throw new Error(detailStr || `Confirm failed (${response.status}).`);
      }

      const result = data.result;
      setMessages((prev) => {
        const next = prev.map((m, i) => {
          if (i !== messageIndex || m.role !== "bot") return m;
          return {
            ...m,
            pendingActions: (m.pendingActions || []).map((p) =>
              p.action_id === pa.action_id ? { ...p, status: "confirmed" } : p,
            ),
          };
        });
        const ok = result?.ok;
        const label = result
          ? `${result.service}.${result.operation}`
          : "Action";
        return [
          ...next,
          {
            role: "bot",
            text: ok
              ? `${label} completed successfully.`
              : `${label} failed: ${result?.error || "Unknown error"}`,
            actionResults: result ? [result] : [],
            pendingActions: [],
            pendingPlan: null,
          },
        ];
      });
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        {
          role: "bot",
          text: err.message || "Could not confirm that action.",
          actionResults: null,
          pendingActions: [],
          pendingPlan: null,
        },
      ]);
    } finally {
      setConfirmingActionId(null);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!inputText.trim() || awsStatus !== "connected" || !sessionId) return;

    const userMessage = {
      role: "user",
      text: inputText,
      actionResults: null,
      pendingActions: [],
      pendingPlan: null,
    };
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
          setAccountId(null);
          setUserArn(null);
          setAwsRegion(null);
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
          pendingActions: (data.pending_actions || []).map((p) => ({
            ...p,
            status: "open",
          })),
          pendingPlan: null,
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
          pendingActions: [],
          pendingPlan: null,
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

      <aside className="w-[55%] h-full flex flex-col justify-start items-center text-center pt-[5vh] px-[5vw] overflow-y-auto pb-8">
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
              : "bg-[#C1C4FF] text-black hover:bg-[#b8b7e8]"
          }`}
        >
          {awsStatus === "connected" ? "AWS Connected" : "Connect to AWS"}
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
            <strong>How it works:</strong> You create an IAM role in your account
            via the AWS CloudFormation quick-create link. The stack uses an{" "}
            <strong>ExternalId</strong> so only this app can assume that role.
            We call <strong>STS AssumeRole</strong>, store the resulting{" "}
            <strong>temporary</strong> credentials in server memory for your
            session, then run only allowlisted API calls. Delete the stack or
            role in AWS to revoke access.
          </p>
          <p>
            You never paste long-term access keys into this app — only the Role
            ARN outputs from CloudFormation.
          </p>
        </div>

        {awsStatus === "connected" && sessionId ? (
          <VPCStarterCard
            sessionId={sessionId}
            region={awsRegion}
            disabled={
              awsStatus !== "connected" || !sessionId || !awsRegion || isLoading
            }
            onPlanCreated={handleVpcPlanCreated}
          />
        ) : null}
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
                    <div className="whitespace-pre-wrap">{msg.text}</div>
                    {msg.role === "bot" && msg.actionResults?.length ? (
                      <ul className="list-none mt-3 pt-3 border-t border-black/10">
                        {formatActionResults(msg.actionResults)}
                      </ul>
                    ) : null}
                    {msg.role === "bot" &&
                    msg.pendingPlan?.status === "open" ? (
                      <div className="mt-3 pt-3 border-t border-black/10">
                        <div className="rounded-lg bg-white/90 p-3 text-left text-xs text-gray-800 ring-1 ring-black/10 space-y-2">
                          <p className="font-semibold text-amber-900">
                            Review VPC plan
                          </p>
                          <p className="text-gray-700 leading-relaxed">
                            One confirmation runs the full VPC sequence in AWS
                            (multiple API calls).
                          </p>
                          <div className="flex gap-2 justify-end pt-1">
                            <button
                              type="button"
                              disabled={confirmingBusy}
                              onClick={() => handleCancelPlan(index)}
                              className="px-3 py-1.5 rounded-full text-gray-700 bg-gray-100 hover:bg-gray-200 disabled:opacity-50 text-xs font-medium"
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              disabled={confirmingBusy}
                              onClick={() =>
                                handleConfirmPlan(index, msg.pendingPlan)
                              }
                              className="px-3 py-1.5 rounded-full text-white bg-black hover:bg-gray-800 disabled:opacity-50 text-xs font-medium"
                            >
                              {confirmingPlanId === msg.pendingPlan.plan_id
                                ? "Running…"
                                : "Confirm plan"}
                            </button>
                          </div>
                        </div>
                      </div>
                    ) : null}
                    {msg.role === "bot" &&
                    (msg.pendingActions || []).some((p) => p.status === "open") ? (
                      <div className="mt-3 pt-3 border-t border-black/10 space-y-3">
                        {(msg.pendingActions || [])
                          .filter((p) => p.status === "open")
                          .map((p) => (
                            <div
                              key={p.action_id}
                              className="rounded-lg bg-white/90 p-3 text-left text-xs text-gray-800 ring-1 ring-black/10"
                            >
                              <p className="font-semibold text-amber-900">
                                Review before running
                              </p>
                              <p className="text-gray-700 mt-1 leading-relaxed">
                                {p.risk_summary}
                              </p>
                              <pre className="mt-2 whitespace-pre-wrap break-words bg-white/80 rounded-md p-2 max-h-32 overflow-y-auto text-[11px] text-gray-900">
                                {JSON.stringify(
                                  {
                                    service: p.service,
                                    operation: p.operation,
                                    params: p.params,
                                  },
                                  null,
                                  2,
                                )}
                              </pre>
                              <div className="flex gap-2 mt-2 justify-end">
                                <button
                                  type="button"
                                  disabled={confirmingBusy}
                                  onClick={() => handleCancelPending(index, p)}
                                  className="px-3 py-1.5 rounded-full text-gray-700 bg-gray-100 hover:bg-gray-200 disabled:opacity-50 text-xs font-medium"
                                >
                                  Cancel
                                </button>
                                <button
                                  type="button"
                                  disabled={confirmingBusy}
                                  onClick={() => handleConfirmPending(index, p)}
                                  className="px-3 py-1.5 rounded-full text-white bg-black hover:bg-gray-800 disabled:opacity-50 text-xs font-medium"
                                >
                                  {confirmingActionId === p.action_id
                                    ? "Running…"
                                    : "Confirm"}
                                </button>
                              </div>
                            </div>
                          ))}
                      </div>
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
