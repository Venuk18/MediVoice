import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertCircle,
  ArrowLeft,
  Calendar,
  CheckCircle2,
  ClipboardList,
  Clock,
  LayoutDashboard,
  LogOut,
  Plus,
  RefreshCw,
  Search,
  Stethoscope,
  User,
  XCircle,
} from 'lucide-react';
import { usePlatform } from '../../app/PlatformContext';
import { StaffAuthGate } from '../../components/StaffAuthGate';
import { ApiError, medivoiceApi } from '../../services/api';
import {
  AppointmentRead,
  AppointmentSlotRead,
  AppRoutePath,
} from '../../types/api';

const DOCTOR_SIDEBAR_ITEMS: Array<{
  label: string;
  route: AppRoutePath;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  { label: 'Overview', route: '/doctor', icon: LayoutDashboard },
  { label: 'Appointments', route: '/doctor/appointments', icon: ClipboardList },
  { label: 'Schedule Calendar', route: '/doctor/calendar', icon: Calendar },
  { label: 'Availability & Slots', route: '/doctor/availability', icon: Clock },
  { label: 'Physician Profile', route: '/doctor/profile', icon: User },
];

export const DoctorWorkspaceView: React.FC = () => {
  const {
    currentRoute,
    navigate,
    staffProfile,
    logoutStaff,
    doctors,
    appointments,
    auditEvents,
    refreshOperationalData,
  } = usePlatform();

  const [selectedDoctorId, setSelectedDoctorId] = useState<string>(
    staffProfile?.doctor_id || doctors[0]?.id || '33333333-0001-0000-0000-000000000001'
  );
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedAppointmentId, setSelectedAppointmentId] = useState<string | null>(null);

  // Action & Confirmation state
  const [completionNotes, setCompletionNotes] = useState<string>(
    'Clinical assessment completed. Vitals stable; routine care plan advised.'
  );
  const [followUpDate, setFollowUpDate] = useState<string>(() => {
    const d = new Date(Date.now() + 7 * 86400000);
    return d.toISOString().slice(0, 10);
  });
  const [followUpNotes, setFollowUpNotes] = useState<string>(
    'Review diagnostic panel and symptom progression in 7 days.'
  );
  const [pendingAction, setPendingAction] = useState<
    'COMPLETE' | 'FOLLOW_UP' | 'CANCEL' | null
  >(null);
  const [isSubmittingAction, setIsSubmittingAction] = useState<boolean>(false);

  // Availability / Slot Management state
  const [doctorSlots, setDoctorSlots] = useState<AppointmentSlotRead[]>([]);
  const [slotDate, setSlotDate] = useState<string>(() => {
    const tomorrow = new Date(Date.now() + 86400000);
    return tomorrow.toISOString().slice(0, 10);
  });
  const [slotStartTime, setSlotStartTime] = useState<string>('11:00');
  const [slotEndTime, setSlotEndTime] = useState<string>('11:30');
  const [isCreatingSlot, setIsCreatingSlot] = useState<boolean>(false);

  // Feedback banner
  const [banner, setBanner] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

  useEffect(() => {
    if (staffProfile?.doctor_id) {
      setSelectedDoctorId(staffProfile.doctor_id);
    } else if (doctors.length > 0 && !doctors.some((d) => d.id === selectedDoctorId)) {
      setSelectedDoctorId(doctors[0].id);
    }
  }, [staffProfile?.doctor_id, doctors]);

  const activeDoctor = useMemo(() => {
    return doctors.find((d) => d.id === selectedDoctorId) || doctors[0] || null;
  }, [doctors, selectedDoctorId]);

  const loadDoctorSlots = async (docId: string) => {
    try {
      const slots = await medivoiceApi.getDoctorSlots(docId);
      setDoctorSlots(slots);
    } catch {
      setDoctorSlots([]);
    }
  };

  useEffect(() => {
    if (activeDoctor) {
      void loadDoctorSlots(activeDoctor.id);
    }
  }, [activeDoctor?.id]);

  const doctorAppointments = useMemo(() => {
    return appointments.filter((a) => !activeDoctor || a.doctor_id === activeDoctor.id);
  }, [appointments, activeDoctor]);

  const filteredAppointments = useMemo(() => {
    return doctorAppointments.filter((a) => {
      if (statusFilter !== 'ALL' && a.appointment_status !== statusFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.trim().toLowerCase();
        const hay = `${a.patient_reference} ${a.reason_category} ${a.id}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [doctorAppointments, statusFilter, searchQuery]);

  const selectedAppointment: AppointmentRead | null = useMemo(() => {
    if (!selectedAppointmentId) return filteredAppointments[0] || null;
    return (
      filteredAppointments.find((a) => a.id === selectedAppointmentId) ||
      doctorAppointments.find((a) => a.id === selectedAppointmentId) ||
      filteredAppointments[0] ||
      null
    );
  }, [filteredAppointments, doctorAppointments, selectedAppointmentId]);

  const metrics = useMemo(() => {
    const total = doctorAppointments.length;
    const confirmed = doctorAppointments.filter((a) => a.appointment_status === 'CONFIRMED').length;
    const completed = doctorAppointments.filter((a) => a.appointment_status === 'COMPLETED').length;
    const cancelled = doctorAppointments.filter((a) => a.appointment_status === 'CANCELLED').length;
    return { total, confirmed, completed, cancelled };
  }, [doctorAppointments]);

  const nextConfirmedAppointment = useMemo(() => {
    return (
      doctorAppointments.find((a) => a.appointment_status === 'CONFIRMED') || null
    );
  }, [doctorAppointments]);

  const executeAppointmentAction = async () => {
    if (!selectedAppointment || !pendingAction) return;
    setIsSubmittingAction(true);
    setBanner(null);
    try {
      if (pendingAction === 'COMPLETE') {
        await medivoiceApi.completeAppointment(selectedAppointment.id, completionNotes);
        setBanner({
          type: 'success',
          message: `Appointment ${selectedAppointment.id.slice(0, 8)} marked COMPLETED.`,
        });
      } else if (pendingAction === 'FOLLOW_UP') {
        const isoDate = new Date(`${followUpDate}T10:00:00Z`).toISOString();
        await medivoiceApi.recordFollowUp(selectedAppointment.id, isoDate, followUpNotes);
        setBanner({
          type: 'success',
          message: `Follow-up recommendation persisted for ${selectedAppointment.patient_reference}.`,
        });
      } else if (pendingAction === 'CANCEL') {
        await medivoiceApi.cancelAppointment(
          selectedAppointment.id,
          'Cancelled by attending physician via Doctor Workspace'
        );
        setBanner({
          type: 'success',
          message: `Appointment ${selectedAppointment.id.slice(0, 8)} cancelled and slot released.`,
        });
      }
      setPendingAction(null);
      await refreshOperationalData();
      if (activeDoctor) await loadDoctorSlots(activeDoctor.id);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Unable to update appointment status.';
      setBanner({ type: 'error', message: msg });
    } finally {
      setIsSubmittingAction(false);
    }
  };

  const handlePublishNewSlot = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeDoctor) return;
    setIsCreatingSlot(true);
    setBanner(null);
    try {
      const startIso = new Date(`${slotDate}T${slotStartTime}:00Z`).toISOString();
      const endIso = new Date(`${slotDate}T${slotEndTime}:00Z`).toISOString();
      await medivoiceApi.createDoctorSlot(activeDoctor.id, {
        start_time: startIso,
        end_time: endIso,
      });
      setBanner({
        type: 'success',
        message: `Published new open appointment slot for ${activeDoctor.display_name} on ${slotDate} (${slotStartTime} - ${slotEndTime}).`,
      });
      await loadDoctorSlots(activeDoctor.id);
      await refreshOperationalData();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Unable to create appointment slot.';
      setBanner({ type: 'error', message: msg });
    } finally {
      setIsCreatingSlot(false);
    }
  };

  return (
    <StaffAuthGate
      requiredRoles={['DOCTOR']}
      workspaceTitle="Doctor Clinical Schedule & Appointment Workspace"
      workspaceSubtitle="Review patient consultations, manage daily schedule calendars, publish open availability slots, and record follow-up plans."
    >
      <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A] flex flex-col lg:flex-row">
        {/* Left Role-Specific Sidebar */}
        <aside className="w-full lg:w-64 shrink-0 border-b lg:border-b-0 lg:border-r border-slate-200 bg-white flex flex-col justify-between p-5">
          <div className="space-y-6">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold text-teal-700">
                <Stethoscope className="h-4 w-4" />
                <span>Doctor Workspace</span>
              </div>
              <h2 className="mt-1 font-display text-lg font-bold text-slate-900">
                Aarogya One Hospital
              </h2>
              <p className="text-xs text-slate-500">
                {activeDoctor?.display_name || staffProfile?.display_name} ·{' '}
                {activeDoctor?.specialty || staffProfile?.department}
              </p>
            </div>

            {/* Active Physician Switcher (for Demo Evaluation) */}
            <div>
              <label className="block text-[11px] font-medium text-slate-500">
                Active Physician Schedule
              </label>
              <select
                value={activeDoctor?.id || ''}
                onChange={(e) => setSelectedDoctorId(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs font-medium text-slate-900 focus:border-teal-600 focus:outline-none"
              >
                {doctors.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.display_name} ({d.specialty})
                  </option>
                ))}
              </select>
            </div>

            <nav aria-label="Doctor Workspace Navigation" className="space-y-1">
              {DOCTOR_SIDEBAR_ITEMS.map((item) => {
                const Icon = item.icon;
                const isActive = currentRoute === item.route;
                return (
                  <button
                    key={item.route}
                    type="button"
                    onClick={() => navigate(item.route)}
                    className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors whitespace-nowrap ${
                      isActive
                        ? 'bg-teal-600 text-white font-semibold'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                    }`}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </nav>
          </div>

          <div className="mt-6 border-t border-slate-200 pt-4 space-y-2">
            <button
              type="button"
              onClick={() => navigate('/')}
              className="flex w-full items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-100 whitespace-nowrap"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Patient Hospital Website</span>
            </button>
            <button
              type="button"
              onClick={logoutStaff}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-rose-600 hover:bg-rose-50 whitespace-nowrap"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span>Sign Out ({staffProfile?.username})</span>
            </button>
          </div>
        </aside>

        {/* Main Operational Viewport */}
        <div className="flex-1 p-6 sm:p-8 space-y-6 max-w-[1200px]">
          {/* Contextual Top Header */}
          <div className="flex flex-col justify-between gap-4 border-b border-slate-200 pb-5 sm:flex-row sm:items-center">
            <div>
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <span>Doctor Workspace</span>
                <span aria-hidden="true">/</span>
                <span className="font-semibold text-slate-800">
                  {DOCTOR_SIDEBAR_ITEMS.find((i) => i.route === currentRoute)?.label || 'Overview'}
                </span>
              </div>
              <h1 className="mt-1 font-display text-2xl font-bold text-slate-900">
                {activeDoctor?.display_name} · {activeDoctor?.specialty}
              </h1>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => void refreshOperationalData()}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 whitespace-nowrap"
              >
                <RefreshCw className="h-3.5 w-3.5 text-teal-600" />
                <span>Sync Schedule</span>
              </button>
            </div>
          </div>

          {banner && (
            <div
              className={`flex items-center justify-between rounded-lg border p-4 text-xs ${
                banner.type === 'success'
                  ? 'border-emerald-300 bg-emerald-50 text-emerald-900'
                  : 'border-rose-300 bg-rose-50 text-rose-900'
              }`}
            >
              <div className="flex items-center gap-2">
                {banner.type === 'success' ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                ) : (
                  <AlertCircle className="h-4 w-4 text-rose-600" />
                )}
                <span>{banner.message}</span>
              </div>
              <button
                type="button"
                onClick={() => setBanner(null)}
                className="underline opacity-80 hover:opacity-100"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* KPI Summary Strip */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <span className="text-xs font-medium text-slate-500">Total Appointments</span>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-slate-900">
                {metrics.total}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <span className="text-xs font-medium text-slate-500">Upcoming Confirmed</span>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-teal-700">
                {metrics.confirmed}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <span className="text-xs font-medium text-slate-500">Completed Visits</span>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-emerald-700">
                {metrics.completed}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <span className="text-xs font-medium text-slate-500">Cancelled</span>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-slate-500">
                {metrics.cancelled}
              </p>
            </div>
          </div>

          {/* =================================================================
              SUB-VIEW 1 & 2: OVERVIEW & APPOINTMENTS (`/doctor`, `/doctor/appointments`)
          ================================================================= */}
          {(currentRoute === '/doctor' || currentRoute === '/doctor/appointments') && (
            <>
              {currentRoute === '/doctor' && nextConfirmedAppointment && (
                <div className="rounded-xl border border-teal-200 bg-teal-50/70 p-5 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
                  <div>
                    <p className="text-xs font-semibold text-teal-800">
                      Next Highlighted Patient Consultation
                    </p>
                    <h3 className="mt-1 font-display text-base font-bold text-slate-900">
                      Patient {nextConfirmedAppointment.patient_reference} ·{' '}
                      {nextConfirmedAppointment.reason_category}
                    </h3>
                    <p className="mt-0.5 font-mono text-xs tabular-nums text-slate-600">
                      Scheduled:{' '}
                      {nextConfirmedAppointment.slot_start_time
                        ? new Date(nextConfirmedAppointment.slot_start_time).toLocaleString()
                        : 'Upcoming Slot'}{' '}
                      · Ref: {nextConfirmedAppointment.id.slice(0, 8)}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedAppointmentId(nextConfirmedAppointment.id);
                      navigate('/doctor/appointments');
                    }}
                    className="rounded-lg bg-teal-600 px-4 py-2 text-xs font-semibold text-white hover:bg-teal-700 whitespace-nowrap shrink-0"
                  >
                    Open Consultation Actions
                  </button>
                </div>
              )}

              <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
                {/* Left 7 Cols: Appointments Table */}
                <div className="lg:col-span-7 rounded-xl border border-slate-200 bg-white overflow-hidden">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 p-4">
                    <h2 className="font-display text-sm font-bold text-slate-900">
                      Patient Appointment Queue ({filteredAppointments.length})
                    </h2>
                    <div className="flex items-center gap-2">
                      <div className="relative">
                        <Search className="pointer-events-none absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-400" />
                        <input
                          type="text"
                          value={searchQuery}
                          onChange={(e) => setSearchQuery(e.target.value)}
                          placeholder="Patient ID or reason..."
                          className="rounded-lg border border-slate-200 bg-slate-50 pl-8 pr-2.5 py-1 text-xs text-slate-900 focus:border-teal-600 focus:outline-none"
                        />
                      </div>
                      <select
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                        aria-label="Filter appointments by status"
                        className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700"
                      >
                        <option value="ALL">All Statuses</option>
                        <option value="CONFIRMED">CONFIRMED</option>
                        <option value="COMPLETED">COMPLETED</option>
                        <option value="CANCELLED">CANCELLED</option>
                      </select>
                    </div>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold text-slate-500">
                          <th className="py-2.5 pl-4 pr-2">Ref & Patient</th>
                          <th className="px-2 py-2.5">Reason</th>
                          <th className="px-2 py-2.5">Scheduled Time</th>
                          <th className="py-2.5 pl-2 pr-4">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200 text-xs">
                        {filteredAppointments.length === 0 ? (
                          <tr>
                            <td colSpan={4} className="py-8 text-center text-slate-500">
                              No appointments match the selected filter.
                            </td>
                          </tr>
                        ) : (
                          filteredAppointments.map((appt) => {
                            const isSelected = selectedAppointment?.id === appt.id;
                            return (
                              <tr
                                key={appt.id}
                                onClick={() => {
                                  setSelectedAppointmentId(appt.id);
                                  setPendingAction(null);
                                }}
                                className={`cursor-pointer transition-colors ${
                                  isSelected ? 'bg-teal-50/80' : 'hover:bg-slate-50'
                                }`}
                              >
                                <td className="py-3 pl-4 pr-2 align-top">
                                  <div className="font-mono font-semibold text-slate-900">
                                    {appt.patient_reference}
                                  </div>
                                  <div className="font-mono text-[10px] text-slate-500">
                                    #{appt.id.slice(0, 8)}
                                  </div>
                                </td>
                                <td className="px-2 py-3 align-top text-slate-700">
                                  {appt.reason_category}
                                </td>
                                <td className="px-2 py-3 align-top font-mono text-[11px] tabular-nums text-slate-600">
                                  {appt.slot_start_time
                                    ? new Date(appt.slot_start_time).toLocaleString([], {
                                        month: 'short',
                                        day: 'numeric',
                                        hour: '2-digit',
                                        minute: '2-digit',
                                      })
                                    : 'Scheduled'}
                                </td>
                                <td className="py-3 pl-2 pr-4 align-top font-mono text-[11px] font-semibold">
                                  <span
                                    className={
                                      appt.appointment_status === 'CONFIRMED'
                                        ? 'text-teal-700'
                                        : appt.appointment_status === 'COMPLETED'
                                        ? 'text-emerald-700'
                                        : 'text-rose-600'
                                    }
                                  >
                                    {appt.appointment_status}
                                  </span>
                                </td>
                              </tr>
                            );
                          })
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Right 5 Cols: Appointment Detail & Status Confirmation Dialog */}
                <div className="lg:col-span-5 rounded-xl border border-slate-200 bg-white p-5 space-y-4">
                  <div className="border-b border-slate-200 pb-3">
                    <h3 className="font-display text-sm font-bold text-slate-900">
                      Appointment Detail & Permitted Actions
                    </h3>
                  </div>

                  {!selectedAppointment ? (
                    <p className="py-8 text-center text-xs text-slate-500">
                      Select an appointment from the table to inspect details.
                    </p>
                  ) : (
                    <div className="space-y-4 text-xs">
                      <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-1.5">
                        <div className="flex items-center justify-between font-mono">
                          <span className="font-bold text-slate-900">
                            Patient: {selectedAppointment.patient_reference}
                          </span>
                          <span className="font-semibold text-teal-700">
                            {selectedAppointment.appointment_status}
                          </span>
                        </div>
                        <p className="text-slate-700">
                          <strong>Reason:</strong> {selectedAppointment.reason_category}
                        </p>
                        <p className="font-mono text-[11px] tabular-nums text-slate-500">
                          Appointment ID: {selectedAppointment.id}
                        </p>
                        {selectedAppointment.follow_up_recommended && (
                          <p className="text-emerald-700 font-medium pt-1">
                            Follow-up Note: {selectedAppointment.follow_up_notes}
                          </p>
                        )}
                      </div>

                      {selectedAppointment.appointment_status === 'CONFIRMED' && (
                        <div className="space-y-3">
                          <div>
                            <label className="block font-medium text-slate-700">
                              Consultation Completion Note
                            </label>
                            <textarea
                              rows={2}
                              value={completionNotes}
                              onChange={(e) => setCompletionNotes(e.target.value)}
                              className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2.5 text-xs text-slate-900"
                            />
                          </div>

                          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                            <div>
                              <label className="block font-medium text-slate-700">
                                Follow-Up Date
                              </label>
                              <input
                                type="date"
                                value={followUpDate}
                                onChange={(e) => setFollowUpDate(e.target.value)}
                                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 font-mono text-xs text-slate-900"
                              />
                            </div>
                            <div>
                              <label className="block font-medium text-slate-700">
                                Follow-Up Instructions
                              </label>
                              <input
                                type="text"
                                value={followUpNotes}
                                onChange={(e) => setFollowUpNotes(e.target.value)}
                                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900"
                              />
                            </div>
                          </div>

                          {!pendingAction ? (
                            <div className="flex flex-wrap gap-2 pt-1">
                              <button
                                type="button"
                                onClick={() => setPendingAction('COMPLETE')}
                                className="rounded-lg bg-teal-600 px-3.5 py-2 font-semibold text-white hover:bg-teal-700"
                              >
                                Mark Visit Completed
                              </button>
                              <button
                                type="button"
                                onClick={() => setPendingAction('FOLLOW_UP')}
                                className="rounded-lg border border-teal-600 px-3.5 py-2 font-semibold text-teal-700 hover:bg-teal-50"
                              >
                                Record Follow-Up
                              </button>
                              <button
                                type="button"
                                onClick={() => setPendingAction('CANCEL')}
                                className="rounded-lg border border-rose-300 px-3 py-2 font-medium text-rose-700 hover:bg-rose-50"
                              >
                                Cancel Visit
                              </button>
                            </div>
                          ) : (
                            <div className="rounded-lg border border-amber-300 bg-amber-50 p-3.5 space-y-2.5">
                              <p className="font-semibold text-amber-900">
                                Confirm Status Update: {pendingAction} for{' '}
                                {selectedAppointment.patient_reference}?
                              </p>
                              <div className="flex items-center gap-2">
                                <button
                                  type="button"
                                  disabled={isSubmittingAction}
                                  onClick={() => void executeAppointmentAction()}
                                  className="rounded-lg bg-slate-900 px-3.5 py-1.5 font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
                                >
                                  {isSubmittingAction ? 'Saving...' : 'Confirm & Persist'}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setPendingAction(null)}
                                  className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-slate-700"
                                >
                                  Back
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}

          {/* =================================================================
              SUB-VIEW 3: SCHEDULE CALENDAR (`/doctor/calendar`)
          ================================================================= */}
          {currentRoute === '/doctor/calendar' && (
            <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-4">
              <div className="flex items-center justify-between border-b border-slate-200 pb-3">
                <div>
                  <h2 className="font-display text-base font-bold text-slate-900">
                    Daily & Weekly Schedule Blocks
                  </h2>
                  <p className="text-xs text-slate-500">
                    Combined view of booked patient consultations and open availability slots.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="space-y-2.5">
                  <h3 className="text-xs font-semibold text-slate-700">
                    Booked Appointments ({doctorAppointments.length})
                  </h3>
                  {doctorAppointments.map((appt) => (
                    <div
                      key={appt.id}
                      className="rounded-lg border border-slate-200 bg-slate-50 p-3.5 text-xs flex items-center justify-between"
                    >
                      <div>
                        <p className="font-semibold text-slate-900">
                          {appt.patient_reference} · {appt.reason_category}
                        </p>
                        <p className="font-mono text-[11px] tabular-nums text-slate-500">
                          {appt.slot_start_time
                            ? new Date(appt.slot_start_time).toLocaleString()
                            : 'Scheduled'}
                        </p>
                      </div>
                      <span className="font-mono text-[11px] font-semibold text-teal-700">
                        {appt.appointment_status}
                      </span>
                    </div>
                  ))}
                </div>

                <div className="space-y-2.5">
                  <h3 className="text-xs font-semibold text-slate-700">
                    Open Unbooked Slots ({doctorSlots.length})
                  </h3>
                  {doctorSlots.map((sl) => (
                    <div
                      key={sl.id}
                      className="rounded-lg border border-teal-200 bg-teal-50/40 p-3.5 text-xs flex items-center justify-between"
                    >
                      <span className="font-mono tabular-nums text-slate-800">
                        {new Date(sl.start_time).toLocaleString()} —{' '}
                        {new Date(sl.end_time).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                      <span className="font-mono text-[11px] font-semibold text-teal-700">
                        {sl.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* =================================================================
              SUB-VIEW 4: AVAILABILITY MANAGEMENT (`/doctor/availability`)
          ================================================================= */}
          {currentRoute === '/doctor/availability' && (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
              <div className="lg:col-span-5 rounded-xl border border-slate-200 bg-white p-6 space-y-4">
                <div className="border-b border-slate-200 pb-3">
                  <h2 className="font-display text-base font-bold text-slate-900">
                    Publish New Appointment Slot
                  </h2>
                  <p className="text-xs text-slate-500">
                    Persists a new <span className="font-mono">AVAILABLE</span> slot via{' '}
                    <span className="font-mono">POST /api/v1/doctors/&#123;id&#125;/slots</span>.
                  </p>
                </div>

                <form onSubmit={(e) => void handlePublishNewSlot(e)} className="space-y-3 text-xs">
                  <div>
                    <label className="block font-medium text-slate-700">Date</label>
                    <input
                      type="date"
                      required
                      value={slotDate}
                      onChange={(e) => setSlotDate(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-slate-900"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block font-medium text-slate-700">Start Time (UTC)</label>
                      <input
                        type="time"
                        required
                        value={slotStartTime}
                        onChange={(e) => setSlotStartTime(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-slate-900"
                      />
                    </div>
                    <div>
                      <label className="block font-medium text-slate-700">End Time (UTC)</label>
                      <input
                        type="time"
                        required
                        value={slotEndTime}
                        onChange={(e) => setSlotEndTime(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-slate-900"
                      />
                    </div>
                  </div>
                  <button
                    type="submit"
                    disabled={isCreatingSlot}
                    className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-teal-600 px-4 py-2.5 font-semibold text-white hover:bg-teal-700 disabled:opacity-50"
                  >
                    <Plus className="h-4 w-4" />
                    {isCreatingSlot ? 'Publishing Slot...' : 'Publish Available Slot'}
                  </button>
                </form>
              </div>

              <div className="lg:col-span-7 rounded-xl border border-slate-200 bg-white p-6 space-y-4">
                <h2 className="font-display text-base font-bold text-slate-900">
                  Active Open Slots for {activeDoctor?.display_name} ({doctorSlots.length})
                </h2>
                <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 max-h-96 overflow-y-auto pr-1">
                  {doctorSlots.map((slot) => (
                    <div
                      key={slot.id}
                      className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs flex items-center justify-between"
                    >
                      <div className="font-mono tabular-nums text-slate-800">
                        <div className="font-semibold">
                          {new Date(slot.start_time).toLocaleDateString()}
                        </div>
                        <div className="text-slate-500">
                          {new Date(slot.start_time).toLocaleTimeString([], {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}{' '}
                          –{' '}
                          {new Date(slot.end_time).toLocaleTimeString([], {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </div>
                      </div>
                      <span className="font-mono text-[11px] font-semibold text-teal-700">
                        {slot.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* =================================================================
              SUB-VIEW 5: DOCTOR PROFILE (`/doctor/profile`)
          ================================================================= */}
          {currentRoute === '/doctor/profile' && activeDoctor && (
            <div className="rounded-xl border border-slate-200 bg-white p-6 space-y-4 max-w-2xl">
              <h2 className="font-display text-lg font-bold text-slate-900">
                Physician Credential & Department Profile
              </h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 text-xs">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <span className="text-slate-500">Display Name</span>
                  <p className="mt-1 font-display text-sm font-bold text-slate-900">
                    {activeDoctor.display_name}
                  </p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <span className="text-slate-500">Clinical Specialty</span>
                  <p className="mt-1 font-semibold text-teal-700">{activeDoctor.specialty}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <span className="text-slate-500">Department</span>
                  <p className="mt-1 font-semibold text-slate-900">
                    {activeDoctor.department_name || activeDoctor.specialty}
                  </p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <span className="text-slate-500">Authenticated Staff Account</span>
                  <p className="mt-1 font-mono text-slate-900">
                    {staffProfile?.username} ({staffProfile?.role})
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </StaffAuthGate>
  );
};
