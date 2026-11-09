/**
 * Sanitizes error messages by scrubbing potential PII, Indian mobile numbers,
 * authentication tokens, and patient references before logging.
 */
export function sanitizeErrorMessage(message: string | null | undefined): string {
  if (!message) return '';
  return String(message)
    // Scrub JWT / Bearer tokens
    .replace(/Bearer\s+[A-Za-z0-9._-]+/gi, 'Bearer [REDACTED_TOKEN]')
    .replace(/token=([A-Za-z0-9._-]+)/gi, 'token=[REDACTED_TOKEN]')
    .replace(/"access_token"\s*:\s*"[^"]+"/gi, '"access_token": "[REDACTED_TOKEN]"')
    // Scrub 10-digit Indian phone numbers and +91 variations
    .replace(/(?:\+91[\s-]?)?[6-9]\d{9}\b/g, '[REDACTED_PHONE]')
    .replace(/\b\d{10}\b/g, '[REDACTED_PHONE]')
    // Scrub patient references
    .replace(/\bPAT-[A-Z0-9-]+\b/gi, 'PAT-[REDACTED]')
    // Scrub email addresses
    .replace(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g, '[REDACTED_EMAIL]')
    // Scrub credentials / passwords / api keys
    .replace(/\b(password|secret|apikey|api_key)\s*[:=]\s*[^\s,]+/gi, '$1=[REDACTED]');
}

/**
 * Sanitizes component stacks by scrubbing raw text and attributes.
 */
export function sanitizeComponentStack(stack?: string | null): string {
  if (!stack) return '';
  return sanitizeErrorMessage(stack);
}

/**
 * Safely logs error metadata without leaking patient data or credentials.
 */
export function logSanitizedError(
  error: Error | unknown,
  errorInfo?: { componentStack?: string | null },
  boundaryName = 'ErrorBoundary'
): void {
  const errName = error instanceof Error ? error.name : 'UnknownError';
  const rawMsg = error instanceof Error ? error.message : String(error);
  const sanitizedMsg = sanitizeErrorMessage(rawMsg);
  const sanitizedStack = errorInfo?.componentStack
    ? sanitizeComponentStack(errorInfo.componentStack)
    : '';

  // Safe structured console output
  console.error(`[MediVoice ${boundaryName}] Handled component crash:`, {
    errorName: errName,
    message: sanitizedMsg,
    componentStack: sanitizedStack ? sanitizedStack.slice(0, 500) : undefined,
    timestamp: new Date().toISOString(),
  });
}

