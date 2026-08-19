"use client";

import type { SupabaseClient } from "@supabase/supabase-js";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { ApiError, parkSmartApi } from "@/lib/api";
import type { AuthenticatedProfile, AuthStatus, ParkingIdentity } from "@/lib/auth";
import { MVP_DEMO_USER_ID, MVP_DEMO_VEHICLE_ID } from "@/lib/demo";
import { createBrowserSupabaseClient } from "@/lib/supabase/client";

const DEMO_PROFILE: AuthenticatedProfile = {
  id: "00000000-0000-0000-0000-000000000001",
  email: null,
  full_name: "Demo User",
  role: "user",
  parking_user_id: MVP_DEMO_USER_ID,
  default_vehicle_id: MVP_DEMO_VEHICLE_ID,
};

interface SignInResult {
  profile: AuthenticatedProfile | null;
  error: string | null;
}

interface AuthContextValue {
  status: AuthStatus;
  profile: AuthenticatedProfile | null;
  initializationError: string | null;
  signIn: (email: string, password: string) => Promise<SignInResult>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function safeProfileError(error: unknown) {
  if (error instanceof ApiError && error.status === 403) {
    return "Tài khoản đã đăng nhập nhưng chưa được cấu hình quyền ParkSmart hợp lệ.";
  }
  return "Không thể xác minh tài khoản ParkSmart. Vui lòng đăng nhập lại.";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const demoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
  const [status, setStatus] = useState<AuthStatus>(() =>
    demoMode ? "authenticated" : "loading",
  );
  const [profile, setProfile] = useState<AuthenticatedProfile | null>(() =>
    demoMode ? DEMO_PROFILE : null,
  );
  const [initializationError, setInitializationError] =
    useState<string | null>(null);
  const supabaseRef = useRef<SupabaseClient | null>(null);

  const becomeGuest = useCallback((error: string | null = null) => {
    setProfile(null);
    setInitializationError(error);
    setStatus("guest");
  }, []);

  const loadBackendProfile = useCallback(async () => {
    const currentProfile = await parkSmartApi.getCurrentUser();
    setProfile(currentProfile);
    setInitializationError(null);
    setStatus("authenticated");
    return currentProfile;
  }, []);

  useEffect(() => {
    if (demoMode) {
      parkSmartApi.setAuthProvider(null);
      return () => parkSmartApi.setAuthProvider(null);
    }

    let active = true;
    let supabase: SupabaseClient;
    try {
      supabase = createBrowserSupabaseClient();
    } catch {
      queueMicrotask(() => {
        if (active) becomeGuest("Supabase chưa được cấu hình cho frontend.");
      });
      return;
    }
    supabaseRef.current = supabase;

    parkSmartApi.setAuthProvider({
      async getAccessToken() {
        const { data, error } = await supabase.auth.getSession();
        if (error) return null;
        return data.session?.access_token ?? null;
      },
      async refreshAccessToken() {
        const { data, error } = await supabase.auth.refreshSession();
        if (error) return null;
        return data.session?.access_token ?? null;
      },
      async onAuthenticationFailure() {
        await supabase.auth.signOut();
        if (active) becomeGuest();
      },
    });

    async function bootstrap() {
      const { data, error } = await supabase.auth.getSession();
      if (!active) return;
      if (error || !data.session) {
        becomeGuest();
        return;
      }
      try {
        await loadBackendProfile();
      } catch (profileError) {
        await supabase.auth.signOut();
        if (active) becomeGuest(safeProfileError(profileError));
      }
    }

    void bootstrap();

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (!active) return;
      if (event === "SIGNED_OUT" || !session) {
        becomeGuest();
        return;
      }
      if (
        event === "SIGNED_IN" ||
        event === "TOKEN_REFRESHED" ||
        event === "USER_UPDATED" ||
        event === "INITIAL_SESSION"
      ) {
        window.setTimeout(() => {
          if (!active) return;
          void loadBackendProfile().catch(async (profileError) => {
            await supabase.auth.signOut();
            if (active) becomeGuest(safeProfileError(profileError));
          });
        }, 0);
      }
    });

    return () => {
      active = false;
      subscription.unsubscribe();
      supabaseRef.current = null;
      parkSmartApi.setAuthProvider(null);
    };
  }, [becomeGuest, demoMode, loadBackendProfile]);

  const signIn = useCallback(
    async (email: string, password: string): Promise<SignInResult> => {
      if (demoMode) {
        setProfile(DEMO_PROFILE);
        setStatus("authenticated");
        return { profile: DEMO_PROFILE, error: null };
      }

      const supabase = supabaseRef.current;
      if (!supabase) {
        return {
          profile: null,
          error: "Dịch vụ đăng nhập chưa sẵn sàng. Vui lòng thử lại.",
        };
      }

      const { data, error } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });
      if (error || !data.session) {
        return {
          profile: null,
          error: "Email hoặc mật khẩu không đúng.",
        };
      }

      try {
        const currentProfile = await loadBackendProfile();
        return { profile: currentProfile, error: null };
      } catch (profileError) {
        await supabase.auth.signOut();
        const message = safeProfileError(profileError);
        becomeGuest(message);
        return { profile: null, error: message };
      }
    },
    [becomeGuest, demoMode, loadBackendProfile],
  );

  const signOut = useCallback(async () => {
    const supabase = supabaseRef.current;
    if (supabase) {
      await supabase.auth.signOut();
    }
    becomeGuest();
  }, [becomeGuest]);

  const value = useMemo<AuthContextValue>(
    () => ({ status, profile, initializationError, signIn, signOut }),
    [initializationError, profile, signIn, signOut, status],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }
  return value;
}

export function parkingIdentityFromProfile(
  profile: AuthenticatedProfile,
): ParkingIdentity | null {
  if (profile.role !== "user" || !profile.parking_user_id) return null;
  return {
    userId: profile.parking_user_id,
    vehicleId: profile.default_vehicle_id,
  };
}