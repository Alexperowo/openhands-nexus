export interface AnnouncedStatus { status: string; error: string }

/** Opening old work is silent; a current request for help or error must still be announced. */
export function shouldAnnounceStatus(before: AnnouncedStatus, current: AnnouncedStatus): boolean {
  if (!current.status) return false;
  if (!before.status) {
    return Boolean(current.error) || ["error", "stuck", "awaiting_user_input", "awaiting_user_confirmation"].includes(current.status);
  }
  return current.status !== before.status || Boolean(current.error && current.error !== before.error);
}
