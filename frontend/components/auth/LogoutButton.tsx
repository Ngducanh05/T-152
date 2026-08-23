"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useAuth } from "./AuthProvider";
import styles from "./auth.module.css";

export function LogoutButton() {
  const router = useRouter();
  const { signOut } = useAuth();
  const [pending, setPending] = useState(false);

  async function logout() {
    if (pending) return;
    setPending(true);
    try {
      await signOut();
      router.replace("/login");
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  return (
    <button
      type="button"
      className={styles.logoutButton}
      onClick={() => void logout()}
      disabled={pending}
    >
      {pending ? "Đang đăng xuất…" : "Đăng xuất"}
    </button>
  );
}
