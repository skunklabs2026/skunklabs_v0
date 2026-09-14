/**
 * Test helpers that are not fixtures.
 *
 * See `factories.ts` for telemetry builders.
 */

import { afterEach, beforeEach } from "vitest";

/**
 * Silence jsdom's reporting of render errors for the current describe block.
 *
 * Error-boundary tests throw during render on purpose. React re-throws so the
 * host environment can report it, and jsdom then prints about ten lines of
 * stack trace per throw — enough to make a passing run look like a failing
 * one in CI. This suppresses that, and only that: it is scoped to the block
 * that opts in, so an *unexpected* throw anywhere else is still loud.
 */
export function expectRenderErrors(): void {
  const swallow = (event: ErrorEvent) => event.preventDefault();
  beforeEach(() => window.addEventListener("error", swallow));
  afterEach(() => window.removeEventListener("error", swallow));
}
