export type AppRole = "user" | "admin";

export interface AuthenticatedProfile {
  id: string;
  email: string | null;
  full_name: string | null;
  role: AppRole;
  parking_user_id: string | null;
  default_vehicle_id: string | null;
}

export type AuthStatus = "loading" | "guest" | "authenticated";

export interface ParkingIdentity {
  userId: string;
  vehicleId: string | null;
}

export function roleHome(role: AppRole) {
  return role === "admin" ? "/admin" : "/";
}
