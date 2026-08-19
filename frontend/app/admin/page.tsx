import type { Metadata } from "next";

import { AdminRoute } from "@/components/auth/AdminRoute";

export const metadata: Metadata = {
  title: "ParkSmart AI | Admin",
  description: "Dashboard vận hành ParkSmart AI",
};

export default function AdminPage() {
  return <AdminRoute />;
}
