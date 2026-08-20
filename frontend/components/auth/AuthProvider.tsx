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
import type {
  AuthenticatedProfile,
  AuthStatus,
  ParkingIdentity,
} from "@/lib/auth";
import {
  MVP_DEMO_USER_ID,
  MVP_DEMO_VEHICLE_ID,
} from "@/lib/demo";
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
  const accessTokenRef = useRef<string | null>(null);
  const signInInFlightRef = useRef(false);

  const becomeGuest = useCallback((error: string | null = null) => {
    console.log("[AUTH] becomeGuest", {
      error,
    });

    accessTokenRef.current = null;
    setProfile(null);
    setInitializationError(error);
    setStatus("guest");
  }, []);

  const loadBackendProfile = useCallback(async () => {
    console.log("[AUTH] loading backend profile");

    try {
      const currentProfile = await parkSmartApi.getCurrentUser();

      console.log("[AUTH] backend profile loaded", {
        id: currentProfile.id,
        role: currentProfile.role,
        parkingUserId: currentProfile.parking_user_id,
        defaultVehicleId: currentProfile.default_vehicle_id,
      });

      setProfile(currentProfile);
      setInitializationError(null);
      setStatus("authenticated");

      return currentProfile;
    } catch (error) {
      console.error("[AUTH] backend profile load FAILED:", error);
      throw error;
    }
  }, []);

  useEffect(() => {
    console.log("[AUTH] AuthProvider effect started", {
      demoMode,
      supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL,
      hasPublishableKey: Boolean(
        process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
      ),
    });

    if (demoMode) {
      console.log("[AUTH] demo mode enabled");

      accessTokenRef.current = null;
      parkSmartApi.setAuthProvider(null);

      return () => {
        console.log("[AUTH] demo AuthProvider cleanup");

        accessTokenRef.current = null;
        parkSmartApi.setAuthProvider(null);
      };
    }

    let active = true;
    let supabase: SupabaseClient;

    try {
      console.log("[AUTH] creating Supabase browser client");

      supabase = createBrowserSupabaseClient();

      console.log("[AUTH] Supabase browser client created");
    } catch (error) {
      console.error("[AUTH] Supabase client init FAILED:", error);

      queueMicrotask(() => {
        if (active) {
          becomeGuest("Supabase chưa được cấu hình cho frontend.");
        }
      });

      return () => {
        console.log("[AUTH] cleanup after Supabase init failure");
        active = false;
      };
    }

    supabaseRef.current = supabase;

    console.log("[AUTH] supabaseRef assigned", {
      ready: Boolean(supabaseRef.current),
    });

    parkSmartApi.setAuthProvider({
      async getAccessToken() {
        console.log("[AUTH] API getAccessToken called", {
          cached: Boolean(accessTokenRef.current),
        });

        if (accessTokenRef.current) {
          return accessTokenRef.current;
        }

        const { data, error } = await supabase.auth.getSession();

        if (error) {
          console.error("[AUTH] getSession FAILED:", error);
        }

        if (error || !data.session) {
          accessTokenRef.current = null;
          return null;
        }

        accessTokenRef.current = data.session.access_token;

        console.log("[AUTH] getSession returned access token");

        return data.session.access_token;
      },

      async refreshAccessToken() {
        console.log("[AUTH] refreshAccessToken called");

        const { data, error } = await supabase.auth.refreshSession();

        if (error) {
          console.error("[AUTH] refreshSession FAILED:", error);
        }

        if (error || !data.session) {
          accessTokenRef.current = null;
          return null;
        }

        accessTokenRef.current = data.session.access_token;

        console.log("[AUTH] access token refreshed");

        return data.session.access_token;
      },

      async onAuthenticationFailure() {
        console.warn("[AUTH] API authentication failure");

        accessTokenRef.current = null;
        await supabase.auth.signOut();

        if (active) {
          becomeGuest();
        }
      },
    });

    console.log("[AUTH] ParkSmart API auth provider configured");

    /*
     * INITIAL_SESSION is the single source of truth for startup.
     */
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      console.log("[AUTH] Supabase auth state changed", {
        event,
        hasSession: Boolean(session),
        active,
        signInInFlight: signInInFlightRef.current,
      });

      if (!active) {
        console.log("[AUTH] auth event ignored because provider is inactive");
        return;
      }

      if (event === "INITIAL_SESSION") {
        if (!session) {
          console.log("[AUTH] INITIAL_SESSION has no session");

          becomeGuest();
          return;
        }

        console.log("[AUTH] INITIAL_SESSION has active session");

        accessTokenRef.current = session.access_token;
        setStatus("loading");

        window.setTimeout(() => {
          if (!active) {
            return;
          }

          void loadBackendProfile().catch(async (profileError) => {
            console.error(
              "[AUTH] INITIAL_SESSION profile validation FAILED:",
              profileError,
            );

            accessTokenRef.current = null;
            await supabase.auth.signOut();

            if (active) {
              becomeGuest(safeProfileError(profileError));
            }
          });
        }, 0);

        return;
      }

      if (event === "SIGNED_OUT" || !session) {
        console.log("[AUTH] signed out or session missing");

        becomeGuest();
        return;
      }

      accessTokenRef.current = session.access_token;

      console.log("[AUTH] latest JWT stored", {
        event,
      });

      /*
       * signIn() itself owns the first /auth/me call.
       */
      if (event === "SIGNED_IN" && signInInFlightRef.current) {
        console.log(
          "[AUTH] SIGNED_IN profile load skipped because signIn owns it",
        );
        return;
      }

      if (
        event === "SIGNED_IN" ||
        event === "TOKEN_REFRESHED" ||
        event === "USER_UPDATED"
      ) {
        window.setTimeout(() => {
          if (!active) {
            return;
          }

          void loadBackendProfile().catch(async (profileError) => {
            console.error(
              `[AUTH] ${event} profile validation FAILED:`,
              profileError,
            );

            accessTokenRef.current = null;
            await supabase.auth.signOut();

            if (active) {
              becomeGuest(safeProfileError(profileError));
            }
          });
        }, 0);
      }
    });

    console.log("[AUTH] auth state subscription registered");

    return () => {
      console.log("[AUTH] AuthProvider cleanup", {
        hadSupabaseClient: Boolean(supabaseRef.current),
      });

      active = false;
      subscription.unsubscribe();

      supabaseRef.current = null;
      accessTokenRef.current = null;

      parkSmartApi.setAuthProvider(null);
    };
  }, [becomeGuest, demoMode, loadBackendProfile]);

  const signIn = useCallback(
    async (email: string, password: string): Promise<SignInResult> => {
      console.log("[AUTH] signIn called", {
        email: email.trim(),
        demoMode,
        clientReady: Boolean(supabaseRef.current),
      });

      if (demoMode) {
        accessTokenRef.current = null;
        setProfile(DEMO_PROFILE);
        setInitializationError(null);
        setStatus("authenticated");

        console.log("[AUTH] demo signIn completed");

        return {
          profile: DEMO_PROFILE,
          error: null,
        };
      }

      const supabase = supabaseRef.current;

      console.log("[AUTH] signIn Supabase client state", {
        ready: Boolean(supabase),
      });

      if (!supabase) {
        console.error(
          "[AUTH] signIn aborted because Supabase client is null",
        );

        return {
          profile: null,
          error: "Dịch vụ đăng nhập chưa sẵn sàng. Vui lòng thử lại.",
        };
      }

      signInInFlightRef.current = true;

      console.log("[AUTH] signInWithPassword starting");

      try {
        const { data, error } = await supabase.auth.signInWithPassword({
          email: email.trim(),
          password,
        });

        if (error) {
          console.error("[AUTH] signInWithPassword FAILED:", error);
        }

        if (error || !data.session) {
          accessTokenRef.current = null;

          console.warn("[AUTH] login rejected", {
            hasSession: Boolean(data.session),
          });

          return {
            profile: null,
            error: "Email hoặc mật khẩu không đúng.",
          };
        }

        console.log("[AUTH] Supabase login PASS", {
          userId: data.user?.id,
          email: data.user?.email,
          hasAccessToken: Boolean(data.session.access_token),
        });

        accessTokenRef.current = data.session.access_token;

        console.log("[AUTH] JWT stored; loading ParkSmart profile");

        try {
          const currentProfile = await loadBackendProfile();

          console.log("[AUTH] full login flow PASS", {
            role: currentProfile.role,
          });

          return {
            profile: currentProfile,
            error: null,
          };
        } catch (profileError) {
          console.error(
            "[AUTH] login succeeded but ParkSmart profile FAILED:",
            profileError,
          );

          accessTokenRef.current = null;

          await supabase.auth.signOut();

          const message = safeProfileError(profileError);

          becomeGuest(message);

          return {
            profile: null,
            error: message,
          };
        }
      } catch (error) {
        console.error("[AUTH] unexpected signIn exception:", error);

        return {
          profile: null,
          error: "Không thể đăng nhập. Vui lòng thử lại.",
        };
      } finally {
        signInInFlightRef.current = false;

        console.log("[AUTH] signIn finished", {
          clientReady: Boolean(supabaseRef.current),
        });
      }
    },
    [becomeGuest, demoMode, loadBackendProfile],
  );

  const signOut = useCallback(async () => {
    console.log("[AUTH] signOut called", {
      clientReady: Boolean(supabaseRef.current),
    });

    const supabase = supabaseRef.current;

    accessTokenRef.current = null;

    if (supabase) {
      const { error } = await supabase.auth.signOut();

      if (error) {
        console.error("[AUTH] Supabase signOut FAILED:", error);
      } else {
        console.log("[AUTH] Supabase signOut PASS");
      }
    }

    becomeGuest();
  }, [becomeGuest]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      profile,
      initializationError,
      signIn,
      signOut,
    }),
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
  if (profile.role !== "user" || !profile.parking_user_id) {
    return null;
  }

  return {
    userId: profile.parking_user_id,
    vehicleId: profile.default_vehicle_id,
  };
}