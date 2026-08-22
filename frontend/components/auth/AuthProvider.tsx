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

interface SignUpResult extends SignInResult {
  confirmationRequired?: boolean;
}

interface AuthContextValue {
  status: AuthStatus;
  profile: AuthenticatedProfile | null;
  initializationError: string | null;
  signIn: (email: string, password: string) => Promise<SignInResult>;
  signUp: (input: {
    fullName: string;
    email: string;
    password: string;
  }) => Promise<SignUpResult>;
  refreshProfile: () => Promise<AuthenticatedProfile | null>;
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
  const backendProfileInFlightRef =
    useRef<Promise<AuthenticatedProfile> | null>(null);

  const becomeGuest = useCallback((error: string | null = null) => {
    accessTokenRef.current = null;
    setProfile(null);
    setInitializationError(error);
    setStatus("guest");
  }, []);

  const loadBackendProfile = useCallback(async () => {
    if (backendProfileInFlightRef.current) {
      return backendProfileInFlightRef.current;
    }

    const promise = (async () => {
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
    })().finally(() => {
      backendProfileInFlightRef.current = null;
    });
    backendProfileInFlightRef.current = promise;
    return promise;
  }, []);

  useEffect(() => {
    if (demoMode) {
      accessTokenRef.current = null;
      parkSmartApi.setAuthProvider(null);

      return () => {
        accessTokenRef.current = null;
        parkSmartApi.setAuthProvider(null);
      };
    }

    let active = true;
    let supabase: SupabaseClient;

    try {
      supabase = createBrowserSupabaseClient();
    } catch {
      queueMicrotask(() => {
        if (active) {
          becomeGuest("Supabase chưa được cấu hình cho frontend.");
        }
      });

      return;
    }

    supabaseRef.current = supabase;

    parkSmartApi.setAuthProvider({
      async getAccessToken() {
        if (accessTokenRef.current) {
          return accessTokenRef.current;
        }

        const { data, error } = await supabase.auth.getSession();

        if (error || !data.session) {
          accessTokenRef.current = null;
          return null;
        }

        accessTokenRef.current = data.session.access_token;
        return data.session.access_token;
      },

      async refreshAccessToken() {
        const { data, error } = await supabase.auth.refreshSession();

        if (error || !data.session) {
          accessTokenRef.current = null;
          return null;
        }

        accessTokenRef.current = data.session.access_token;
        return data.session.access_token;
      },

      async onAuthenticationFailure() {
        accessTokenRef.current = null;
        await supabase.auth.signOut();

        if (active) {
          becomeGuest();
        }
      },
    });

    /*
     * Do not run a separate bootstrap(getSession()) here.
     *
     * Supabase emits INITIAL_SESSION after its own initialization completes.
     * Using both a manual bootstrap and INITIAL_SESSION creates two competing
     * initialization flows. A delayed null bootstrap/initial event can
     * overwrite a successful sign-in and return the UI to "guest".
     *
     * INITIAL_SESSION is therefore the single source of truth for startup.
     */
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (!active) {
        return;
      }

      if (event === "INITIAL_SESSION") {
        if (!session) {
          becomeGuest();
          return;
        }

        accessTokenRef.current = session.access_token;
        setStatus("loading");

        window.setTimeout(() => {
          if (!active) {
            return;
          }

          void loadBackendProfile().catch(async (profileError) => {
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
        becomeGuest();
        return;
      }

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
            accessTokenRef.current = null;
            await supabase.auth.signOut();

            if (active) {
              becomeGuest(safeProfileError(profileError));
            }
          });
        }, 0);
      }
    });

    return () => {
      active = false;
      subscription.unsubscribe();
      supabaseRef.current = null;
      accessTokenRef.current = null;
      parkSmartApi.setAuthProvider(null);
    };
  }, [becomeGuest, demoMode, loadBackendProfile]);

  const signIn = useCallback(
    async (email: string, password: string): Promise<SignInResult> => {
      if (demoMode) {
        accessTokenRef.current = null;
        setProfile(DEMO_PROFILE);
        setInitializationError(null);
        setStatus("authenticated");

        return {
          profile: DEMO_PROFILE,
          error: null,
        };
      }

      const supabase = supabaseRef.current;

      if (!supabase) {
        return {
          profile: null,
          error: "Dịch vụ đăng nhập chưa sẵn sàng. Vui lòng thử lại.",
        };
      }

      signInInFlightRef.current = true;

      try {
        const { data, error } = await supabase.auth.signInWithPassword({
          email: email.trim(),
          password,
        });

        if (error || !data.session) {
          accessTokenRef.current = null;

          return {
            profile: null,
            error: "Email hoặc mật khẩu không đúng.",
          };
        }

        /*
         * signInWithPassword already returns the newly issued session.
         * Use that JWT immediately for the first ParkSmart /auth/me request.
         */
        accessTokenRef.current = data.session.access_token;

        try {
          const currentProfile = await loadBackendProfile();

          return {
            profile: currentProfile,
            error: null,
          };
        } catch (profileError) {
          accessTokenRef.current = null;
          await supabase.auth.signOut();

          const message = safeProfileError(profileError);
          becomeGuest(message);

          return {
            profile: null,
            error: message,
          };
        }
      } finally {
        signInInFlightRef.current = false;
      }
    },
    [becomeGuest, demoMode, loadBackendProfile],
  );

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

      signInInFlightRef.current = true;
      try {
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
        try {
          const currentProfile = await loadBackendProfile();
          return {
            profile: currentProfile,
            error: null,
            confirmationRequired: false,
          };
        } catch (profileError) {
          accessTokenRef.current = null;
          await supabase.auth.signOut();

          const message = safeProfileError(profileError);
          becomeGuest(message);

          return {
            profile: null,
            error: message,
            confirmationRequired: false,
          };
        }
      } catch {
        return {
          profile: null,
          error: "Khong the tao tai khoan. Vui long thu lai.",
        };
      } finally {
        signInInFlightRef.current = false;
      }
    },
    [becomeGuest, demoMode, loadBackendProfile],
  );

  const signOut = useCallback(async () => {
    const supabase = supabaseRef.current;

    accessTokenRef.current = null;

    if (supabase) {
      await supabase.auth.signOut();
    }

    becomeGuest();
  }, [becomeGuest]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      profile,
      initializationError,
      signIn,
      signUp,
      refreshProfile: loadBackendProfile,
      signOut,
    }),
    [initializationError, loadBackendProfile, profile, signIn, signOut, signUp, status],
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
