/**
 * Responsive viewport state (M22 — v2.4).
 *
 * One shared reactive `window.innerWidth` listener installed once per
 * page, so every component that needs to ask `isMobile` cheap-checks
 * the same source of truth.
 *
 * Breakpoints follow Element Plus + Tailwind convention:
 *   mobile  : < 768
 *   tablet  : 768 .. 1023
 *   desktop : >= 1024
 *
 * SSR safe: when `window` is undefined we report desktop and skip the
 * listener; the value flips on `onMounted` once the browser hydrates.
 */
import { computed, onMounted, onUnmounted, ref, type ComputedRef, type Ref } from 'vue'

export const BP_MOBILE_MAX = 767
export const BP_TABLET_MAX = 1023
export const BP_DESKTOP_MIN = 1024

const width = ref<number>(typeof window === 'undefined' ? 1280 : window.innerWidth)
let installed = false
let refCount = 0

function onResize(): void {
  width.value = window.innerWidth
}

function ensureInstalled(): void {
  if (installed || typeof window === 'undefined') return
  window.addEventListener('resize', onResize, { passive: true })
  installed = true
}

export interface ResponsiveState {
  width: Ref<number>
  isMobile: ComputedRef<boolean>
  isTablet: ComputedRef<boolean>
  isDesktop: ComputedRef<boolean>
  /** True for mobile + tablet (< 1024) — handy for "collapse three-pane" UIs. */
  isCompact: ComputedRef<boolean>
}

export function useResponsive(): ResponsiveState {
  onMounted(() => {
    ensureInstalled()
    refCount += 1
    // Sync once on mount in case width changed before listener attached.
    if (typeof window !== 'undefined') width.value = window.innerWidth
  })
  onUnmounted(() => {
    refCount = Math.max(0, refCount - 1)
    // We intentionally never remove the listener — toggling it per-mount
    // is more error-prone than the trivial cost of one passive listener.
  })

  return {
    width,
    isMobile: computed(() => width.value <= BP_MOBILE_MAX),
    isTablet: computed(() => width.value > BP_MOBILE_MAX && width.value <= BP_TABLET_MAX),
    isDesktop: computed(() => width.value >= BP_DESKTOP_MIN),
    isCompact: computed(() => width.value <= BP_TABLET_MAX),
  }
}
