# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: auth.spec.ts >> admin login routes to dashboard and redirects away from user route
- Location: e2e\auth.spec.ts:732:5

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
  642 | 
  643 |     await expect(
  644 |       page,
  645 |     ).toHaveURL(/\/login$/);
  646 |   },
  647 | );
  648 | 
  649 | test(
  650 |   "invalid login shows a safe error without role selection",
  651 |   async ({ page }) => {
  652 |     await page.goto(
  653 |       "/login",
  654 |     );
  655 | 
  656 |     await page
  657 |       .getByLabel("Email")
  658 |       .fill(
  659 |         "invalid@example.com",
  660 |       );
  661 | 
  662 |     await page
  663 |       .getByLabel("Mật khẩu")
  664 |       .fill(
  665 |         "wrong-password",
  666 |       );
  667 | 
  668 |     await page
  669 |       .getByRole(
  670 |         "button",
  671 |         {
  672 |           name: "Đăng nhập",
  673 |         },
  674 |       )
  675 |       .click();
  676 | 
  677 |     await expect(
  678 |       page.locator(
  679 |         'p[role="alert"]',
  680 |       ),
  681 |     ).toHaveText(
  682 |       "Email hoặc mật khẩu không đúng.",
  683 |     );
  684 | 
  685 |     await expect(
  686 |       page.locator("select"),
  687 |     ).toHaveCount(0);
  688 |   },
  689 | );
  690 | 
  691 | test(
  692 |   "user login routes to chat, survives reload, blocks admin, and logs out",
  693 |   async ({ page }) => {
  694 |     await login(
  695 |       page,
  696 |       USER,
  697 |     );
  698 | 
  699 |     await expect(
  700 |       page,
  701 |     ).toHaveURL(/\/$/);
  702 | 
  703 |     await page.reload();
  704 | 
  705 |     await expect(
  706 |       page,
  707 |     ).toHaveURL(/\/$/);
  708 | 
  709 |     await page.goto(
  710 |       "/admin",
  711 |     );
  712 | 
  713 |     await expect(
  714 |       page,
  715 |     ).toHaveURL(/\/$/);
  716 | 
  717 |     await page
  718 |       .getByRole(
  719 |         "button",
  720 |         {
  721 |           name: "Đăng xuất",
  722 |         },
  723 |       )
  724 |       .click();
  725 | 
  726 |     await expect(
  727 |       page,
  728 |     ).toHaveURL(/\/login$/);
  729 |   },
  730 | );
  731 | 
  732 | test(
  733 |   "admin login routes to dashboard and redirects away from user route",
  734 |   async ({ page }) => {
  735 |     await login(
  736 |       page,
  737 |       ADMIN,
  738 |     );
  739 | 
  740 |     await expect(
  741 |       page,
> 742 |     ).toHaveURL(/\/admin$/);
      |       ^ Error: expect(page).toHaveURL(expected) failed
  743 | 
  744 |     await page.goto("/");
  745 | 
  746 |     await expect(
  747 |       page,
  748 |     ).toHaveURL(/\/admin$/);
  749 |   },
  750 | );
```