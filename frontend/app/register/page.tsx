import type { Metadata } from "next";

import { LoginForm } from "@/components/auth/LoginForm";
import styles from "@/components/auth/auth.module.css";

export const metadata: Metadata = {
  title: "Dang ky | ParkSmart AI",
  description: "Dang ky tai khoan nguoi dung ParkSmart AI.",
};

export default function RegisterPage() {
  return (
    <main className={styles.loginPage}>
      <LoginForm />
    </main>
  );
}
