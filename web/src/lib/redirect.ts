/** Hosted-page redirects (Stripe checkout/portal) — a seam jsdom can mock. */
export function redirectTo(url: string): void {
  window.location.assign(url);
}
