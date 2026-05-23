/**
 * Native touch-event gestures (M22 — v2.4).
 *
 * Two primitives, no hammerjs:
 *
 *   useSwipe(elRef, { onLeft, onRight, threshold = 80 })
 *     Detects horizontal swipes on touch devices. Vertical motion within
 *     the same gesture cancels it (so a scroll doesn't accidentally
 *     trigger a swipe).
 *
 *   useLongPress(elRef, handler, { delay = 500 })
 *     Fires `handler({ x, y })` after `delay` ms of stationary touch.
 *     Movement > 10px or a touchend before the timer cancels it. The
 *     handler runs once per touch — multi-finger gestures are ignored.
 *
 * Both safely no-op on SSR / non-touch desktops (no touch event ever
 * fires on a mouse) so they're cheap to mount unconditionally.
 */
import { onMounted, onUnmounted, type Ref } from 'vue'

export interface SwipeOpts {
  onLeft?: () => void
  onRight?: () => void
  onUp?: () => void
  onDown?: () => void
  /** Minimum horizontal distance for a swipe to register. */
  threshold?: number
  /** Max time (ms) for the swipe to complete. Slow drags don't count. */
  maxDuration?: number
}

export function useSwipe(
  elRef: Ref<HTMLElement | null | undefined>,
  opts: SwipeOpts,
): void {
  const threshold = opts.threshold ?? 80
  const maxDuration = opts.maxDuration ?? 800
  let startX = 0
  let startY = 0
  let startT = 0
  let active = false

  function onTouchStart(e: TouchEvent): void {
    if (e.touches.length !== 1) { active = false; return }
    const t = e.touches[0]
    startX = t.clientX
    startY = t.clientY
    startT = Date.now()
    active = true
  }

  function onTouchEnd(e: TouchEvent): void {
    if (!active) return
    active = false
    const t = e.changedTouches[0]
    if (!t) return
    const dx = t.clientX - startX
    const dy = t.clientY - startY
    const dt = Date.now() - startT
    if (dt > maxDuration) return
    const absX = Math.abs(dx)
    const absY = Math.abs(dy)
    // Horizontal wins
    if (absX > absY && absX >= threshold) {
      if (dx < 0) opts.onLeft?.()
      else opts.onRight?.()
      return
    }
    // Vertical
    if (absY > absX && absY >= threshold) {
      if (dy < 0) opts.onUp?.()
      else opts.onDown?.()
    }
  }

  function attach(el: HTMLElement): void {
    el.addEventListener('touchstart', onTouchStart, { passive: true })
    el.addEventListener('touchend', onTouchEnd, { passive: true })
  }
  function detach(el: HTMLElement): void {
    el.removeEventListener('touchstart', onTouchStart)
    el.removeEventListener('touchend', onTouchEnd)
  }

  onMounted(() => {
    const el = elRef.value
    if (el && typeof window !== 'undefined') attach(el)
  })
  onUnmounted(() => {
    const el = elRef.value
    if (el) detach(el)
  })
}

export interface LongPressOpts {
  delay?: number
  /** Movement (px) before the press is cancelled. */
  tolerance?: number
}

export type LongPressHandler = (pos: { x: number; y: number; target: EventTarget | null }) => void

export function useLongPress(
  elRef: Ref<HTMLElement | null | undefined>,
  handler: LongPressHandler,
  opts: LongPressOpts = {},
): void {
  const delay = opts.delay ?? 500
  const tolerance = opts.tolerance ?? 10
  let timer: number | null = null
  let startX = 0
  let startY = 0
  let fired = false
  let originalTarget: EventTarget | null = null

  function clear(): void {
    if (timer !== null) {
      window.clearTimeout(timer)
      timer = null
    }
  }

  function onTouchStart(e: TouchEvent): void {
    if (e.touches.length !== 1) { clear(); return }
    const t = e.touches[0]
    startX = t.clientX
    startY = t.clientY
    fired = false
    originalTarget = e.target
    timer = window.setTimeout(() => {
      fired = true
      handler({ x: startX, y: startY, target: originalTarget })
    }, delay)
  }

  function onTouchMove(e: TouchEvent): void {
    if (timer === null) return
    const t = e.touches[0]
    if (!t) return
    if (Math.abs(t.clientX - startX) > tolerance
        || Math.abs(t.clientY - startY) > tolerance) {
      clear()
    }
  }

  function onTouchEnd(e: TouchEvent): void {
    clear()
    // If long-press fired we suppress the trailing click — the consumer
    // typically opens a context menu and doesn't want the underlying
    // button to also activate.
    if (fired) {
      e.preventDefault()
      fired = false
    }
  }

  function attach(el: HTMLElement): void {
    el.addEventListener('touchstart', onTouchStart, { passive: true })
    el.addEventListener('touchmove', onTouchMove, { passive: true })
    el.addEventListener('touchend', onTouchEnd)
    el.addEventListener('touchcancel', clear, { passive: true })
  }
  function detach(el: HTMLElement): void {
    el.removeEventListener('touchstart', onTouchStart)
    el.removeEventListener('touchmove', onTouchMove)
    el.removeEventListener('touchend', onTouchEnd)
    el.removeEventListener('touchcancel', clear)
  }

  onMounted(() => {
    const el = elRef.value
    if (el && typeof window !== 'undefined') attach(el)
  })
  onUnmounted(() => {
    const el = elRef.value
    if (el) detach(el)
  })
}
