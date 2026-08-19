# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: auth.spec.ts >> invalid login shows a safe error without role selection
- Location: e2e\auth.spec.ts:257:5

# Error details

```
Error: expect(locator).toHaveText(expected) failed

Locator: getByRole('alert')
Expected: "Email hoặc mật khẩu không đúng."
Error: strict mode violation: getByRole('alert') resolved to 2 elements:
    1) <p role="alert" class="auth-module__dgWmnG__loginError">Email hoặc mật khẩu không đúng.</p> aka getByText('Email hoặc mật khẩu không đú')
    2) <div role="alert" aria-live="assertive" id="__next-route-announcer__"></div> aka locator('[id="__next-route-announcer__"]')

Call log:
  - Expect "toHaveText" with timeout 10000ms
  - waiting for getByRole('alert')

```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - main [ref=e2]:
    - generic [ref=e3]:
      - generic [ref=e4]:
        - generic [ref=e5]: P
        - generic [ref=e6]:
          - heading "Đăng nhập ParkSmart" [level=1] [ref=e7]
          - paragraph [ref=e8]: Sử dụng tài khoản đã được quản trị viên cấp.
      - generic [ref=e9]:
        - generic [ref=e10]: Email
        - textbox "Email" [ref=e11]: invalid@example.com
      - generic [ref=e12]:
        - generic [ref=e13]: Mật khẩu
        - textbox "Mật khẩu" [ref=e14]: wrong-password
      - alert [ref=e15]: Email hoặc mật khẩu không đúng.
      - button "Đăng nhập" [ref=e16] [cursor=pointer]
      - paragraph [ref=e17]: Vai trò được xác định bởi backend ParkSmart; màn hình này không cho phép chọn quyền.
  - alert [ref=e18]
```

# Test source

```ts
  163 |     const url = new URL(request.url());
  164 |     const authorization = request.headers()["authorization"] ?? "";
  165 |     const token = authorization.replace(/^Bearer\s+/i, "");
  166 |     const account = tokens.get(token);
  167 | 
  168 |     if (url.pathname === "/api/v1/auth/me") {
  169 |       if (!account) {
  170 |         await fulfillJson(route, failure("INVALID_TOKEN", "Token is invalid."), 401);
  171 |         return;
  172 |       }
  173 |       await fulfillJson(
  174 |         route,
  175 |         success({
  176 |           id: account.id,
  177 |           email: account.email,
  178 |           full_name: account.role === "admin" ? "Admin E2E" : "User E2E",
  179 |           role: account.role,
  180 |           parking_user_id: account.parking_user_id,
  181 |           default_vehicle_id: account.default_vehicle_id,
  182 |         }),
  183 |       );
  184 |       return;
  185 |     }
  186 | 
  187 |     if (!account) {
  188 |       await fulfillJson(route, failure("AUTH_REQUIRED", "Authentication required."), 401);
  189 |       return;
  190 |     }
  191 | 
  192 |     if (url.pathname === "/api/v1/parking/map") {
  193 |       await fulfillJson(
  194 |         route,
  195 |         success({ floor_id: "F1", nodes: [], edges: [], slots: [] }),
  196 |       );
  197 |       return;
  198 |     }
  199 |     if (url.pathname === "/api/v1/parking/slots") {
  200 |       await fulfillJson(route, success([]));
  201 |       return;
  202 |     }
  203 |     if (url.pathname === "/api/v1/parking/status") {
  204 |       await fulfillJson(
  205 |         route,
  206 |         success({
  207 |           total: 40,
  208 |           available: 40,
  209 |           reserved: 0,
  210 |           occupied: 0,
  211 |           by_zone: {
  212 |             A: { AVAILABLE: 10, RESERVED: 0, OCCUPIED: 0 },
  213 |             B: { AVAILABLE: 10, RESERVED: 0, OCCUPIED: 0 },
  214 |             C: { AVAILABLE: 10, RESERVED: 0, OCCUPIED: 0 },
  215 |             D: { AVAILABLE: 10, RESERVED: 0, OCCUPIED: 0 },
  216 |           },
  217 |         }),
  218 |       );
  219 |       return;
  220 |     }
  221 |     if (
  222 |       url.pathname === "/api/v1/locations/current" ||
  223 |       url.pathname === "/api/v1/reservations/active" ||
  224 |       url.pathname === "/api/v1/sessions/active"
  225 |     ) {
  226 |       await fulfillJson(route, failure("NOT_FOUND", "Not found."), 404);
  227 |       return;
  228 |     }
  229 |     if (url.pathname.startsWith("/api/v1/admin/")) {
  230 |       await fulfillJson(route, success([]));
  231 |       return;
  232 |     }
  233 | 
  234 |     await fulfillJson(route, success({}));
  235 |   });
  236 | }
  237 | 
  238 | async function login(page: Page, account: Account) {
  239 |   await page.goto("/login");
  240 |   await page.getByLabel("Email").fill(account.email);
  241 |   await page.getByLabel("Mật khẩu").fill(account.password);
  242 |   await page.getByRole("button", { name: "Đăng nhập" }).click();
  243 | }
  244 | 
  245 | test.beforeEach(async ({ page }) => {
  246 |   await installAuthMocks(page);
  247 | });
  248 | 
  249 | test("guest cannot access user or admin routes", async ({ page }) => {
  250 |   await page.goto("/");
  251 |   await expect(page).toHaveURL(/\/login$/);
  252 | 
  253 |   await page.goto("/admin");
  254 |   await expect(page).toHaveURL(/\/login$/);
  255 | });
  256 | 
  257 | test("invalid login shows a safe error without role selection", async ({ page }) => {
  258 |   await page.goto("/login");
  259 |   await page.getByLabel("Email").fill("invalid@example.com");
  260 |   await page.getByLabel("Mật khẩu").fill("wrong-password");
  261 |   await page.getByRole("button", { name: "Đăng nhập" }).click();
  262 | 
> 263 |   await expect(page.getByRole("alert")).toHaveText("Email hoặc mật khẩu không đúng.");
      |                                         ^ Error: expect(locator).toHaveText(expected) failed
  264 |   await expect(page.locator("select")).toHaveCount(0);
  265 | });
  266 | 
  267 | test("user login routes to chat, survives reload, blocks admin, and logs out", async ({ page }) => {
  268 |   await login(page, USER);
  269 |   await expect(page).toHaveURL(/\/$/);
  270 | 
  271 |   await page.reload();
  272 |   await expect(page).toHaveURL(/\/$/);
  273 | 
  274 |   await page.goto("/admin");
  275 |   await expect(page).toHaveURL(/\/$/);
  276 | 
  277 |   await page.getByRole("button", { name: "Đăng xuất" }).click();
  278 |   await expect(page).toHaveURL(/\/login$/);
  279 | });
  280 | 
  281 | test("admin login routes to dashboard and redirects away from user route", async ({ page }) => {
  282 |   await login(page, ADMIN);
  283 |   await expect(page).toHaveURL(/\/admin$/);
  284 | 
  285 |   await page.goto("/");
  286 |   await expect(page).toHaveURL(/\/admin$/);
  287 | });
  288 | 
```