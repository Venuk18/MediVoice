import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  Clock,
  FileText,
  ShieldCheck,
  Stethoscope,
  User,
  XCircle,
} from 'lucide-react';
import { usePlatform } from '../../context/PlatformContext';
import { ApiError, medivoiceApi } from '../../services/api';
import { AppointmentRead, AppointmentSlotRead, DoctorRead } from '../../types/api';

const SPECIALTY_FILTERS = [
  'All Specialties',
  'Cardiology',
  'Neurology',
  'Orthopedics',
  'Pediatrics',
  'General Medicine',
];

export const AppointmentBookingSection: React.FC = () => {
  const {
    doctors,
    appointments,
    activePatientRef,
    setActivePatientRef,
    refreshOperationalData,
  } = usePlatform();

  const [selectedSpecialty, setSelectedSpecialty] = useState<string>('All Specialties');
  const [selectedDoctor, setSelectedDoctor] = useState<DoctorRead | null>(null);
  const [availableSlots, setAvailableSlots] = useState<AppointmentSlotRead[]>([]);
  const [slotsLoading, setSlotsLoading] = useState<boolean>(false);
  const [selectedSlot, setSelectedSlot] = useState<AppointmentSlotRead | null>(null);
  const [reasonCategory, setReasonCategory] = useState<string>(
    'Outpatient Specialist Consultation'
  );

  // Two-step explicit confirmation state
  const [awaitingExplicitConfirmation, setAwaitingExplicitConfirmation] =
    useState<boolean>(false);
  const [isSubmittingBooking, setIsSubmittingBooking] = useState<boolean>(false);
  const [bookingError, setBookingError] = useState<string | null>(null);
  const [confirmedBooking, setConfirmedBooking] = useState<AppointmentRead | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const filteredDoctors =
    selectedSpecialty === 'All Specialties'
      ? doctors
      : doctors.filter(
          (doc) =>
            doc.specialty.toLowerCase() === selectedSpecialty.toLowerCase() ||
            (doc.department_name || '').toLowerCase() === selectedSpecialty.toLowerCase()
        );

  useEffect(() => {
    if (!selectedDoctor && doctors.length > 0) {
      setSelectedDoctor(doctors[0]);
    }
  }, [doctors, selectedDoctor]);

  const loadDoctorSlots = async (doctorId: string) => {
    setSlotsLoading(true);
    setSelectedSlot(null);
    setAwaitingExplicitConfirmation(false);
    setBookingError(null);
    try {
      const slots = await medivoiceApi.getDoctorSlots(doctorId);
      setAvailableSlots(slots);
      if (slots.length > 0) {
        setSelectedSlot(slots[0]);
      }
    } catch (err) {
      setBookingError(
        err instanceof ApiError
          ? err.message
          : 'Unable to load available slots for the selected physician.'
      );
      setAvailableSlots([]);
    } finally {
      setSlotsLoading(false);
    }
  };

  useEffect(() => {
    if (selectedDoctor) {
      void loadDoctorSlots(selectedDoctor.id);
    }
  }, [selectedDoctor]);

  const handlePrepareConfirmation = (e: React.FormEvent) => {
    e.preventDefault();
    setBookingError(null);
    setConfirmedBooking(null);

    if (!selectedDoctor) {
      setBookingError('Please select a consulting specialist.');
      return;
    }
    if (!selectedSlot) {
      setBookingError('Please select an available appointment slot.');
      return;
    }
    if (!activePatientRef.trim()) {
      setBookingError('Please enter your synthetic patient reference ID.');
      return;
    }
    if (!reasonCategory.trim() || reasonCategory.trim().length < 3) {
      setBookingError('Please enter a brief consultation reason (at least 3 characters).');
      return;
    }

    setAwaitingExplicitConfirmation(true);
  };

  const handleExecuteConfirmedBooking = async () => {
    if (!selectedDoctor || !selectedSlot || isSubmittingBooking) return;
    setIsSubmittingBooking(true);
    setBookingError(null);

    try {
      const created = await medivoiceApi.bookAppointment({
        patient_reference: activePatientRef.trim(),
        doctor_id: selectedDoctor.id,
        slot_id: selectedSlot.id,
        reason_category: reasonCategory.trim(),
      });
      setConfirmedBooking(created);
      setAwaitingExplicitConfirmation(false);
      await loadDoctorSlots(selectedDoctor.id);
      await refreshOperationalData();
    } catch (err) {
      setBookingError(
        err instanceof ApiError
          ? err.message
          : 'Appointment booking failed due to a backend validation error.'
      );
      setAwaitingExplicitConfirmation(false);
    } finally {
      setIsSubmittingBooking(false);
    }
  };

  const handleCancelPatientAppointment = async (appointmentId: string) => {
    if (cancellingId) return;
    setCancellingId(appointmentId);
    setBookingError(null);
    try {
      await medivoiceApi.cancelAppointment(
        appointmentId,
        'Patient requested cancellation from Patient Portal'
      );
      if (selectedDoctor) {
        await loadDoctorSlots(selectedDoctor.id);
      }
      await refreshOperationalData();
    } catch (err) {
      setBookingError(
        err instanceof ApiError ? err.message : 'Unable to cancel the selected appointment.'
      );
    } finally {
      setCancellingId(null);
    }
  };

  const formatSlotWindow = (startIso?: string | null, endIso?: string | null) => {
    if (!startIso) return 'Scheduled Slot';
    const start = new Date(startIso);
    const datePart = start.toLocaleDateString('en-IN', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
    const startTimePart = start.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
    });
    if (!endIso) return `${datePart} • ${startTimePart}`;
    const end = new Date(endIso);
    const endTimePart = end.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
    });
    return `${datePart} • ${startTimePart} – ${endTimePart}`;
  };

  const patientAppointments = appointments.filter(
    (a) =>
      !activePatientRef.trim() ||
      a.patient_reference.toLowerCase().includes(activePatientRef.trim().toLowerCase())
  );

  return (
    <section id="appointments-section" className="space-y-8">
      <div className="flex flex-col justify-between gap-4 border-b border-[#334155] pb-5 sm:flex-row sm:items-end">
        <div>
          <span className="font-mono text-xs font-semibold uppercase tracking-wider text-[#2DD4BF]">
            01 • Specialist Discovery & Slot Booking
          </span>
          <h2 className="mt-1 font-display text-2xl font-bold text-[#E5EDF7] sm:text-3xl">
            Outpatient Consultation Scheduling
          </h2>
          <p className="mt-1 text-sm text-[#94A3B8]">
            Real-time physician slot availability with row-level lock protection and explicit two-step patient confirmation.
          </p>
        </div>

        {/* Specialty Filter Bar */}
        <div className="flex flex-wrap gap-1.5">
          {SPECIALTY_FILTERS.map((spec) => {
            const active = selectedSpecialty === spec;
            return (
              <button
                key={spec}
                type="button"
                onClick={() => setSelectedSpecialty(spec)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                  active
                    ? 'bg-[#2DD4BF] text-[#0B1020] font-semibold'
                    : 'border border-[#334155] bg-[#111B2E] text-[#94A3B8] hover:text-[#E5EDF7]'
                }`}
              >
                {spec}
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left 7 Columns: Specialist Roster & Open Slots */}
        <div className="lg:col-span-7 space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {filteredDoctors.map((doc) => {
              const isSelected = selectedDoctor?.id === doc.id;
              return (
                <button
                  key={doc.id}
                  type="button"
                  onClick={() => setSelectedDoctor(doc)}
                  className={`flex flex-col justify-between rounded-xl border p-4 text-left transition-all ${
                    isSelected
                      ? 'border-[#2DD4BF] bg-[#111B2E] ring-1 ring-[#2DD4BF]/50'
                      : 'border-[#334155] bg-[#111B2E]/60 hover:border-[#38BDF8]/60'
                  }`}
                >
                  <div>
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2.5">
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[#334155] bg-[#0B1020] text-[#38BDF8]">
                          <Stethoscope className="h-4 w-4" />
                        </div>
                        <div>
                          <h3 className="font-display text-sm font-bold text-[#E5EDF7]">
                            {doc.display_name}
                          </h3>
                          <p className="text-xs font-medium text-[#2DD4BF]">{doc.specialty}</p>
                        </div>
                      </div>
                      <span className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] text-emerald-300">
                        ACTIVE
                      </span>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center justify-between border-t border-[#334155]/60 pt-2.5 font-mono text-[11px] text-[#94A3B8]">
                    <span>Dept: {doc.department_name || doc.specialty}</span>
                    <span className="text-[#38BDF8]">
                      {isSelected ? 'Selected →' : 'View Slots'}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Open Slots Grid for Selected Doctor */}
          {selectedDoctor && (
            <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-5">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#334155] pb-3">
                <div>
                  <h3 className="font-display text-sm font-bold text-[#E5EDF7]">
                    Available Slots — {selectedDoctor.display_name}
                  </h3>
                  <p className="text-xs text-[#94A3B8]">
                    Only unbooked future slots (`status = AVAILABLE`) are returned by `/api/v1/doctors/{selectedDoctor.id.slice(0, 8)}.../slots`
                  </p>
                </div>
                <span className="rounded bg-[#0B1020] px-2.5 py-1 font-mono text-xs text-[#2DD4BF] border border-[#334155] tabular-nums">
                  {availableSlots.length} Open Slots
                </span>
              </div>

              {slotsLoading ? (
                <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                  {[1, 2, 3, 4].map((n) => (
                    <div
                      key={n}
                      className="h-14 animate-pulse rounded-lg border border-[#334155]/60 bg-[#0B1020]/60"
                    />
                  ))}
                </div>
              ) : availableSlots.length === 0 ? (
                <div className="mt-4 rounded-lg border border-[#334155] bg-[#0B1020] p-4 text-xs text-[#94A3B8]">
                  No open future slots available for {selectedDoctor.display_name}. Select another specialist or cancel an existing reservation to release a slot.
                </div>
              ) : (
                <div className="mt-4 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                  {availableSlots.map((slot) => {
                    const isSlotPicked = selectedSlot?.id === slot.id;
                    return (
                      <button
                        key={slot.id}
                        type="button"
                        onClick={() => {
                          setSelectedSlot(slot);
                          setAwaitingExplicitConfirmation(false);
                        }}
                        className={`flex items-center justify-between rounded-lg border px-3.5 py-2.5 text-left transition-all ${
                          isSlotPicked
                            ? 'border-[#2DD4BF] bg-[#2DD4BF]/15 text-[#E5EDF7]'
                            : 'border-[#334155] bg-[#0B1020] text-[#94A3B8] hover:border-[#38BDF8]/60 hover:text-[#E5EDF7]'
                        }`}
                      >
                        <div className="flex items-center gap-2.5">
                          <Clock className="h-4 w-4 text-[#2DD4BF] shrink-0" />
                          <div>
                            <p className="font-mono text-xs font-semibold text-[#E5EDF7] tabular-nums">
                              {formatSlotWindow(slot.start_time, slot.end_time)}
                            </p>
                            <p className="font-mono text-[10px] text-[#94A3B8]">
                              Slot ID: {slot.id}
                            </p>
                          </div>
                        </div>
                        <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-emerald-300">
                          {slot.status}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right 5 Columns: Two-Step Explicit Booking Confirmation & Patient Appointments */}
        <div className="lg:col-span-5 space-y-5">
          <form
            onSubmit={handlePrepareConfirmation}
            className="rounded-xl border border-[#334155] bg-[#111B2E] p-5 space-y-4"
          >
            <div className="flex items-center justify-between border-b border-[#334155] pb-3">
              <div>
                <h3 className="font-display text-base font-bold text-[#E5EDF7]">
                  Consultation Reservation
                </h3>
                <p className="text-xs text-[#94A3B8]">
                  Backed by `POST /api/v1/appointments` with unique slot constraint
                </p>
              </div>
              <Calendar className="h-5 w-5 text-[#2DD4BF]" />
            </div>

            {bookingError && (
              <div className="flex items-start gap-2.5 rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-200">
                <AlertCircle className="h-4 w-4 shrink-0 text-rose-400 mt-0.5" />
                <span>{bookingError}</span>
              </div>
            )}

            {confirmedBooking && (
              <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3.5 text-xs text-emerald-200 space-y-1">
                <div className="flex items-center gap-2 font-semibold text-emerald-300">
                  <CheckCircle2 className="h-4 w-4" />
                  <span>Appointment Confirmed by Backend</span>
                </div>
                <p className="font-mono text-[11px] tabular-nums">
                  ID: {confirmedBooking.id} • Status: {confirmedBooking.appointment_status}
                </p>
                <p>
                  Doctor: <strong>{confirmedBooking.doctor_name}</strong> ({confirmedBooking.slot_id})
                </p>
              </div>
            )}

            <div>
              <label
                htmlFor="booking-patient-ref"
                className="block text-xs font-medium text-[#E5EDF7]"
              >
                Synthetic Patient Reference
              </label>
              <div className="relative mt-1">
                <User className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-[#94A3B8]" />
                <input
                  id="booking-patient-ref"
                  type="text"
                  value={activePatientRef}
                  onChange={(e) => {
                    setActivePatientRef(e.target.value);
                    setAwaitingExplicitConfirmation(false);
                  }}
                  className="w-full rounded-lg border border-[#334155] bg-[#0B1020] pl-9 pr-3 py-2 font-mono text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 font-mono text-xs">
              <div className="rounded-lg border border-[#334155] bg-[#0B1020] p-2.5">
                <span className="block text-[10px] text-[#94A3B8]">SELECTED DOCTOR</span>
                <span className="mt-0.5 block font-sans font-semibold text-[#E5EDF7] truncate">
                  {selectedDoctor?.display_name || 'None'}
                </span>
              </div>
              <div className="rounded-lg border border-[#334155] bg-[#0B1020] p-2.5">
                <span className="block text-[10px] text-[#94A3B8]">SELECTED SLOT</span>
                <span className="mt-0.5 block text-[#2DD4BF] truncate">
                  {selectedSlot?.id || 'None'}
                </span>
              </div>
            </div>

            <div>
              <label
                htmlFor="booking-reason-input"
                className="block text-xs font-medium text-[#E5EDF7]"
              >
                Visit Reason / Symptom Summary
              </label>
              <input
                id="booking-reason-input"
                type="text"
                value={reasonCategory}
                onChange={(e) => {
                  setReasonCategory(e.target.value);
                  setAwaitingExplicitConfirmation(false);
                }}
                placeholder="e.g., Follow-up blood pressure & ECG review"
                className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#E5EDF7] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none"
              />
            </div>

            {!awaitingExplicitConfirmation ? (
              <button
                type="submit"
                disabled={!selectedDoctor || !selectedSlot}
                className="w-full rounded-lg bg-[#2DD4BF] px-4 py-2.5 text-xs font-semibold text-[#0B1020] transition-colors hover:bg-[#2DD4BF]/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#38BDF8] disabled:opacity-50"
              >
                Review & Prepare Booking Confirmation
              </button>
            ) : (
              <div className="rounded-xl border border-[#2DD4BF] bg-[#0B1020] p-4 space-y-3">
                <div className="flex items-start gap-2 text-xs text-[#E5EDF7]">
                  <ShieldCheck className="h-4 w-4 shrink-0 text-[#2DD4BF] mt-0.5" />
                  <div>
                    <p className="font-semibold text-[#2DD4BF]">
                      Explicit Patient Confirmation Step
                    </p>
                    <p className="mt-1 text-[#94A3B8]">
                      Confirming will lock slot <span className="font-mono text-[#E5EDF7]">{selectedSlot?.id}</span> with{' '}
                      <strong className="text-[#E5EDF7]">{selectedDoctor?.display_name}</strong> for patient{' '}
                      <span className="font-mono text-[#E5EDF7]">{activePatientRef}</span>.
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={isSubmittingBooking}
                    onClick={() => void handleExecuteConfirmedBooking()}
                    className="flex-1 rounded-lg bg-[#2DD4BF] px-3 py-2 text-xs font-semibold text-[#0B1020] hover:bg-[#2DD4BF]/90 disabled:opacity-50"
                  >
                    {isSubmittingBooking ? 'Committing Transaction...' : 'Confirm & Commit Booking'}
                  </button>
                  <button
                    type="button"
                    disabled={isSubmittingBooking}
                    onClick={() => setAwaitingExplicitConfirmation(false)}
                    className="rounded-lg border border-[#334155] bg-[#111B2E] px-3 py-2 text-xs text-[#94A3B8] hover:text-[#E5EDF7]"
                  >
                    Modify
                  </button>
                </div>
              </div>
            )}
          </form>

          {/* Synchronized Patient Appointments List */}
          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-5">
            <div className="flex items-center justify-between border-b border-[#334155] pb-3">
              <h3 className="font-display text-sm font-bold text-[#E5EDF7]">
                Appointments for {activePatientRef || 'All Patients'}
              </h3>
              <span className="font-mono text-xs text-[#94A3B8] tabular-nums">
                {patientAppointments.length} records
              </span>
            </div>

            <div className="mt-3 max-h-64 overflow-y-auto space-y-2.5 pr-1">
              {patientAppointments.length === 0 ? (
                <p className="py-4 text-center text-xs text-[#94A3B8]">
                  No appointments found for patient reference {activePatientRef}.
                </p>
              ) : (
                patientAppointments.map((appt) => (
                  <div
                    key={appt.id}
                    className="rounded-lg border border-[#334155] bg-[#0B1020] p-3 text-xs space-y-2"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <span className="font-display font-bold text-[#E5EDF7]">
                          {appt.doctor_name || appt.doctor_id}
                        </span>
                        <span className="ml-2 text-[#2DD4BF]">
                          {appt.doctor_specialty}
                        </span>
                      </div>
                      <span
                        className={`rounded px-2 py-0.5 font-mono text-[10px] font-semibold ${
                          appt.appointment_status === 'CONFIRMED'
                            ? 'bg-[#38BDF8]/15 text-[#38BDF8] border border-[#38BDF8]/30'
                            : appt.appointment_status === 'COMPLETED'
                            ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                            : 'bg-rose-500/15 text-rose-300 border border-rose-500/30'
                        }`}
                      >
                        {appt.appointment_status}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[11px] text-[#94A3B8] tabular-nums">
                      <span>{formatSlotWindow(appt.slot_start_time, appt.slot_end_time)}</span>
                      <span>Slot: {appt.slot_id}</span>
                    </div>

                    <p className="text-[#94A3B8]">Reason: {appt.reason_category}</p>

                    {appt.follow_up_recommended && appt.follow_up_notes && (
                      <div className="rounded border border-[#2DD4BF]/30 bg-[#2DD4BF]/10 p-2 text-[11px] text-[#E5EDF7]">
                        <div className="flex items-center gap-1.5 font-semibold text-[#2DD4BF]">
                          <FileText className="h-3.5 w-3.5" />
                          <span>Doctor Follow-Up Recommendation</span>
                        </div>
                        <p className="mt-0.5 text-[#E5EDF7]/90">{appt.follow_up_notes}</p>
                      </div>
                    )}

                    {appt.appointment_status === 'CONFIRMED' && (
                      <div className="flex justify-end pt-1">
                        <button
                          type="button"
                          disabled={cancellingId === appt.id}
                          onClick={() => void handleCancelPatientAppointment(appt.id)}
                          className="inline-flex items-center gap-1 rounded border border-rose-500/40 bg-rose-500/10 px-2.5 py-1 text-[11px] font-medium text-rose-300 hover:bg-rose-500/20 disabled:opacity-50"
                        >
                          <XCircle className="h-3 w-3" />
                          {cancellingId === appt.id ? 'Cancelling...' : 'Cancel & Release Slot'}
                        </button>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
