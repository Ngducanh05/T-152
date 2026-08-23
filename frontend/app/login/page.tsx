import type { Metadata } from "next";

import { LoginForm } from "@/components/auth/LoginForm";
import styles from "@/components/auth/auth.module.css";

export const metadata: Metadata = {
  title: "Đăng nhập | ParkSmart AI",
  description: "Đăng nhập ParkSmart AI bằng tài khoản Supabase được cấp.",
};

export default function LoginPage() {
  return (
    <main className={styles.loginPage}>
      <LoginForm />
    </main>
  );
}
