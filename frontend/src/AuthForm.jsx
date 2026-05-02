import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL;

const jsonOpts = {
  credentials: "include",
  headers: { "Content-Type": "application/json" },
};

/**
 * @param {{ onAuthed: (user: { id: number; email: string }) => void }} props
 */
export default function AuthForm({ onAuthed }) {
  const [mode, setMode] = useState("login"); // 'login' | 'register'
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const path = mode === "login" ? "/auth/login" : "/auth/register";
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        ...jsonOpts,
        method: "POST",
        body: JSON.stringify({ email: email.trim(), password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const d = data.detail;
        const msg =
          typeof d === "string"
            ? d
            : Array.isArray(d)
              ? d.map((x) => x.msg || JSON.stringify(x)).join("; ")
              : "Authentication failed";
        throw new Error(msg);
      }
      onAuthed({ id: data.id, email: data.email });
      setPassword("");
    } catch (err) {
      setError(err.message || "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="w-full max-w-md rounded-2xl border border-gray-200 bg-white p-6 text-left shadow-sm">
      <h2 className="text-lg font-semibold text-black mb-1">
        {mode === "login" ? "Sign in" : "Create account"}
      </h2>
      <p className="text-xs text-gray-500 mb-4">
        An account binds your AWS CloudFormation connection across sessions.
      </p>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-gray-700">Email</span>
          <input
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded-lg border border-gray-200 px-3 py-2 text-black text-sm"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-gray-700">Password</span>
          <input
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            required
            minLength={mode === "register" ? 8 : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-lg border border-gray-200 px-3 py-2 text-black text-sm"
          />
        </label>
        {error ? (
          <p className="text-xs text-red-600 bg-red-50 rounded-lg px-2 py-1.5">
            {error}
          </p>
        ) : null}
        <button
          type="submit"
          disabled={loading}
          className="mt-2 w-full rounded-full bg-black text-white py-2.5 text-sm font-medium hover:bg-gray-800 disabled:opacity-50"
        >
          {loading ? "Please wait…" : mode === "login" ? "Sign in" : "Register"}
        </button>
      </form>
      <p className="text-xs text-gray-500 mt-4 text-center">
        {mode === "login" ? (
          <>
            No account?{" "}
            <button
              type="button"
              className="text-[#5c5fba] underline"
              onClick={() => {
                setMode("register");
                setError(null);
              }}
            >
              Register
            </button>
          </>
        ) : (
          <>
            Already have an account?{" "}
            <button
              type="button"
              className="text-[#5c5fba] underline"
              onClick={() => {
                setMode("login");
                setError(null);
              }}
            >
              Sign in
            </button>
          </>
        )}
      </p>
    </div>
  );
}

