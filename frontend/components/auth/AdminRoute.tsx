"use client";

import { AdminDashboard } from "@/components/admin/AdminDashboard";

import { LogoutButton } from "./LogoutButton";
import { ProtectedRoute } from "./ProtectedRoute";
import styles from "./auth.module.css";

export function AdminRoute() {
  return (
    <ProtectedRoute requiredRole="admin">
      <div className={styles.adminAuthBar}>
        <LogoutButton />
      </div>
      <AdminDashboard />
    </ProtectedRoute>
  );
}
