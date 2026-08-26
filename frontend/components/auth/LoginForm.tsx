"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { roleHome } from "@/lib/auth";
import { useAuth } from "./AuthProvider";
import styles from "./auth.module.css";

export function LoginForm({
  initialMode = "login",
}: {
  initialMode?: "login" | "register";
}) {
  const router = useRouter();
  const { status, profile, initializationError, signIn, signUp } = useAuth();
  const [mode, setMode] = useState<"login" | "register">(initialMode);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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
    setNotice(null);
    try {
      if (mode === "register") {
        if (password !== confirmPassword) {
          setError("Mật khẩu xác nhận không khớp.");
          return;
        }
        const result = await signUp({ fullName, email, password });
        if (result.confirmationRequired) {
          setNotice("Vui lòng xác nhận email trước khi đăng nhập ParkSmart.");
          return;
        }
        if (!result.profile) {
          setError(result.error ?? "Không thể đăng ký.");
          return;
        }
        router.replace(roleHome(result.profile.role));
        router.refresh();
        return;
      }

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
        <p>Đang xác minh phiên đăng nhập...</p>
      </div>
    );
  }

  return (
    <form className={styles.loginCard} onSubmit={(event) => void submit(event)}>
      <div className={styles.loginHeading}>
        <span className={styles.logoMark} aria-hidden="true">P</span>
        <div>
          <h1>{mode === "login" ? "Đăng nhập ParkSmart" : "Đăng ký ParkSmart"}</h1>
          <p>
            {mode === "login"
              ? "Sử dụng tài khoản ParkSmart của bạn."
              : "Tự đăng ký luôn tạo tài khoản người dùng."}
          </p>
        </div>
      </div>

      <div className={styles.authTabs} role="tablist" aria-label="Auth mode">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "login"}
          onClick={() => setMode("login")}
          disabled={pending}
        >
          Đăng nhập
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "register"}
          onClick={() => setMode("register")}
          disabled={pending}
        >
          Đăng ký
        </button>
      </div>

      {mode === "register" && (
        <label className={styles.field}>
          <span>Họ tên</span>
          <input
            type="text"
            name="name"
            autoComplete="name"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            required
            disabled={pending}
          />
        </label>
      )}

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
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
          disabled={pending}
        />
      </label>

      {mode === "register" && (
        <label className={styles.field}>
          <span>Xác nhận mật khẩu</span>
          <input
            type="password"
            name="confirm-password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            required
            disabled={pending}
          />
        </label>
      )}

      {(error || initializationError) && (
        <p className={styles.loginError} role="alert">
          {error ?? initializationError}
        </p>
      )}
      {notice && (
        <p className={styles.securityNote} role="status">
          {notice}
        </p>
      )}

      <button className={styles.loginButton} type="submit" disabled={pending}>
        {pending
          ? mode === "login"
            ? "Đang đăng nhập..."
            : "Đang đăng ký..."
          : mode === "login"
            ? "Đăng nhập"
            : "Đăng ký"}
      </button>
      <p className={styles.securityNote}>
        Vai trò do backend ParkSmart quyết định; màn hình này không cho phép chọn quyền.{" "}
        <Link href="/privacy">Quyền riêng tư</Link>
      </p>
    </form>
  );
}
