import { expect, test } from '@playwright/test'

test('project list shell renders without horizontal overflow', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('body')).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
  expect(overflow).toBe(false)
})
