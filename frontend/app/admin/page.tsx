import type { Metadata } from "next";

import { AdminDashboard } from "@/components/admin/AdminDashboard";

export const metadata: Metadata = {
  title: "Bảng điều khiển vận hành — ParkSmart AI",
  description: "Bảng điều khiển vận hành bãi xe ParkSmart AI.",
};

export default function AdminPage() {
  return <AdminDashboard />;
}
