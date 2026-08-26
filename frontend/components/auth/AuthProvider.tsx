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
  state: "authenticated" | "confirmation_required" | "failed";
  profile: AuthenticatedProfile | null;
  error: string | null;
  email?: string;
}

interface SignUpResult {
  state: "authenticated" | "confirmation_required" | "rate_limited" | "failed";
  profile: AuthenticatedProfile | null;
  error: string | null;
  email: string;
}

interface ResendConfirmationResult {
  state: "sent" | "rate_limited" | "failed";
  error: string | null;
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
  resendSignUpConfirmation: (email: string) => Promise<ResendConfirmationResult>;
  refreshProfile: () => Promise<AuthenticatedProfile | null>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const MIN_PASSWORD_LENGTH = 6;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function normalizeEmail(email: string) {
  return email.trim().toLowerCase();
}

function validateEmail(email: string): string | null {
  if (!email) {
    return "Email không được để trống.";
  }

  if (!EMAIL_PATTERN.test(email)) {
    return "Email không đúng định dạng. Ví dụ: tenban@example.com.";
  }

  return null;
}

function validatePassword(password: string): string | null {
  if (!password) {
    return "Mật khẩu không được để trống.";
  }

  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Mật khẩu phải có ít nhất ${MIN_PASSWORD_LENGTH} ký tự.`;
  }

  return null;
}

function validateFullName(fullName: string): string | null {
  if (!fullName) {
    return "Họ và tên không được để trống.";
  }

  return null;
}

function safeProfileError(error: unknown) {
  if (error instanceof ApiError && error.status === 403) {
    return "Tài khoản đã đăng nhập nhưng chưa được cấu hình quyền ParkSmart hợp lệ.";
  }

  return "Không thể xác minh tài khoản ParkSmart. Vui lòng đăng nhập lại.";
}

function safeSignUpError(error: unknown) {
  const code =
    error && typeof error === "object" && "code" in error
      ? String(error.code)
      : null;

  if (code === "over_email_send_rate_limit") {
    return "Supabase đang tạm giới hạn số email xác nhận. Vui lòng chờ một lúc rồi thử lại.";
  }

  if (code === "weak_password") {
    return `Mật khẩu phải có ít nhất ${MIN_PASSWORD_LENGTH} ký tự.`;
  }

  if (code === "email_address_invalid") {
    return "Email không đúng định dạng. Vui lòng kiểm tra lại địa chỉ email.";
  }

  if (code === "user_already_exists") {
    return "Email này đã được đăng ký. Vui lòng đăng nhập hoặc sử dụng email khác.";
  }

  return "Không thể tạo tài khoản. Vui lòng kiểm tra email và mật khẩu rồi thử lại.";
}

function authErrorCode(error: unknown): string | null {
  return error && typeof error === "object" && "code" in error
    ? String(error.code)
    : null;
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
          state: "authenticated",
          profile: DEMO_PROFILE,
          error: null,
        };
      }

      const normalizedEmail = normalizeEmail(email);
      const emailError = validateEmail(normalizedEmail);
      if (emailError) {
        console.warn("[Auth] Đăng nhập bị chặn: email không hợp lệ.");
        return {
          state: "failed",
          profile: null,
          error: emailError,
        };
      }

      const passwordError = validatePassword(password);
      if (passwordError) {
        console.warn("[Auth] Đăng nhập bị chặn: mật khẩu không hợp lệ.");
        return {
          state: "failed",
          profile: null,
          error: passwordError,
        };
      }

      const supabase = supabaseRef.current;

      if (!supabase) {
        return {
          state: "failed",
          profile: null,
          error: "Dịch vụ đăng nhập chưa sẵn sàng. Vui lòng thử lại.",
        };
      }

      signInInFlightRef.current = true;

      try {
        const { data, error } = await supabase.auth.signInWithPassword({
          email: normalizedEmail,
          password,
        });

        if (error || !data.session) {
          accessTokenRef.current = null;
          const code = authErrorCode(error);
          console.warn(`[Auth] Đăng nhập thất bại. Mã lỗi: ${code ?? "unknown"}.`);

          if (code === "email_not_confirmed") {
            return {
              state: "confirmation_required",
              profile: null,
              error: "Email chưa được xác nhận. Vui lòng kiểm tra hộp thư hoặc gửi lại email xác nhận.",
              email: normalizedEmail,
            };
          }

          return {
            state: "failed",
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
            state: "authenticated",
            profile: currentProfile,
            error: null,
          };
        } catch (profileError) {
          accessTokenRef.current = null;
          await supabase.auth.signOut();

          const message = safeProfileError(profileError);
          becomeGuest(message);

          return {
            state: "failed",
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
          state: "authenticated",
          profile: DEMO_PROFILE,
          error: null,
          email: normalizeEmail(input.email),
        };
      }

      const fullName = input.fullName.trim();
      const normalizedEmail = normalizeEmail(input.email);

      const fullNameError = validateFullName(fullName);
      if (fullNameError) {
        console.warn("[Auth] Đăng ký bị chặn: họ và tên không hợp lệ.");
        return {
          state: "failed",
          profile: null,
          error: fullNameError,
          email: normalizedEmail,
        };
      }

      const emailError = validateEmail(normalizedEmail);
      if (emailError) {
        console.warn("[Auth] Đăng ký bị chặn: email không hợp lệ.");
        return {
          state: "failed",
          profile: null,
          error: emailError,
          email: normalizedEmail,
        };
      }

      const passwordError = validatePassword(input.password);
      if (passwordError) {
        console.warn("[Auth] Đăng ký bị chặn: mật khẩu không hợp lệ.");
        return {
          state: "failed",
          profile: null,
          error: passwordError,
          email: normalizedEmail,
        };
      }

      const supabase = supabaseRef.current;
      if (!supabase) {
        return {
          state: "failed",
          profile: null,
          error: "Dịch vụ đăng ký chưa sẵn sàng. Vui lòng thử lại.",
          email: normalizedEmail,
        };
      }

      signInInFlightRef.current = true;
      try {
        const { data, error } = await supabase.auth.signUp({
          email: normalizedEmail,
          password: input.password,
          options: {
            data: {
              full_name: fullName,
            },
          },
        });

        if (error) {
          const errorCode =
            typeof error === "object" && error && "code" in error
              ? String(error.code)
              : "unknown";

          console.warn(`[Auth] Supabase từ chối đăng ký. Mã lỗi: ${errorCode}.`);

          return {
            state: errorCode === "over_email_send_rate_limit" ? "rate_limited" : "failed",
            profile: null,
            error: safeSignUpError(error),
            email: normalizedEmail,
          };
        }

        if (!data.session) {
          return {
            state: "confirmation_required",
            profile: null,
            error: null,
            email: normalizedEmail,
          };
        }

        accessTokenRef.current = data.session.access_token;
        try {
          const currentProfile = await loadBackendProfile();
          return {
            state: "authenticated",
            profile: currentProfile,
            error: null,
            email: normalizedEmail,
          };
        } catch (profileError) {
          accessTokenRef.current = null;
          await supabase.auth.signOut();

          const message = safeProfileError(profileError);
          becomeGuest(message);

          return {
            state: "failed",
            profile: null,
            error: message,
            email: normalizedEmail,
          };
        }
      } catch (error) {
        console.error("[Auth] Có lỗi không mong muốn khi tạo tài khoản.", error);

        return {
          state: "failed",
          profile: null,
          error: "Không thể tạo tài khoản. Vui lòng thử lại.",
          email: normalizedEmail,
        };
      } finally {
        signInInFlightRef.current = false;
      }
    },
    [becomeGuest, demoMode, loadBackendProfile],
  );

  const resendSignUpConfirmation = useCallback(
    async (email: string): Promise<ResendConfirmationResult> => {
      const normalizedEmail = normalizeEmail(email);
      const emailError = validateEmail(normalizedEmail);
      if (emailError) {
        return { state: "failed", error: emailError };
      }
      if (demoMode) {
        return { state: "sent", error: null };
      }
      const supabase = supabaseRef.current;
      if (!supabase) {
        return {
          state: "failed",
          error: "Dịch vụ xác nhận email chưa sẵn sàng. Vui lòng thử lại.",
        };
      }
      try {
        const { error } = await supabase.auth.resend({
          type: "signup",
          email: normalizedEmail,
        });
        if (!error) {
          return { state: "sent", error: null };
        }
        if (authErrorCode(error) === "over_email_send_rate_limit") {
          return {
            state: "rate_limited",
            error: "Email xác nhận đang bị giới hạn tạm thời. Vui lòng chờ rồi gửi lại.",
          };
        }
        return {
          state: "failed",
          error: "Không thể gửi lại email xác nhận. Vui lòng thử lại.",
        };
      } catch {
        return {
          state: "failed",
          error: "Không thể gửi lại email xác nhận. Vui lòng thử lại.",
        };
      }
    },
    [demoMode],
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
      resendSignUpConfirmation,
      refreshProfile: loadBackendProfile,
      signOut,
    }),
    [
      initializationError,
      loadBackendProfile,
      profile,
      resendSignUpConfirmation,
      signIn,
      signOut,
      signUp,
      status,
    ],
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
