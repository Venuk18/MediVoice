const STORAGE_KEY = 'medivoice_patient_appointment_refs_v1';

export function getPatientAppointmentReferences(): string[] {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed.filter((value): value is string => typeof value === 'string')
      : [];
  } catch {
    return [];
  }
}

export function rememberPatientAppointmentReference(reference: string): void {
  const value = reference.trim();
  if (!value) return;
  const references = new Set(getPatientAppointmentReferences());
  references.add(value);
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...references]));
  } catch {
    // The patient can still copy and use the booking reference manually.
  }
}

export function forgetPatientAppointmentReference(reference: string): void {
  try {
    const next = getPatientAppointmentReferences().filter((item) => item !== reference);
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Session storage may be unavailable in a restricted browser context.
  }
}

export function clearPatientAppointmentReferences(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Session storage may be unavailable in a restricted browser context.
  }
}
