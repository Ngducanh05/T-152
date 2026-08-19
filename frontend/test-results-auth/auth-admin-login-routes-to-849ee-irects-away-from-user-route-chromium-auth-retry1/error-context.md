# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: auth.spec.ts >> admin login routes to dashboard and redirects away from user route
- Location: e2e\auth.spec.ts:343:5

# Error details

```
Error: expect(page).toHaveURL(expected) failed

Expected pattern: /\/admin$/
Received string:  "http://127.0.0.1:3200/login"
Timeout: 10000ms

Call log:
  - Expect "toHaveURL" with timeout 10000ms
    23 × locator resolved to <html lang="vi">…</html>
       - unexpected value "http://127.0.0.1:3200/login"

```

```yaml
- main:
  - heading "Đăng nhập ParkSmart" [level=1]
  - paragraph: Sử dụng tài khoản đã được quản trị viên cấp.
  - text: Email
  - textbox "Email": admin@example.com
  - text: Mật khẩu
  - textbox "Mật khẩu": admin-password-e2e
  - alert: Không thể xác minh tài khoản ParkSmart. Vui lòng đăng nhập lại.
  - button "Đăng nhập"
  - paragraph: Vai trò được xác định bởi backend ParkSmart; màn hình này không cho phép chọn quyền.
- alert
```

# Test source

```ts
  245 |     }
  246 | 
  247 |     if (!account) {
  248 |       await fulfillJson(route, failure("AUTH_REQUIRED", "Authentication required."), 401);
  249 |       return;
  250 |     }
  251 | 
  252 |     if (url.pathname === "/api/v1/parking/map") {
  253 |       await fulfillJson(
  254 |         route,
  255 |         success({ floor_id: "F1", nodes: [], edges: [], slots: [] }),
  256 |       );
  257 |       return;
  258 |     }
  259 |     if (url.pathname === "/api/v1/parking/slots") {
  260 |       await fulfillJson(route, success([]));
  261 |       return;
  262 |     }
  263 |     if (url.pathname === "/api/v1/parking/status") {
  264 |       await fulfillJson(
  265 |         route,
  266 |         success({
  267 |           total: 40,
  268 |           available: 40,
  269 |           reserved: 0,
  270 |           occupied: 0,
  271 |           by_zone: {
  272 |             A: { AVAILABLE: 10, RESERVED: 0, OCCUPIED: 0 },
  273 |             B: { AVAILABLE: 10, RESERVED: 0, OCCUPIED: 0 },
  274 |             C: { AVAILABLE: 10, RESERVED: 0, OCCUPIED: 0 },
  275 |             D: { AVAILABLE: 10, RESERVED: 0, OCCUPIED: 0 },
  276 |           },
  277 |         }),
  278 |       );
  279 |       return;
  280 |     }
  281 |     if (
  282 |       url.pathname === "/api/v1/locations/current" ||
  283 |       url.pathname === "/api/v1/reservations/active" ||
  284 |       url.pathname === "/api/v1/sessions/active"
  285 |     ) {
  286 |       await fulfillJson(route, failure("NOT_FOUND", "Not found."), 404);
  287 |       return;
  288 |     }
  289 |     if (url.pathname.startsWith("/api/v1/admin/")) {
  290 |       await fulfillJson(route, success([]));
  291 |       return;
  292 |     }
  293 | 
  294 |     await fulfillJson(route, success({}));
  295 |   });
  296 | }
  297 | 
  298 | async function login(page: Page, account: Account) {
  299 |   await page.goto("/login");
  300 |   await page.getByLabel("Email").fill(account.email);
  301 |   await page.getByLabel("Mật khẩu").fill(account.password);
  302 |   await page.getByRole("button", { name: "Đăng nhập" }).click();
  303 | }
  304 | 
  305 | test.beforeEach(async ({ page }) => {
  306 |   await installAuthMocks(page);
  307 | });
  308 | 
  309 | test("guest cannot access user or admin routes", async ({ page }) => {
  310 |   await page.goto("/");
  311 |   await expect(page).toHaveURL(/\/login$/);
  312 | 
  313 |   await page.goto("/admin");
  314 |   await expect(page).toHaveURL(/\/login$/);
  315 | });
  316 | 
  317 | test("invalid login shows a safe error without role selection", async ({ page }) => {
  318 |   await page.goto("/login");
  319 |   await page.getByLabel("Email").fill("invalid@example.com");
  320 |   await page.getByLabel("Mật khẩu").fill("wrong-password");
  321 |   await page.getByRole("button", { name: "Đăng nhập" }).click();
  322 | 
  323 |   await expect(
  324 |     page.locator('p[role="alert"]'),
  325 |   ).toHaveText("Email hoặc mật khẩu không đúng.");
  326 |   await expect(page.locator("select")).toHaveCount(0);
  327 | });
  328 | 
  329 | test("user login routes to chat, survives reload, blocks admin, and logs out", async ({ page }) => {
  330 |   await login(page, USER);
  331 |   await expect(page).toHaveURL(/\/$/);
  332 | 
  333 |   await page.reload();
  334 |   await expect(page).toHaveURL(/\/$/);
  335 | 
  336 |   await page.goto("/admin");
  337 |   await expect(page).toHaveURL(/\/$/);
  338 | 
  339 |   await page.getByRole("button", { name: "Đăng xuất" }).click();
  340 |   await expect(page).toHaveURL(/\/login$/);
  341 | });
  342 | 
  343 | test("admin login routes to dashboard and redirects away from user route", async ({ page }) => {
  344 |   await login(page, ADMIN);
> 345 |   await expect(page).toHaveURL(/\/admin$/);
      |                      ^ Error: expect(page).toHaveURL(expected) failed
  346 | 
  347 |   await page.goto("/");
  348 |   await expect(page).toHaveURL(/\/admin$/);
  349 | });
```