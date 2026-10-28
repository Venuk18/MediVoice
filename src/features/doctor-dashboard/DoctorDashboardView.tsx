import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  Clock,
  FileText,
  History,
  Search,
  Stethoscope,
  XCircle,
} from 'lucide-react';
import { usePlatform } from '../../context/PlatformContext';
import { StaffAuthGate } from '../../components/ui/StaffAuthGate';
import { ApiError, medivoiceApi } from '../../services/api';
import { AppointmentRead, AppointmentSlotRead } from '../../types/api';

export const DoctorDashboardView: React.FC = () => {
  const {
    staffProfile,
    doctors,
    appointments,
    auditEvents,
    refreshOperationalData,
  } = usePlatform();

  const [selectedDoctorFilter, setSelectedDoctorFilter] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedAppointment, setSelectedAppointment] = useState<AppointmentRead | null>(null);
  const [doctorOpenSlots, setDoctorOpenSlots] = useState<AppointmentSlotRead[]>([]);

  // Action form state
  const [completionNotes, setCompletionNotes] = useState<string>(
    'Outpatient consultation completed; vitals and treatment plan reviewed.'
  );
  const [cancellationReason, setCancellationReason] = useState<string>(
    'Clinician schedule adjustment — patient notified for rebooking.'
  );
  const [followUpDays, setFollowUpDays] = useState<number>(14);
  const [followUpNotes, setFollowUpNotes] = useState<string>(
    'Review diagnostic panel and symptom progression in 2 weeks.'
  );
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Default to the logged-in doctor's ID if available
  useEffect(() => {
    if (staffProfile?.doctor_id) {
      setSelectedDoctorFilter('ALL');
    }
  }, [staffProfile?.doctor_id]);

  const filteredAppointments = appointments.filter((appt) => {
    if (selectedDoctorFilter !== 'ALL' && appt.doctor_id !== selectedDoctorFilter) {
      return false;
    }
    if (statusFilter !== 'ALL' && appt.appointment_status !== statusFilter) {
      return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      const blob = `${appt.patient_reference} ${appt.doctor_name || ''} ${
        appt.doctor_specialty || ''
      } ${appt.reason_category} ${appt.slot_id}`.toLowerCase();
      if (!blob.includes(q)) return false;
    }
    return true;
  });

  useEffect(() => {
    if (filteredAppointments.length > 0) {
      const stillPresent = filteredAppointments.find((a) => a.id === selectedAppointment?.id);
      setSelectedAppointment(stillPresent || filteredAppointments[0]);
    } else {
      setSelectedAppointment(null);
    }
  }, [appointments, selectedDoctorFilter, statusFilter, searchQuery]);

  // Load open slots for currently active doctor filter (or first doctor)
  useEffect(() => {
    const targetDocId =
      selectedDoctorFilter !== 'ALL'
        ? selectedDoctorFilter
        : staffProfile?.doctor_id || doctors[0]?.id;
    if (!targetDocId) return;
    medivoiceApi
      .getDoctorSlots(targetDocId)
      .then((slots) => setDoctorOpenSlots(slots))
      .catch(() => setDoctorOpenSlots([]));
  }, [selectedDoctorFilter, staffProfile?.doctor_id, doctors, appointments]);

  const handleCompleteVisit = async () => {
    if (!selectedAppointment || actionLoading) return;
    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await medivoiceApi.completeAppointment(
        selectedAppointment.id,
        completionNotes.trim() || 'Visit concluded'
      );
      setSelectedAppointment(updated);
      setActionSuccess(
        `Appointment ${updated.patient_reference} marked COMPLETED and synchronized with Patient Portal.`
      );
      await refreshOperationalData();
    } catch (err) {
      setActionError(
        err instanceof ApiError ? err.message : 'Unable to mark appointment completed.'
      );
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancelVisit = async () => {
    if (!selectedAppointment || actionLoading) return;
    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await medivoiceApi.cancelAppointment(
        selectedAppointment.id,
        cancellationReason.trim() || 'Cancelled from Doctor Dashboard'
      );
      setSelectedAppointment(updated);
      setActionSuccess(
        `Appointment cancelled and slot ${updated.slot_id} released back to AVAILABLE.`
      );
      await refreshOperationalData();
    } catch (err) {
      setActionError(
        err instanceof ApiError ? err.message : 'Unable to cancel appointment.'
      );
    } finally {
      setActionLoading(false);
    }
  };

  const handleSaveFollowUp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAppointment || actionLoading) return;
    if (!followUpNotes.trim() || followUpNotes.trim().length < 3) {
      setActionError('Please enter follow-up operational instructions.');
      return;
    }

    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const targetDate = new Date(
        Date.now() + Math.max(1, followUpDays) * 86400 * 1000
      ).toISOString();
      const updated = await medivoiceApi.recordFollowUp(
        selectedAppointment.id,
        targetDate,
        followUpNotes.trim()
      );
      setSelectedAppointment(updated);
      setActionSuccess(
        `Follow-up recommendation recorded for ${updated.patient_reference} (${followUpDays} days).`
      );
      await refreshOperationalData();
    } catch (err) {
      setActionError(
        err instanceof ApiError ? err.message : 'Failed to record follow-up recommendation.'
      );
    } finally {
      setActionLoading(false);
    }
  };

  const confirmedCount = appointments.filter((a) => a.appointment_status === 'CONFIRMED').length;
  const completedCount = appointments.filter((a) => a.appointment_status === 'COMPLETED').length;
  const cancelledCount = appointments.filter((a) => a.appointment_status === 'CANCELLED').length;
  const followUpCount = appointments.filter((a) => a.follow_up_recommended).length;

  const appointmentAudits = auditEvents.filter((ev) => ev.entity_type === 'Appointment');

  return (
    <StaffAuthGate
      requiredRoles={['DOCTOR']}
      workspaceTitle="Doctor Clinical Schedule & Consultation Workspace"
      workspaceSubtitle="Protected physician workspace for reviewing outpatient schedules, completing consultations, releasing cancelled slots, and recording operational follow-up instructions."
    >
      <div className="mx-auto max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-8">
        {/* Workspace Header */}
        <div className="flex flex-col justify-between gap-4 border-b border-[#334155] pb-5 sm:flex-row sm:items-end">
          <div>
            <div className="flex items-center gap-2 font-mono text-xs text-[#2DD4BF]">
              <span>Workspace / Clinical Schedule / {staffProfile?.display_name}</span>
            </div>
            <h1 className="mt-1 font-display text-2xl font-bold text-[#E5EDF7] sm:text-3xl">
              Physician Consultation & Schedule Operations
            </h1>
            <p className="mt-1 text-sm text-[#94A3B8]">
              Synchronized with patient appointment bookings (`GET /api/v1/appointments`, `POST /complete`, `POST /cancel`, `POST /follow-up`).
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="rounded-lg border border-[#2DD4BF]/40 bg-[#2DD4BF]/10 px-3 py-1.5 font-mono text-xs font-semibold text-[#2DD4BF]">
              Active Clinician: {staffProfile?.display_name} ({staffProfile?.role})
            </span>
          </div>
        </div>

        {/* Summary Metric Bar */}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-4">
            <span className="font-mono text-xs uppercase text-[#94A3B8]">
              Confirmed Queue
            </span>
            <p className="mt-1 font-mono text-2xl font-bold text-[#38BDF8] tabular-nums">
              {confirmedCount}
            </p>
            <span className="text-xs text-[#94A3B8]">Awaiting consultation</span>
          </div>

          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-4">
            <span className="font-mono text-xs uppercase text-[#94A3B8]">
              Completed Visits
            </span>
            <p className="mt-1 font-mono text-2xl font-bold text-emerald-400 tabular-nums">
              {completedCount}
            </p>
            <span className="text-xs text-[#94A3B8]">Concluded in system</span>
          </div>

          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-4">
            <span className="font-mono text-xs uppercase text-[#94A3B8]">
              Follow-Ups Flagged
            </span>
            <p className="mt-1 font-mono text-2xl font-bold text-[#2DD4BF] tabular-nums">
              {followUpCount}
            </p>
            <span className="text-xs text-[#94A3B8]">With operational instructions</span>
          </div>

          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-4">
            <span className="font-mono text-xs uppercase text-[#94A3B8]">
              Cancelled / Released
            </span>
            <p className="mt-1 font-mono text-2xl font-bold text-rose-400 tabular-nums">
              {cancelledCount}
            </p>
            <span className="text-xs text-[#94A3B8]">Slots returned to pool</span>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#334155] bg-[#111B2E] p-4">
          <div className="flex flex-wrap items-center gap-2">
            <select
              aria-label="Filter by Doctor"
              value={selectedDoctorFilter}
              onChange={(e) => setSelectedDoctorFilter(e.target.value)}
              className="rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
            >
              <option value="ALL">All Hospital Physicians ({doctors.length})</option>
              {doctors.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.display_name} ({d.specialty})
                </option>
              ))}
            </select>

            {(['ALL', 'CONFIRMED', 'COMPLETED', 'CANCELLED'] as const).map((st) => (
              <button
                key={st}
                type="button"
                onClick={() => setStatusFilter(st)}
                className={`rounded-lg px-3 py-2 font-mono text-xs font-medium transition-colors ${
                  statusFilter === st
                    ? 'bg-[#2DD4BF] text-[#0B1020] font-semibold'
                    : 'border border-[#334155] bg-[#0B1020] text-[#94A3B8] hover:text-[#E5EDF7]'
                }`}
              >
                {st}
              </button>
            ))}
          </div>

          <div className="relative min-w-[240px] flex-1 sm:max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-[#94A3B8]" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search patient ID, reason, or slot..."
              className="w-full rounded-lg border border-[#334155] bg-[#0B1020] pl-9 pr-3 py-2 text-xs text-[#E5EDF7] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none"
            />
          </div>
        </div>

        {/* Main 12-Column Split: 7-Column High-Density Appointment Grid + 5-Column Consultation Detail & Transition Controls */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="lg:col-span-7 space-y-5">
            <div className="rounded-xl border border-[#334155] bg-[#111B2E] overflow-hidden">
              <div className="flex items-center justify-between border-b border-[#334155] px-5 py-3.5">
                <h2 className="font-display text-sm font-bold text-[#E5EDF7]">
                  Outpatient Consultation Queue
                </h2>
                <span className="font-mono text-xs text-[#94A3B8] tabular-nums">
                  Showing {filteredAppointments.length} of {appointments.length}
                </span>
              </div>

              {filteredAppointments.length === 0 ? (
                <div className="p-8 text-center text-xs text-[#94A3B8]">
                  No appointments match the current filter criteria.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-[#334155] bg-[#0B1020]/70 font-mono text-[11px] uppercase text-[#94A3B8]">
                        <th className="py-3 px-4">Patient Ref</th>
                        <th className="py-3 px-4">Physician & Specialty</th>
                        <th className="py-3 px-4">Slot & Schedule</th>
                        <th className="py-3 px-4">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#334155]/60 text-xs">
                      {filteredAppointments.map((appt) => {
                        const isSelected = selectedAppointment?.id === appt.id;
                        return (
                          <tr
                            key={appt.id}
                            onClick={() => {
                              setSelectedAppointment(appt);
                              setActionError(null);
                              setActionSuccess(null);
                            }}
                            className={`cursor-pointer transition-colors ${
                              isSelected
                                ? 'bg-[#2DD4BF]/10'
                                : 'hover:bg-[#0B1020]/60'
                            }`}
                          >
                            <td className="py-3 px-4 font-mono font-semibold text-[#E5EDF7] tabular-nums">
                              {appt.patient_reference}
                              {appt.follow_up_recommended && (
                                <span className="ml-1.5 rounded bg-[#2DD4BF]/20 px-1.5 py-0.5 text-[10px] text-[#2DD4BF]">
                                  Follow-Up
                                </span>
                              )}
                            </td>
                            <td className="py-3 px-4">
                              <div className="font-semibold text-[#E5EDF7]">
                                {appt.doctor_name || appt.doctor_id}
                              </div>
                              <div className="text-[11px] text-[#94A3B8]">
                                {appt.doctor_specialty} • {appt.reason_category}
                              </div>
                            </td>
                            <td className="py-3 px-4 font-mono text-[11px] text-[#94A3B8] tabular-nums">
                              <div className="text-[#E5EDF7]">{appt.slot_id}</div>
                              <div>
                                {appt.slot_start_time
                                  ? new Date(appt.slot_start_time).toLocaleString([], {
                                      month: 'short',
                                      day: 'numeric',
                                      hour: '2-digit',
                                      minute: '2-digit',
                                    })
                                  : 'Scheduled'}
                              </div>
                            </td>
                            <td className="py-3 px-4">
                              <span
                                className={`inline-block rounded px-2 py-0.5 font-mono text-[10px] font-semibold ${
                                  appt.appointment_status === 'CONFIRMED'
                                    ? 'bg-[#38BDF8]/15 text-[#38BDF8] border border-[#38BDF8]/30'
                                    : appt.appointment_status === 'COMPLETED'
                                    ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                                    : 'bg-rose-500/15 text-rose-300 border border-rose-500/30'
                                }`}
                              >
                                {appt.appointment_status}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Open Slots Timeline for Selected Physician */}
            <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-5">
              <div className="flex items-center justify-between border-b border-[#334155] pb-3">
                <div className="flex items-center gap-2">
                  <Calendar className="h-4 w-4 text-[#38BDF8]" />
                  <h3 className="font-display text-sm font-bold text-[#E5EDF7]">
                    Available Unbooked Slots in Physician Calendar
                  </h3>
                </div>
                <span className="font-mono text-xs text-[#2DD4BF] tabular-nums">
                  {doctorOpenSlots.length} open
                </span>
              </div>

              <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
                {doctorOpenSlots.slice(0, 6).map((slot) => (
                  <div
                    key={slot.id}
                    className="rounded-lg border border-[#334155] bg-[#0B1020] p-2.5 font-mono text-xs tabular-nums"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-[#2DD4BF]">{slot.id}</span>
                      <span className="text-[10px] text-emerald-300">{slot.status}</span>
                    </div>
                    <p className="mt-1 text-[11px] text-[#94A3B8]">
                      {new Date(slot.start_time).toLocaleString([], {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right 5 Columns: Selected Appointment Detail & Status Transition Controls */}
          <div className="lg:col-span-5 space-y-5">
            {selectedAppointment ? (
              <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-5 space-y-4">
                <div className="flex items-start justify-between border-b border-[#334155] pb-3.5">
                  <div>
                    <span className="font-mono text-[11px] text-[#94A3B8]">
                      SELECTED APPOINTMENT RECORD
                    </span>
                    <h2 className="mt-0.5 font-display text-lg font-bold text-[#E5EDF7]">
                      {selectedAppointment.patient_reference}
                    </h2>
                    <p className="text-xs text-[#2DD4BF]">
                      {selectedAppointment.doctor_name} • {selectedAppointment.doctor_specialty}
                    </p>
                  </div>

                  <span
                    className={`rounded-lg px-2.5 py-1 font-mono text-xs font-bold ${
                      selectedAppointment.appointment_status === 'CONFIRMED'
                        ? 'bg-[#38BDF8]/15 text-[#38BDF8] border border-[#38BDF8]/30'
                        : selectedAppointment.appointment_status === 'COMPLETED'
                        ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                        : 'bg-rose-500/15 text-rose-300 border border-rose-500/30'
                    }`}
                  >
                    {selectedAppointment.appointment_status}
                  </span>
                </div>

                {actionError && (
                  <div className="flex items-start gap-2 rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-200">
                    <AlertCircle className="h-4 w-4 shrink-0 text-rose-400 mt-0.5" />
                    <span>{actionError}</span>
                  </div>
                )}

                {actionSuccess && (
                  <div className="flex items-start gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-xs text-emerald-200">
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400 mt-0.5" />
                    <span>{actionSuccess}</span>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-2.5 font-mono text-xs">
                  <div className="rounded-lg border border-[#334155] bg-[#0B1020] p-2.5">
                    <span className="block text-[10px] text-[#94A3B8]">SLOT ID</span>
                    <span className="text-[#E5EDF7]">{selectedAppointment.slot_id}</span>
                  </div>
                  <div className="rounded-lg border border-[#334155] bg-[#0B1020] p-2.5">
                    <span className="block text-[10px] text-[#94A3B8]">REASON CATEGORY</span>
                    <span className="font-sans text-[#E5EDF7] truncate block">
                      {selectedAppointment.reason_category}
                    </span>
                  </div>
                </div>

                {/* Permitted Status Transitions (CONFIRMED -> COMPLETED / CANCELLED) */}
                {selectedAppointment.appointment_status === 'CONFIRMED' ? (
                  <div className="space-y-3 border-t border-[#334155] pt-4">
                    <h3 className="font-mono text-xs font-semibold uppercase text-[#2DD4BF]">
                      Permitted Consultation Status Transitions
                    </h3>

                    <div>
                      <label
                        htmlFor="doc-complete-notes"
                        className="block text-xs font-medium text-[#E5EDF7]"
                      >
                        Operational Completion Note
                      </label>
                      <input
                        id="doc-complete-notes"
                        type="text"
                        value={completionNotes}
                        onChange={(e) => setCompletionNotes(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                      />
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        disabled={actionLoading}
                        onClick={() => void handleCompleteVisit()}
                        className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-lg bg-[#2DD4BF] px-3.5 py-2 text-xs font-semibold text-[#0B1020] hover:bg-[#2DD4BF]/90 disabled:opacity-50"
                      >
                        <CheckCircle2 className="h-4 w-4" />
                        <span>Mark Visit COMPLETED</span>
                      </button>

                      <button
                        type="button"
                        disabled={actionLoading}
                        onClick={() => void handleCancelVisit()}
                        className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3.5 py-2 text-xs font-semibold text-rose-300 hover:bg-rose-500/20 disabled:opacity-50"
                      >
                        <XCircle className="h-4 w-4" />
                        <span>Cancel & Release Slot</span>
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-lg border border-[#334155] bg-[#0B1020] p-3 text-xs text-[#94A3B8]">
                    Status is <strong>{selectedAppointment.appointment_status}</strong>. Terminal consultation states cannot be reverted to CONFIRMED.
                  </div>
                )}

                {/* Record Follow-Up Recommendation Form */}
                <form
                  onSubmit={(e) => void handleSaveFollowUp(e)}
                  className="space-y-3 border-t border-[#334155] pt-4"
                >
                  <div className="flex items-center justify-between">
                    <h3 className="font-mono text-xs font-semibold uppercase text-[#38BDF8]">
                      Record Follow-Up Recommendation
                    </h3>
                    <span className="font-mono text-[10px] text-[#94A3B8]">
                      POST /follow-up
                    </span>
                  </div>

                  <div className="grid grid-cols-3 gap-2">
                    <div>
                      <label
                        htmlFor="followup-days"
                        className="block text-xs font-medium text-[#E5EDF7]"
                      >
                        In (Days)
                      </label>
                      <input
                        id="followup-days"
                        type="number"
                        min={1}
                        max={365}
                        value={followUpDays}
                        onChange={(e) => setFollowUpDays(Number(e.target.value) || 14)}
                        className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-2.5 py-2 font-mono text-xs text-[#E5EDF7] tabular-nums"
                      />
                    </div>
                    <div className="col-span-2">
                      <label
                        htmlFor="followup-notes"
                        className="block text-xs font-medium text-[#E5EDF7]"
                      >
                        Operational Follow-Up Instructions
                      </label>
                      <input
                        id="followup-notes"
                        type="text"
                        value={followUpNotes}
                        onChange={(e) => setFollowUpNotes(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#E5EDF7]"
                      />
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={actionLoading}
                    className="w-full inline-flex items-center justify-center gap-1.5 rounded-lg border border-[#38BDF8]/50 bg-[#38BDF8]/15 px-3.5 py-2 text-xs font-semibold text-[#38BDF8] hover:bg-[#38BDF8]/25 disabled:opacity-50"
                  >
                    <FileText className="h-3.5 w-3.5" />
                    <span>Save Follow-Up Instructions</span>
                  </button>
                </form>
              </div>
            ) : (
              <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-6 text-xs text-[#94A3B8]">
                Select an appointment from the consultation queue to inspect details or update status.
              </div>
            )}

            {/* Appointment Audit Trail */}
            <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-5">
              <div className="flex items-center justify-between border-b border-[#334155] pb-3">
                <div className="flex items-center gap-2">
                  <History className="h-4 w-4 text-[#2DD4BF]" />
                  <h3 className="font-display text-sm font-bold text-[#E5EDF7]">
                    Appointment Audit Events
                  </h3>
                </div>
                <span className="font-mono text-xs text-[#94A3B8] tabular-nums">
                  {appointmentAudits.length} events
                </span>
              </div>

              <div className="mt-3 max-h-48 overflow-y-auto space-y-2 pr-1 font-mono text-[11px]">
                {appointmentAudits.slice(0, 8).map((ev) => (
                  <div
                    key={ev.id}
                    className="rounded border border-[#334155] bg-[#0B1020] p-2.5 space-y-1"
                  >
                    <div className="flex items-center justify-between text-[#2DD4BF]">
                      <span>{ev.action}</span>
                      <span className="text-[10px] text-[#94A3B8]">
                        {new Date(ev.created_at).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                          second: '2-digit',
                        })}
                      </span>
                    </div>
                    <p className="text-[#94A3B8] truncate">
                      Actor: {ev.actor_reference} • Entity: {ev.entity_id.slice(0, 10)}...
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </StaffAuthGate>
  );
};
