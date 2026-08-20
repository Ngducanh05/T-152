"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { roleHome } from "@/lib/auth";
import { useAuth } from "./AuthProvider";
import styles from "./auth.module.css";

export function LoginForm() {
  const router = useRouter();
  const { status, profile, initializationError, signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status === "authenticated" && profile) {
      router.replace(roleHome(profile.role));
    }
  }, [profile, router, status]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      const result = await signIn(email, password);
      if (!result.profile) {
        setError(result.error ?? "Không thể đăng nhập.");
        return;
      }
      router.replace(roleHome(result.profile.role));
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  if (status === "loading" || (status === "authenticated" && profile)) {
    return (
      <div className={styles.loginCard} role="status">
        <strong>ParkSmart AI</strong>
        <p>Đang xác minh phiên đăng nhập…</p>
      </div>
    );
  }

  return (
    <form className={styles.loginCard} onSubmit={(event) => void submit(event)}>
      <div className={styles.loginHeading}>
        <span className={styles.logoMark} aria-hidden="true">P</span>
        <div>
          <h1>Đăng nhập ParkSmart</h1>
          <p>Sử dụng tài khoản đã được quản trị viên cấp.</p>
        </div>
      </div>

      <label className={styles.field}>
        <span>Email</span>
        <input
          type="email"
          name="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          disabled={pending}
        />
      </label>

      <label className={styles.field}>
        <span>Mật khẩu</span>
        <input
          type="password"
          name="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          disabled={pending}
        />
      </label>

      {(error || initializationError) && (
        <p className={styles.loginError} role="alert">
          {error ?? initializationError}
        </p>
      )}

      <button className={styles.loginButton} type="submit" disabled={pending}>
        {pending ? "Đang đăng nhập…" : "Đăng nhập"}
      </button>

      <p className={styles.securityNote}>
        Vai trò được xác định bởi backend ParkSmart; màn hình này không cho phép chọn quyền.
      </p>
    </form>
  );
}
