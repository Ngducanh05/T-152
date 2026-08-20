import { expect, test, type Page, type Route } from "@playwright/test";

const USER = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "user@example.com",
  password: "user-password-e2e",
  role: "user" as const,
  parking_user_id: "USER-101",
  default_vehicle_id: "VEHICLE-101",
};

const ADMIN = {
  id: "22222222-2222-4222-8222-222222222222",
  email: "admin@example.com",
  password: "admin-password-e2e",
  role: "admin" as const,
  parking_user_id: null,
  default_vehicle_id: null,
};

type Account = typeof USER | typeof ADMIN;

function responseHeaders() {
  return {
    "access-control-allow-origin": "*",
    "access-control-allow-headers":
      "authorization, apikey, content-type, x-client-info, x-supabase-api-version",
    "access-control-allow-methods": "GET, POST, PATCH, DELETE, OPTIONS",
    "content-type": "application/json",
  };
}

function supabaseUser(account: Account) {
  const now = new Date().toISOString();

  return {
    id: account.id,
    aud: "authenticated",
    role: "authenticated",
    email: account.email,
    email_confirmed_at: now,
    confirmed_at: now,
    last_sign_in_at: now,
    phone: "",
    app_metadata: {
      provider: "email",
      providers: ["email"],
    },
    user_metadata: {},
    identities: [],
    created_at: now,
    updated_at: now,
    is_anonymous: false,
  };
}

function base64UrlJson(value: unknown) {
  return Buffer.from(
    JSON.stringify(value),
    "utf-8",
  ).toString("base64url");
}

function makeAccessToken(
  account: Account,
  sequence: number,
) {
  const now =
    Math.floor(Date.now() / 1000);

  const header = {
    alg: "HS256",
    typ: "JWT",
  };

  const payload = {
    iss: "http://supabase.parksmart.test/auth/v1",
    sub: account.id,
    aud: "authenticated",
    exp: now + 3600,
    iat: now,
    email: account.email,
    role: "authenticated",
    aal: "aal1",
    session_id:
      `e2e-${account.role}-${sequence}`,
    is_anonymous: false,
  };

  const signature = Buffer.from(
    `parksmart-e2e-${account.role}-${sequence}`,
    "utf-8",
  ).toString("base64url");

  return (
    `${base64UrlJson(header)}.` +
    `${base64UrlJson(payload)}.` +
    signature
  );
}

function sessionPayload(
  account: Account,
  accessToken: string,
  refreshToken: string,
) {
  return {
    access_token: accessToken,
    token_type: "bearer",
    expires_in: 3600,
    expires_at:
      Math.floor(Date.now() / 1000) +
      3600,
    refresh_token: refreshToken,
    user: supabaseUser(account),
  };
}

function accountFromAccessToken(
  accessToken: string,
  tokens: Map<string, Account>,
): Account | undefined {
  return tokens.get(accessToken);
}

function success(data: unknown) {
  return {
    success: true,
    data,
  };
}

function failure(
  code: string,
  message: string,
) {
  return {
    success: false,
    error: {
      code,
      message,
      request_id:
        "auth-e2e-request",
      details: null,
    },
  };
}

async function fulfillJson(
  route: Route,
  body: unknown,
  status = 200,
) {
  await route.fulfill({
    status,
    headers: responseHeaders(),
    body: JSON.stringify(body),
  });
}

async function installAuthMocks(
  page: Page,
) {
  const tokens =
    new Map<string, Account>();

  const refreshTokens =
    new Map<string, Account>();

  let sequence = 0;

  await page.route(
    "http://supabase.parksmart.test/**",
    async (route) => {
      const request =
        route.request();

      const url =
        new URL(request.url());

      if (
        request.method() ===
        "OPTIONS"
      ) {
        await route.fulfill({
          status: 204,
          headers:
            responseHeaders(),
        });
        return;
      }

      if (
        url.pathname ===
        "/auth/v1/token"
      ) {
        const grantType =
          url.searchParams.get(
            "grant_type",
          );

        const body =
          request.postDataJSON() as
            | Record<
                string,
                string
              >
            | null;

        if (
          grantType ===
          "password"
        ) {
          const account = [
            USER,
            ADMIN,
          ].find(
            (candidate) =>
              candidate.email ===
                body?.email &&
              candidate.password ===
                body?.password,
          );

          if (!account) {
            await fulfillJson(
              route,
              {
                code:
                  "invalid_credentials",
                message:
                  "Invalid login credentials",
              },
              400,
            );

            return;
          }

          sequence += 1;

          const accessToken =
            makeAccessToken(
              account,
              sequence,
            );

          const refreshToken =
            `refresh-${account.role}-${sequence}`;

          tokens.set(
            accessToken,
            account,
          );

          refreshTokens.set(
            refreshToken,
            account,
          );

          await fulfillJson(
            route,
            sessionPayload(
              account,
              accessToken,
              refreshToken,
            ),
          );

          return;
        }

        if (
          grantType ===
          "refresh_token"
        ) {
          const account =
            body?.refresh_token
              ? refreshTokens.get(
                  body.refresh_token,
                )
              : undefined;

          if (!account) {
            await fulfillJson(
              route,
              {
                code:
                  "refresh_token_not_found",
                message:
                  "Invalid refresh token",
              },
              400,
            );

            return;
          }

          sequence += 1;

          const accessToken =
            makeAccessToken(
              account,
              sequence,
            );

          const refreshToken =
            `refresh-${account.role}-refreshed-${sequence}`;

          tokens.set(
            accessToken,
            account,
          );

          refreshTokens.set(
            refreshToken,
            account,
          );

          await fulfillJson(
            route,
            sessionPayload(
              account,
              accessToken,
              refreshToken,
            ),
          );

          return;
        }
      }

      if (
        url.pathname ===
        "/auth/v1/user"
      ) {
        const headers =
          await request.allHeaders();

        const authorization =
          headers.authorization ?? "";

        const accessToken =
          authorization.replace(
            /^Bearer\s+/i,
            "",
          );

        const account =
          accountFromAccessToken(
            accessToken,
            tokens,
          );

        if (!account) {
          await fulfillJson(
            route,
            {
              code: "bad_jwt",
              message:
                "Invalid JWT",
            },
            401,
          );

          return;
        }

        await fulfillJson(
          route,
          supabaseUser(account),
        );

        return;
      }

      if (
        url.pathname ===
        "/auth/v1/logout"
      ) {
        await fulfillJson(
          route,
          {},
        );

        return;
      }

      await fulfillJson(
        route,
        {},
      );
    },
  );

  await page.route(
    "http://api.parksmart.test/**",
    async (route) => {
      const request =
        route.request();

      if (
        request.method() ===
        "OPTIONS"
      ) {
        await route.fulfill({
          status: 204,
          headers:
            responseHeaders(),
        });

        return;
      }

      const url =
        new URL(request.url());

      const headers =
        await request.allHeaders();

      const authorization =
        headers.authorization ?? "";

      const token =
        authorization.replace(
          /^Bearer\s+/i,
          "",
        );

      const account =
        accountFromAccessToken(
          token,
          tokens,
        );

      if (
        url.pathname ===
        "/api/v1/auth/me"
      ) {
        if (!account) {
          await fulfillJson(
            route,
            failure(
              "INVALID_TOKEN",
              "Token is invalid.",
            ),
            401,
          );

          return;
        }

        await fulfillJson(
          route,
          success({
            id: account.id,
            email:
              account.email,
            full_name:
              account.role ===
              "admin"
                ? "Admin E2E"
                : "User E2E",
            role:
              account.role,
            parking_user_id:
              account.parking_user_id,
            default_vehicle_id:
              account.default_vehicle_id,
          }),
        );

        return;
      }

      if (!account) {
        await fulfillJson(
          route,
          failure(
            "AUTH_REQUIRED",
            "Authentication required.",
          ),
          401,
        );

        return;
      }

      if (
        url.pathname ===
        "/api/v1/parking/map"
      ) {
        await fulfillJson(
          route,
          success({
            floor_id: "F1",
            nodes: [],
            edges: [],
            slots: [],
          }),
        );

        return;
      }

      if (
        url.pathname ===
        "/api/v1/parking/slots"
      ) {
        await fulfillJson(
          route,
          success([]),
        );

        return;
      }

      if (
        url.pathname ===
        "/api/v1/parking/status"
      ) {
        await fulfillJson(
          route,
          success({
            total: 40,
            available: 40,
            reserved: 0,
            occupied: 0,
            by_zone: {
              A: {
                AVAILABLE: 10,
                RESERVED: 0,
                OCCUPIED: 0,
              },
              B: {
                AVAILABLE: 10,
                RESERVED: 0,
                OCCUPIED: 0,
              },
              C: {
                AVAILABLE: 10,
                RESERVED: 0,
                OCCUPIED: 0,
              },
              D: {
                AVAILABLE: 10,
                RESERVED: 0,
                OCCUPIED: 0,
              },
            },
          }),
        );

        return;
      }

      if (
        url.pathname ===
          "/api/v1/locations/current" ||
        url.pathname ===
          "/api/v1/reservations/active" ||
        url.pathname ===
          "/api/v1/sessions/active"
      ) {
        await fulfillJson(
          route,
          failure(
            "NOT_FOUND",
            "Not found.",
          ),
          404,
        );

        return;
      }

      if (
        url.pathname.startsWith(
          "/api/v1/admin/",
        )
      ) {
        await fulfillJson(
          route,
          success([]),
        );

        return;
      }

      await fulfillJson(
        route,
        success({}),
      );
    },
  );
}

async function login(
  page: Page,
  account: Account,
) {
  await page.goto("/login");

  await page
    .getByLabel("Email")
    .fill(account.email);

  await page
    .getByLabel("Mật khẩu")
    .fill(account.password);

  await page
    .getByRole(
      "button",
      {
        name: "Đăng nhập",
      },
    )
    .click();
}

test.beforeEach(
  async ({ page }) => {
    await installAuthMocks(
      page,
    );
  },
);

test(
  "guest cannot access user or admin routes",
  async ({ page }) => {
    await page.goto("/");

    await expect(
      page,
    ).toHaveURL(/\/login$/);

    await page.goto(
      "/admin",
    );

    await expect(
      page,
    ).toHaveURL(/\/login$/);
  },
);

test(
  "invalid login shows a safe error without role selection",
  async ({ page }) => {
    await page.goto(
      "/login",
    );

    await page
      .getByLabel("Email")
      .fill(
        "invalid@example.com",
      );

    await page
      .getByLabel("Mật khẩu")
      .fill(
        "wrong-password",
      );

    await page
      .getByRole(
        "button",
        {
          name: "Đăng nhập",
        },
      )
      .click();

    await expect(
      page.locator(
        'p[role="alert"]',
      ),
    ).toHaveText(
      "Email hoặc mật khẩu không đúng.",
    );

    await expect(
      page.locator("select"),
    ).toHaveCount(0);
  },
);

test(
  "user login routes to chat, survives reload, blocks admin, and logs out",
  async ({ page }) => {
    await login(
      page,
      USER,
    );

    await expect(
      page,
    ).toHaveURL(/\/$/);

    await page.reload();

    await expect(
      page,
    ).toHaveURL(/\/$/);

    await page.goto(
      "/admin",
    );

    await expect(
      page,
    ).toHaveURL(/\/$/);

    await page
      .getByRole(
        "button",
        {
          name: "Đăng xuất",
        },
      )
      .click();

    await expect(
      page,
    ).toHaveURL(/\/login$/);
  },
);

test(
  "admin login routes to dashboard and redirects away from user route",
  async ({ page }) => {
    await login(
      page,
      ADMIN,
    );

    await expect(
      page,
    ).toHaveURL(/\/admin$/);

    await page.goto("/");

    await expect(
      page,
    ).toHaveURL(/\/admin$/);
  },
);