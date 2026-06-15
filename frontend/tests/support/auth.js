import { expect } from "@playwright/test";

export async function openLoginDialog(page, { waitForVisible = false } = {}) {
  const loginButton = page.getByRole("button", { name: "登录" });
  if (waitForVisible) {
    await expect(loginButton).toBeVisible();
  }
  await loginButton.click();
}

export async function submitLoginCredentials(page, account) {
  await page.getByLabel("用户名").fill(account.username);
  await page.getByLabel("密码").fill(account.password);
  await page.locator(".modal-panel").getByRole("button", { name: "登录" }).click();
}

export async function login(
  page,
  account,
  { indicator = "name", waitForLoginButton = false } = {}
) {
  await openLoginDialog(page, { waitForVisible: waitForLoginButton });
  await submitLoginCredentials(page, account);

  if (indicator === "none") {
    return;
  }

  if (indicator === "avatar") {
    await expect(page.locator(".user-avatar")).toBeVisible();
    return;
  }

  if (account.nickname) {
    await expect(page.locator(".user-name")).toContainText(account.nickname);
  }
}

export async function logout(page, { waitForLoginButton = false } = {}) {
  await page.getByRole("button", { name: "退出" }).click();
  if (waitForLoginButton) {
    await expect(page.getByRole("button", { name: "登录" })).toBeVisible();
  }
}
