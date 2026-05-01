import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL;

/**
 * Guided VPC starter: collects inputs and requests a staged plan from the backend.
 *
 * @param {{
 *   sessionId: string | null;
 *   region: string | null;
 *   disabled: boolean;
 *   onPlanCreated: (data: { plan_id: string; security_plan: string }) => void;
 * }} props
 */
export default function VPCStarterCard({
  sessionId,
  region,
  disabled,
  onPlanCreated,
}) {
  const [projectName, setProjectName] = useState("demo-vpc");
  const [vpcCidr, setVpcCidr] = useState("10.0.0.0/16");
  const [publicCidr, setPublicCidr] = useState("10.0.1.0/24");
  const [privateCidr, setPrivateCidr] = useState("10.0.2.0/24");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!sessionId || !region || disabled || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/plan-vpc-starter`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          project_name: projectName.trim(),
          region,
          vpc_cidr: vpcCidr.trim(),
          public_subnet_cidr: publicCidr.trim(),
          private_subnet_cidr: privateCidr.trim(),
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
        Guided VPC starter
      </h3>
      <p className="text-[11px] text-gray-500 leading-relaxed mb-3">
        Builds a VPC with public and private subnets, an Internet Gateway, and a
        public route table. Nothing runs in AWS until you confirm the plan in
        the chat panel.
      </p>
      <p className="text-[11px] text-gray-600 mb-2">
        <strong>Region:</strong> {region || "— (connect AWS first)"}
      </p>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="font-medium text-gray-700">Project name</span>
          <input
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            required
            disabled={disabled || submitting}
            className="rounded-lg border border-gray-200 px-3 py-2 text-black focus:outline-none focus:ring-2 focus:ring-[#C1C4FF] disabled:opacity-50"
            placeholder="e.g. demo-vpc"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-medium text-gray-700">VPC CIDR</span>
          <input
            type="text"
            value={vpcCidr}
            onChange={(e) => setVpcCidr(e.target.value)}
            required
            disabled={disabled || submitting}
            className="rounded-lg border border-gray-200 px-3 py-2 text-black focus:outline-none focus:ring-2 focus:ring-[#C1C4FF] disabled:opacity-50"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-medium text-gray-700">Public subnet CIDR</span>
          <input
            type="text"
            value={publicCidr}
            onChange={(e) => setPublicCidr(e.target.value)}
            required
            disabled={disabled || submitting}
            className="rounded-lg border border-gray-200 px-3 py-2 text-black focus:outline-none focus:ring-2 focus:ring-[#C1C4FF] disabled:opacity-50"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="font-medium text-gray-700">Private subnet CIDR</span>
          <input
            type="text"
            value={privateCidr}
            onChange={(e) => setPrivateCidr(e.target.value)}
            required
            disabled={disabled || submitting}
            className="rounded-lg border border-gray-200 px-3 py-2 text-black focus:outline-none focus:ring-2 focus:ring-[#C1C4FF] disabled:opacity-50"
          />
        </label>

        {error ? (
          <p className="text-[11px] text-red-600 bg-red-50 rounded-lg px-2 py-1.5">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={disabled || !sessionId || !region || submitting}
          className="mt-1 w-full rounded-full bg-black text-white py-2 text-xs font-medium hover:bg-gray-800 disabled:opacity-50 transition-colors"
        >
          {submitting ? "Building plan…" : "Preview plan in chat"}
        </button>
      </form>
    </div>
  );
}
