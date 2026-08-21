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

<<<<<<< HEAD
=======
interface SignUpResult extends SignInResult {
  confirmationRequired?: boolean;
}

>>>>>>> feat/phase11-role-based-auth
interface AuthContextValue {
  status: AuthStatus;
  profile: AuthenticatedProfile | null;
  initializationError: string | null;
  signIn: (email: string, password: string) => Promise<SignInResult>;
<<<<<<< HEAD
=======
  signUp: (input: {
    fullName: string;
    email: string;
    password: string;
  }) => Promise<SignUpResult>;
  refreshProfile: () => Promise<AuthenticatedProfile | null>;
>>>>>>> feat/phase11-role-based-auth
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
<<<<<<< HEAD
    console.log("[AUTH] becomeGuest", {
      error,
    });

=======
>>>>>>> feat/phase11-role-based-auth
    accessTokenRef.current = null;
    setProfile(null);
    setInitializationError(error);
    setStatus("guest");
  }, []);

  const loadBackendProfile = useCallback(async () => {
<<<<<<< HEAD
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

=======
    let currentProfile: AuthenticatedProfile;
    try {
      currentProfile = await parkSmartApi.getCurrentUser();
    } catch (error) {
      if (error instanceof ApiError && error.code === "PROFILE_NOT_FOUND") {
        currentProfile = await parkSmartApi.onboardCurrentUser();
      } else {
        throw error;
      }
    }

    setProfile(currentProfile);
    setInitializationError(null);
    setStatus("authenticated");

    return currentProfile;
  }, []);

  useEffect(() => {
    if (demoMode) {
>>>>>>> feat/phase11-role-based-auth
      accessTokenRef.current = null;
      parkSmartApi.setAuthProvider(null);

      return () => {
<<<<<<< HEAD
        console.log("[AUTH] demo AuthProvider cleanup");

=======
>>>>>>> feat/phase11-role-based-auth
        accessTokenRef.current = null;
        parkSmartApi.setAuthProvider(null);
      };
    }

    let active = true;
    let supabase: SupabaseClient;

    try {
<<<<<<< HEAD
      console.log("[AUTH] creating Supabase browser client");

      supabase = createBrowserSupabaseClient();

      console.log("[AUTH] Supabase browser client created");
    } catch (error) {
      console.error("[AUTH] Supabase client init FAILED:", error);

=======
      supabase = createBrowserSupabaseClient();
    } catch {
>>>>>>> feat/phase11-role-based-auth
      queueMicrotask(() => {
        if (active) {
          becomeGuest("Supabase chưa được cấu hình cho frontend.");
        }
      });

<<<<<<< HEAD
      return () => {
        console.log("[AUTH] cleanup after Supabase init failure");
        active = false;
      };
=======
      return;
>>>>>>> feat/phase11-role-based-auth
    }

    supabaseRef.current = supabase;

<<<<<<< HEAD
    console.log("[AUTH] supabaseRef assigned", {
      ready: Boolean(supabaseRef.current),
    });

    parkSmartApi.setAuthProvider({
      async getAccessToken() {
        console.log("[AUTH] API getAccessToken called", {
          cached: Boolean(accessTokenRef.current),
        });

=======
    parkSmartApi.setAuthProvider({
      async getAccessToken() {
>>>>>>> feat/phase11-role-based-auth
        if (accessTokenRef.current) {
          return accessTokenRef.current;
        }

        const { data, error } = await supabase.auth.getSession();

<<<<<<< HEAD
        if (error) {
          console.error("[AUTH] getSession FAILED:", error);
        }

=======
>>>>>>> feat/phase11-role-based-auth
        if (error || !data.session) {
          accessTokenRef.current = null;
          return null;
        }

        accessTokenRef.current = data.session.access_token;
<<<<<<< HEAD

        console.log("[AUTH] getSession returned access token");

=======
>>>>>>> feat/phase11-role-based-auth
        return data.session.access_token;
      },

      async refreshAccessToken() {
<<<<<<< HEAD
        console.log("[AUTH] refreshAccessToken called");

        const { data, error } = await supabase.auth.refreshSession();

        if (error) {
          console.error("[AUTH] refreshSession FAILED:", error);
        }

=======
        const { data, error } = await supabase.auth.refreshSession();

>>>>>>> feat/phase11-role-based-auth
        if (error || !data.session) {
          accessTokenRef.current = null;
          return null;
        }

        accessTokenRef.current = data.session.access_token;
<<<<<<< HEAD

        console.log("[AUTH] access token refreshed");

=======
>>>>>>> feat/phase11-role-based-auth
        return data.session.access_token;
      },

      async onAuthenticationFailure() {
<<<<<<< HEAD
        console.warn("[AUTH] API authentication failure");

=======
>>>>>>> feat/phase11-role-based-auth
        accessTokenRef.current = null;
        await supabase.auth.signOut();

        if (active) {
          becomeGuest();
        }
      },
    });

<<<<<<< HEAD
    console.log("[AUTH] ParkSmart API auth provider configured");

    /*
     * INITIAL_SESSION is the single source of truth for startup.
=======
    /*
     * Do not run a separate bootstrap(getSession()) here.
     *
     * Supabase emits INITIAL_SESSION after its own initialization completes.
     * Using both a manual bootstrap and INITIAL_SESSION creates two competing
     * initialization flows. A delayed null bootstrap/initial event can
     * overwrite a successful sign-in and return the UI to "guest".
     *
     * INITIAL_SESSION is therefore the single source of truth for startup.
>>>>>>> feat/phase11-role-based-auth
     */
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
<<<<<<< HEAD
      console.log("[AUTH] Supabase auth state changed", {
        event,
        hasSession: Boolean(session),
        active,
        signInInFlight: signInInFlightRef.current,
      });

      if (!active) {
        console.log("[AUTH] auth event ignored because provider is inactive");
=======
      if (!active) {
>>>>>>> feat/phase11-role-based-auth
        return;
      }

      if (event === "INITIAL_SESSION") {
        if (!session) {
<<<<<<< HEAD
          console.log("[AUTH] INITIAL_SESSION has no session");

=======
>>>>>>> feat/phase11-role-based-auth
          becomeGuest();
          return;
        }

<<<<<<< HEAD
        console.log("[AUTH] INITIAL_SESSION has active session");

=======
>>>>>>> feat/phase11-role-based-auth
        accessTokenRef.current = session.access_token;
        setStatus("loading");

        window.setTimeout(() => {
          if (!active) {
            return;
          }

          void loadBackendProfile().catch(async (profileError) => {
<<<<<<< HEAD
            console.error(
              "[AUTH] INITIAL_SESSION profile validation FAILED:",
              profileError,
            );

=======
>>>>>>> feat/phase11-role-based-auth
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
<<<<<<< HEAD
        console.log("[AUTH] signed out or session missing");

=======
>>>>>>> feat/phase11-role-based-auth
        becomeGuest();
        return;
      }

<<<<<<< HEAD
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
=======
      /*
       * Keep the latest Supabase JWT in memory. This is the token the
       * ParkSmart API client should attach to Authorization: Bearer.
       */
      accessTokenRef.current = session.access_token;

      /*
       * signIn() itself owns the first /auth/me call because LoginForm needs
       * the authoritative ParkSmart profile returned from signIn().
       */
      if (event === "SIGNED_IN" && signInInFlightRef.current) {
>>>>>>> feat/phase11-role-based-auth
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
<<<<<<< HEAD
            console.error(
              `[AUTH] ${event} profile validation FAILED:`,
              profileError,
            );

=======
>>>>>>> feat/phase11-role-based-auth
            accessTokenRef.current = null;
            await supabase.auth.signOut();

            if (active) {
              becomeGuest(safeProfileError(profileError));
            }
          });
        }, 0);
      }
    });

<<<<<<< HEAD
    console.log("[AUTH] auth state subscription registered");

    return () => {
      console.log("[AUTH] AuthProvider cleanup", {
        hadSupabaseClient: Boolean(supabaseRef.current),
      });

      active = false;
      subscription.unsubscribe();

      supabaseRef.current = null;
      accessTokenRef.current = null;

=======
    return () => {
      active = false;
      subscription.unsubscribe();
      supabaseRef.current = null;
      accessTokenRef.current = null;
>>>>>>> feat/phase11-role-based-auth
      parkSmartApi.setAuthProvider(null);
    };
  }, [becomeGuest, demoMode, loadBackendProfile]);

  const signIn = useCallback(
    async (email: string, password: string): Promise<SignInResult> => {
<<<<<<< HEAD
      console.log("[AUTH] signIn called", {
        email: email.trim(),
        demoMode,
        clientReady: Boolean(supabaseRef.current),
      });

=======
>>>>>>> feat/phase11-role-based-auth
      if (demoMode) {
        accessTokenRef.current = null;
        setProfile(DEMO_PROFILE);
        setInitializationError(null);
        setStatus("authenticated");

<<<<<<< HEAD
        console.log("[AUTH] demo signIn completed");

=======
>>>>>>> feat/phase11-role-based-auth
        return {
          profile: DEMO_PROFILE,
          error: null,
        };
      }

      const supabase = supabaseRef.current;

<<<<<<< HEAD
      console.log("[AUTH] signIn Supabase client state", {
        ready: Boolean(supabase),
      });

      if (!supabase) {
        console.error(
          "[AUTH] signIn aborted because Supabase client is null",
        );

=======
      if (!supabase) {
>>>>>>> feat/phase11-role-based-auth
        return {
          profile: null,
          error: "Dịch vụ đăng nhập chưa sẵn sàng. Vui lòng thử lại.",
        };
      }

      signInInFlightRef.current = true;

<<<<<<< HEAD
      console.log("[AUTH] signInWithPassword starting");

=======
>>>>>>> feat/phase11-role-based-auth
      try {
        const { data, error } = await supabase.auth.signInWithPassword({
          email: email.trim(),
          password,
        });

<<<<<<< HEAD
        if (error) {
          console.error("[AUTH] signInWithPassword FAILED:", error);
        }

        if (error || !data.session) {
          accessTokenRef.current = null;

          console.warn("[AUTH] login rejected", {
            hasSession: Boolean(data.session),
          });

=======
        if (error || !data.session) {
          accessTokenRef.current = null;

>>>>>>> feat/phase11-role-based-auth
          return {
            profile: null,
            error: "Email hoặc mật khẩu không đúng.",
          };
        }

<<<<<<< HEAD
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

=======
        /*
         * signInWithPassword already returns the newly issued session.
         * Use that JWT immediately for the first ParkSmart /auth/me request.
         */
        accessTokenRef.current = data.session.access_token;

        try {
          const currentProfile = await loadBackendProfile();

>>>>>>> feat/phase11-role-based-auth
          return {
            profile: currentProfile,
            error: null,
          };
        } catch (profileError) {
<<<<<<< HEAD
          console.error(
            "[AUTH] login succeeded but ParkSmart profile FAILED:",
            profileError,
          );

          accessTokenRef.current = null;

          await supabase.auth.signOut();

          const message = safeProfileError(profileError);

=======
          accessTokenRef.current = null;
          await supabase.auth.signOut();

          const message = safeProfileError(profileError);
>>>>>>> feat/phase11-role-based-auth
          becomeGuest(message);

          return {
            profile: null,
            error: message,
          };
        }
<<<<<<< HEAD
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
=======
      } finally {
        signInInFlightRef.current = false;
>>>>>>> feat/phase11-role-based-auth
      }
    },
    [becomeGuest, demoMode, loadBackendProfile],
  );

<<<<<<< HEAD
  const signOut = useCallback(async () => {
    console.log("[AUTH] signOut called", {
      clientReady: Boolean(supabaseRef.current),
    });

=======
  const signUp = useCallback(
    async (input: {
      fullName: string;
      email: string;
      password: string;
    }): Promise<SignUpResult> => {
      if (demoMode) {
        return {
          profile: DEMO_PROFILE,
          error: null,
          confirmationRequired: false,
        };
      }

      const supabase = supabaseRef.current;
      if (!supabase) {
        return {
          profile: null,
          error: "Dich vu dang ky chua san sang. Vui long thu lai.",
        };
      }

      const { data, error } = await supabase.auth.signUp({
        email: input.email.trim(),
        password: input.password,
        options: {
          data: {
            full_name: input.fullName.trim(),
          },
        },
      });

      if (error) {
        return {
          profile: null,
          error: "Khong the tao tai khoan. Vui long kiem tra email va mat khau.",
        };
      }

      if (!data.session) {
        return {
          profile: null,
          error: null,
          confirmationRequired: true,
        };
      }

      accessTokenRef.current = data.session.access_token;
      const currentProfile = await loadBackendProfile();
      return {
        profile: currentProfile,
        error: null,
        confirmationRequired: false,
      };
    },
    [demoMode, loadBackendProfile],
  );

  const signOut = useCallback(async () => {
>>>>>>> feat/phase11-role-based-auth
    const supabase = supabaseRef.current;

    accessTokenRef.current = null;

    if (supabase) {
<<<<<<< HEAD
      const { error } = await supabase.auth.signOut();

      if (error) {
        console.error("[AUTH] Supabase signOut FAILED:", error);
      } else {
        console.log("[AUTH] Supabase signOut PASS");
      }
=======
      await supabase.auth.signOut();
>>>>>>> feat/phase11-role-based-auth
    }

    becomeGuest();
  }, [becomeGuest]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      profile,
      initializationError,
      signIn,
<<<<<<< HEAD
      signOut,
    }),
    [initializationError, profile, signIn, signOut, status],
=======
      signUp,
      refreshProfile: loadBackendProfile,
      signOut,
    }),
    [initializationError, loadBackendProfile, profile, signIn, signOut, signUp, status],
>>>>>>> feat/phase11-role-based-auth
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
<<<<<<< HEAD
}
=======
}
>>>>>>> feat/phase11-role-based-auth
