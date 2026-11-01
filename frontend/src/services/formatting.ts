const HOSPITAL_TIME_ZONE = 'Asia/Kolkata';

export function formatHospitalDateTime(value: string): string {
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: HOSPITAL_TIME_ZONE,
  }).format(new Date(value)) + ' IST';
}

export function formatHospitalTime(value: string): string {
  return new Intl.DateTimeFormat('en-IN', {
    hour: 'numeric',
    minute: '2-digit',
    timeZone: HOSPITAL_TIME_ZONE,
  }).format(new Date(value)) + ' IST';
}
