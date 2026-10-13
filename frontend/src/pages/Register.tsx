import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    fullName: "",
    email: "",
    password: "",
    department: "",
    jobTitle: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [key]: e.target.value });

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register({
        email: form.email.trim(),
        full_name: form.fullName.trim(),
        password: form.password,
        department: form.department.trim() || undefined,
        job_title: form.jobTitle.trim() || undefined,
      });
      navigate("/", { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="center-screen">
      <form className="card login-card" onSubmit={onSubmit}>
        <h1>🛡️ Create your account</h1>
        <p className="muted">
          New accounts are created as <strong>employees</strong>. Monitoring only
          starts after you accept the consent notice in the extension.
        </p>
        <label htmlFor="fullName">Full name *</label>
        <input
          id="fullName"
          autoComplete="name"
          required
          maxLength={120}
          value={form.fullName}
          onChange={set("fullName")}
          placeholder="Jane Doe"
        />
        <label htmlFor="email">Work email *</label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          required
          value={form.email}
          onChange={set("email")}
          placeholder="you@corp.example"
        />
        <label htmlFor="password">Password *</label>
        <input
          id="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          maxLength={72}
          value={form.password}
          onChange={set("password")}
          placeholder="min. 8 characters"
        />
        <label htmlFor="department">Department</label>
        <input
          id="department"
          maxLength={120}
          value={form.department}
          onChange={set("department")}
          placeholder="Engineering"
        />
        <label htmlFor="jobTitle">Job title</label>
        <input
          id="jobTitle"
          maxLength={120}
          value={form.jobTitle}
          onChange={set("jobTitle")}
          placeholder="Software Engineer"
        />
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={busy}>
          {busy ? "Creating account…" : "Create account"}
        </button>
        <p className="muted tiny">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
