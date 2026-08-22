"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useAuth } from "./AuthProvider";
import { roleHome, type AppRole } from "@/lib/auth";
import styles from "./auth.module.css";

export function ProtectedRoute({
  requiredRole,
  children,
}: {
  requiredRole: AppRole;
  children: ReactNode;
}) {
  const router = useRouter();
  const { status, profile, initializationError } = useAuth();

  useEffect(() => {
    if (status === "guest") {
      router.replace("/login");
      return;
    }
    if (status === "authenticated" && profile && profile.role !== requiredRole) {
      router.replace(roleHome(profile.role));
    }
  }, [profile, requiredRole, router, status]);

  const allowed =
    status === "authenticated" && profile?.role === requiredRole;
  if (allowed) return <>{children}</>;

  return (
    <main className={styles.guardState} role="status" aria-live="polite">
      <div className={styles.guardCard}>
        <strong>ParkSmart AI</strong>
        <p>
          {initializationError && status === "guest"
            ? initializationError
            : "Dang xac minh phien dang nhap..."}
        </p>
      </div>
    </main>
  );
}
