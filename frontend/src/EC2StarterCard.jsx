import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL;
const INSTANCE_TYPES = ["t3.micro", "t3.small", "t3.medium", "t3.large"];

export default function EC2StarterCard({ region, disabled, onPlanCreated }) {
  const [instanceName, setInstanceName] = useState("demo-instance");
  const [instanceType, setInstanceType] = useState("t3.micro");
  const [assignPublicIp, setAssignPublicIp] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!region || disabled || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/plan-ec2-starter`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          instance_name: instanceName.trim(),
          region,
          instance_type: instanceType,
          assign_public_ip: assignPublicIp,
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
        Guided EC2 starter
      </h3>
      <p className="text-[11px] text-gray-500 leading-relaxed mb-3">
        Creates an EC2 security group and launches a single instance. Nothing runs in AWS until you confirm the plan in the chat panel.
      </p>
      <p className="text-[11px] text-gray-600 mb-2">
        <strong>Region:</strong> {region || "— (connect AWS first)"}
      </p>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="font-medium text-gray-700">Instance name</span>
          <input
            type="text"
            value={instanceName}
            onChange={(e) => setInstanceName(e.target.value)}
            required
            disabled={disabled || submitting}
            className="rounded-lg border border-gray-200 px-3 py-2 text-black focus:outline-none focus:ring-2 focus:ring-[#C1C4FF] disabled:opacity-50"
            placeholder="e.g. demo-instance"
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="font-medium text-gray-700">Instance type</span>
          <select
            value={instanceType}
            onChange={(e) => setInstanceType(e.target.value)}
            disabled={disabled || submitting}
            className="rounded-lg border border-gray-200 px-3 py-2 text-black focus:outline-none focus:ring-2 focus:ring-[#C1C4FF] disabled:opacity-50"
          >
            {INSTANCE_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={assignPublicIp}
            onChange={(e) => setAssignPublicIp(e.target.checked)}
            disabled={disabled || submitting}
            className="rounded border-gray-300 text-[#C1C4FF] focus:ring-[#C1C4FF]"
          />
          <span className="text-gray-700">Assign public IP (default subnet)</span>
        </label>
        <p className="text-[10px] text-gray-500 ml-6">
          Public IP is only assigned if a default subnet exists in the account.
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
