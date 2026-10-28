import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Building2,
  Calendar,
  CheckCircle2,
  Clock,
  FlaskConical,
  HeartHandshake,
  KeyRound,
  LifeBuoy,
  Lock,
  LogIn,
  MapPin,
  MessageSquare,
  PhoneCall,
  Search,
  ShieldAlert,
  ShieldCheck,
  Stethoscope,
  XCircle,
} from 'lucide-react';
import { usePlatform } from '../../app/PlatformContext';
import { ApiError, medivoiceApi } from '../../services/api';
import {
  AppointmentSlotRead,
  DoctorRead,
  InsuranceSearchResponse,
  LabVerificationResponse,
} from '../../types/api';
import { MediVoiceChatExperience } from '../chatbot/MediVoiceChatExperience';

const REASON_CATEGORIES = [
  'General Medicine & Fever Consultation',
  'Cardiology Evaluation & Checkup',
  'Neurology & Migraine Consultation',
  'Orthopedic Joint & Bone Consultation',
  'Pediatric Routine Checkup',
];

export const PatientWebsiteView: React.FC = () => {
  const {
    currentRoute,
    selectedEntityId,
    navigate,
    hospital,
    doctors,
    appointments,
    insuranceProviders,
    insuranceContact,
    supportTickets,
    activePatientRef,
    setActivePatientRef,
    launchMediVoiceWithPrompt,
    loginAsStaff,
    staffProfile,
    logoutStaff,
    isAuthenticating,
    authError,
    refreshOperationalData,
  } = usePlatform();

  // Doctor Discovery & Slot Booking State
  const [selectedDepartment, setSelectedDepartment] = useState<string>('ALL');
  const [doctorSearchQuery, setDoctorSearchQuery] = useState<string>('');
  const [selectedDoctor, setSelectedDoctor] = useState<DoctorRead | null>(null);
  const [availableSlots, setAvailableSlots] = useState<AppointmentSlotRead[]>([]);
  const [isLoadingSlots, setIsLoadingSlots] = useState<boolean>(false);
  const [selectedSlot, setSelectedSlot] = useState<AppointmentSlotRead | null>(null);
  const [reasonCategory, setReasonCategory] = useState<string>(REASON_CATEGORIES[0]);
  const [showConfirmModal, setShowConfirmModal] = useState<boolean>(false);
  const [isBooking, setIsBooking] = useState<boolean>(false);
  const [bookingFeedback, setBookingFeedback] = useState<{
    type: 'success' | 'error';
    message: string;
    appointmentId?: string;
  } | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  // Lab Status Verification State
  const [verificationCode, setVerificationCode] = useState<string>('');
  const [isVerifyingLab, setIsVerifyingLab] = useState<boolean>(false);
  const [labResult, setLabResult] = useState<LabVerificationResponse | null>(null);
  const [labError, setLabError] = useState<string | null>(null);

  // Insurance Search & Escalation Ticket State
  const [insQuery, setInsQuery] = useState<string>('');
  const [insServiceFilter, setInsServiceFilter] = useState<string>('');
  const [insCashlessOnly, setInsCashlessOnly] = useState<boolean>(false);
  const [insSearchRes, setInsSearchRes] = useState<InsuranceSearchResponse | null>(null);
  const [isSearchingIns, setIsSearchingIns] = useState<boolean>(false);

  const [ticketProvider, setTicketProvider] = useState<string>('');
  const [ticketPlan, setTicketPlan] = useState<string>('');
  const [ticketQuestion, setTicketQuestion] = useState<string>('');
  const [ticketContactPref, setTicketContactPref] = useState<string>(
    'In-Hospital Insurance Desk Counter 3'
  );
  const [isSubmittingTicket, setIsSubmittingTicket] = useState<boolean>(false);
  const [ticketFeedback, setTicketFeedback] = useState<{
    type: 'success' | 'error';
    message: string;
    ticketId?: string;
  } | null>(null);

  // Dedicated Staff Portal Sign-In State (/staff/login)
  const [loginUsername, setLoginUsername] = useState<string>('');
  const [loginPassword, setLoginPassword] = useState<string>('');

  // Select default doctor when doctors load
  useEffect(() => {
    if (!selectedDoctor && doctors.length > 0) {
      setSelectedDoctor(doctors[0]);
    }
  }, [doctors, selectedDoctor]);

  // Fetch available slots whenever selectedDoctor changes
  useEffect(() => {
    if (!selectedDoctor) {
      setAvailableSlots([]);
      return;
    }
    setIsLoadingSlots(true);
    setSelectedSlot(null);
    setShowConfirmModal(false);
    medivoiceApi
      .getDoctorSlots(selectedDoctor.id)
      .then((slots) => {
        setAvailableSlots(slots);
      })
      .catch(() => {
        setAvailableSlots([]);
      })
      .finally(() => {
        setIsLoadingSlots(false);
      });
  }, [selectedDoctor]);

  const filteredDoctors = useMemo(() => {
    return doctors.filter((doc) => {
      if (selectedDepartment !== 'ALL' && doc.department_name !== selectedDepartment) {
        return false;
      }
      if (doctorSearchQuery.trim()) {
        const q = doctorSearchQuery.trim().toLowerCase();
        const hay = `${doc.display_name} ${doc.specialty} ${doc.department_name || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [doctors, selectedDepartment, doctorSearchQuery]);

  const patientAppointments = useMemo(() => {
    return appointments.filter(
      (a) => a.patient_reference.toLowerCase() === activePatientRef.trim().toLowerCase()
    );
  }, [appointments, activePatientRef]);

  const handleConfirmBooking = async () => {
    if (!selectedDoctor || !selectedSlot || !activePatientRef.trim()) return;
    setIsBooking(true);
    setBookingFeedback(null);
    try {
      const created = await medivoiceApi.bookAppointment({
        patient_reference: activePatientRef.trim(),
        doctor_id: selectedDoctor.id,
        slot_id: selectedSlot.id,
        reason_category: reasonCategory,
      });
      setBookingFeedback({
        type: 'success',
        message: `Appointment confirmed with ${created.doctor_name || selectedDoctor.display_name} (Ref: ${created.id.slice(0, 8)}).`,
        appointmentId: created.id,
      });
      setShowConfirmModal(false);
      setSelectedSlot(null);
      const updatedSlots = await medivoiceApi.getDoctorSlots(selectedDoctor.id);
      setAvailableSlots(updatedSlots);
      await refreshOperationalData();
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : 'Slot booking failed. Please select another available slot.';
      setBookingFeedback({ type: 'error', message: msg });
    } finally {
      setIsBooking(false);
    }
  };

  const handleCancelAppointment = async (appointmentId: string) => {
    setCancellingId(appointmentId);
    setBookingFeedback(null);
    try {
      await medivoiceApi.cancelAppointment(
        appointmentId,
        'Cancelled by patient via Aarogya One Hospital website'
      );
      setBookingFeedback({
        type: 'success',
        message: 'Appointment cancelled and time slot released back to the doctor schedule.',
      });
      if (selectedDoctor) {
        const updatedSlots = await medivoiceApi.getDoctorSlots(selectedDoctor.id);
        setAvailableSlots(updatedSlots);
      }
      await refreshOperationalData();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Unable to cancel appointment.';
      setBookingFeedback({ type: 'error', message: msg });
    } finally {
      setCancellingId(null);
    }
  };

  const handleVerifyLabCode = async (codeOverride?: string) => {
    const rawCode = (codeOverride !== undefined ? codeOverride : verificationCode).trim();
    if (!/^\d{6}$/.test(rawCode)) {
      setLabError('Please enter a valid 6-digit numerical verification code (e.g., 482910).');
      setLabResult(null);
      return;
    }
    if (codeOverride !== undefined) {
      setVerificationCode(rawCode);
    }
    setIsVerifyingLab(true);
    setLabError(null);
    try {
      const res = await medivoiceApi.verifyLabOrderCode(rawCode);
      setLabResult(res);
    } catch (err) {
      setLabResult(null);
      const msg =
        err instanceof ApiError
          ? err.message
          : 'Unable to verify laboratory code at this moment.';
      setLabError(msg);
    } finally {
      setIsVerifyingLab(false);
    }
  };

  const handleSearchInsurance = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setIsSearchingIns(true);
    try {
      const res = await medivoiceApi.searchInsurance({
        q: insQuery.trim() || undefined,
        service: insServiceFilter.trim() || undefined,
        cashless: insCashlessOnly ? true : undefined,
      });
      setInsSearchRes(res);
    } catch {
      setInsSearchRes(null);
    } finally {
      setIsSearchingIns(false);
    }
  };

  const handleCreateSupportTicket = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticketQuestion.trim() || ticketQuestion.trim().length < 5) return;
    setIsSubmittingTicket(true);
    setTicketFeedback(null);
    try {
      const created = await medivoiceApi.createInsuranceSupportTicket({
        patient_reference: activePatientRef.trim() || 'PAT-2024-9182',
        provider_name: ticketProvider.trim() || null,
        plan_name: ticketPlan.trim() || null,
        question: ticketQuestion.trim(),
        contact_preference: ticketContactPref,
      });
      setTicketFeedback({
        type: 'success',
        message: `Support ticket ${created.ticket_id.slice(0, 8)} created and routed to ${created.assigned_department} (Status: ${created.status}).`,
        ticketId: created.ticket_id,
      });
      setTicketQuestion('');
      await refreshOperationalData();
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : 'Failed to submit insurance escalation ticket.';
      setTicketFeedback({ type: 'error', message: msg });
    } finally {
      setIsSubmittingTicket(false);
    }
  };

  const displayedProviders = insSearchRes ? insSearchRes.providers : insuranceProviders;

  // ============================================================================
  // Dedicated Full-Screen MediVoice AI Route (/medivoice)
  // ============================================================================
  if (currentRoute === '/medivoice') {
    return (
      <div className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8">
        <MediVoiceChatExperience mode="fullscreen" />
      </div>
    );
  }

  // ============================================================================
  // Separate Staff Portal Route (/staff/login)
  // ============================================================================
  if (currentRoute === '/staff/login' || currentRoute === '/login') {
    return (
      <div className="mx-auto max-w-xl px-4 py-14 sm:px-6 lg:px-8">
        <div className="mb-6 flex items-center justify-between">
          <button
            type="button"
            onClick={() => navigate('/')}
            className="inline-flex items-center gap-2 text-xs font-semibold text-[#94A3B8] hover:text-[#E5EDF7] whitespace-nowrap shrink-0"
          >
            <ArrowLeft className="h-4 w-4" />
            Return to Public Hospital Website
          </button>
          <span className="font-mono text-xs text-[#2DD4BF]">Staff Operations Portal</span>
        </div>

        <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-6 sm:p-8 space-y-6">
          <div className="flex items-start gap-3.5 border-b border-[#334155] pb-5">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-[#2DD4BF]/30 bg-[#0B1020] text-[#2DD4BF]">
              <Lock className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-semibold text-[#2DD4BF]">
                Aarogya One Hospital · Authorized Staff Access
              </p>
              <h1 className="mt-1 font-display text-2xl font-bold text-[#E5EDF7]">
                Staff Portal Sign-In
              </h1>
              <p className="mt-1 text-xs leading-relaxed text-[#94A3B8]">
                Sign in with your hospital staff credentials to access Doctor, Laboratory Operator,
                Maintenance Staff, or Administrator workspaces.
              </p>
            </div>
          </div>

          {staffProfile && (
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-[#2DD4BF]/40 bg-[#0B1020] p-4">
              <div>
                <p className="text-xs text-[#94A3B8]">Active Staff Session</p>
                <p className="font-display text-base font-bold text-[#E5EDF7]">
                  {staffProfile.display_name} ·{' '}
                  <span className="font-mono text-xs text-[#2DD4BF]">{staffProfile.role}</span>
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    if (staffProfile.role === 'DOCTOR') navigate('/doctor');
                    else if (staffProfile.role === 'LAB_OPERATOR') navigate('/lab');
                    else navigate('/maintenance');
                  }}
                  className="rounded-lg bg-[#2DD4BF] px-4 py-2 text-xs font-semibold text-[#0B1020] hover:bg-[#2DD4BF]/90 whitespace-nowrap"
                >
                  Continue to Workspace
                </button>
                <button
                  type="button"
                  onClick={logoutStaff}
                  className="rounded-lg border border-[#334155] bg-[#111B2E] px-3 py-2 text-xs text-[#94A3B8] hover:text-[#E5EDF7] whitespace-nowrap"
                >
                  Sign Out
                </button>
              </div>
            </div>
          )}

          {authError && (
            <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3.5 text-xs text-rose-200">
              {authError}
            </div>
          )}

          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (!loginUsername.trim()) return;
              const res = await loginAsStaff(loginUsername.trim(), loginPassword || undefined);
              if (res) {
                if (res.role === 'DOCTOR') navigate('/doctor');
                else if (res.role === 'LAB_OPERATOR') navigate('/lab');
                else navigate('/maintenance');
              }
            }}
            className="space-y-4"
          >
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2 font-semibold text-[#E5EDF7]">
                <KeyRound className="h-4 w-4 text-[#38BDF8]" />
                <span>Staff Credentials</span>
              </div>
              <span className="font-mono text-[11px] text-[#94A3B8]">
                Roles: Doctor · Lab Operator · Maintenance · Admin
              </span>
            </div>

            <div>
              <label
                htmlFor="portal-staff-username"
                className="block text-xs font-medium text-[#94A3B8]"
              >
                Staff Username
              </label>
              <input
                id="portal-staff-username"
                type="text"
                required
                value={loginUsername}
                onChange={(e) => setLoginUsername(e.target.value)}
                placeholder="Enter your staff username"
                className="mt-1.5 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3.5 py-2.5 font-mono text-xs text-[#E5EDF7] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none"
              />
            </div>

            <div>
              <label
                htmlFor="portal-staff-password"
                className="block text-xs font-medium text-[#94A3B8]"
              >
                Password
              </label>
              <input
                id="portal-staff-password"
                type="password"
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                placeholder="Enter your staff password"
                className="mt-1.5 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3.5 py-2.5 font-mono text-xs text-[#E5EDF7] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none"
              />
            </div>

            <button
              type="submit"
              disabled={isAuthenticating || !loginUsername.trim()}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#2DD4BF] px-4 py-3 text-xs font-semibold text-[#0B1020] transition-colors hover:bg-[#2DD4BF]/90 disabled:opacity-50"
            >
              <LogIn className="h-4 w-4" />
              {isAuthenticating ? 'Authenticating Staff Session...' : 'Sign In to Staff Workspace'}
            </button>

            <div className="flex items-start gap-2 pt-2 text-[11px] text-[#94A3B8]">
              <ShieldCheck className="h-4 w-4 shrink-0 text-[#2DD4BF]" />
              <span>
                Role-based authentication routes clinicians to the Doctor Workspace, laboratory
                personnel to the Lab Operator Workspace, and engineering or administrative staff to
                the Maintenance & Operations Workspace.
              </span>
            </div>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1440px] space-y-14 px-4 py-8 sm:px-6 lg:px-8">
      {/* ====================================================================
          PUBLIC PATIENT LANDING PAGE (`/`)
      ==================================================================== */}
      {currentRoute === '/' && (
        <>
          <section className="grid grid-cols-1 gap-8 lg:grid-cols-12 lg:items-stretch">
            {/* Left 6 Columns: Editorial Hospital & AI Proposition */}
            <div className="lg:col-span-6 flex flex-col justify-between rounded-xl border border-[#334155] bg-[#111B2E] p-7 sm:p-9">
              <div className="space-y-6">
                <div className="flex flex-wrap items-center gap-2 text-xs text-[#94A3B8]">
                  <span className="font-semibold text-[#2DD4BF]">
                    Aarogya One Hospital
                  </span>
                  <span aria-hidden="true">·</span>
                  <span>Multilingual Conversational Hospital Services</span>
                </div>

                <h1
                  className="font-display font-bold tracking-tight text-[#E5EDF7]"
                  style={{
                    fontSize: 'clamp(2.25rem, 3.6vw, 3.35rem)',
                    lineHeight: 1.1,
                    textWrap: 'balance',
                  }}
                >
                  Healthcare conversations that move things forward.
                </h1>

                <p className="max-w-xl text-base leading-relaxed text-[#94A3B8]">
                  Discover doctors, manage appointments, check laboratory status, and get help with
                  insurance through one conversational assistant connected to controlled hospital
                  workflows.
                </p>

                {/* Primary & Secondary CTAs */}
                <div className="flex flex-wrap items-center gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => launchMediVoiceWithPrompt()}
                    className="inline-flex items-center gap-2 rounded-lg bg-[#2DD4BF] px-5 py-3 text-sm font-semibold text-[#0B1020] transition-colors hover:bg-[#2DD4BF]/90 whitespace-nowrap shrink-0"
                  >
                    <MessageSquare className="h-4 w-4" />
                    Talk to MediVoice
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate('/doctors')}
                    className="inline-flex items-center gap-2 rounded-lg border border-[#334155] bg-[#0B1020] px-5 py-3 text-sm font-semibold text-[#E5EDF7] transition-colors hover:border-[#38BDF8] whitespace-nowrap shrink-0"
                  >
                    Find Doctors
                    <ArrowRight className="h-4 w-4 text-[#38BDF8]" />
                  </button>
                </div>
              </div>

              {/* Hospital Trust & Safety Boundaries */}
              <div className="mt-8 border-t border-[#334155] pt-6 grid grid-cols-1 gap-4 sm:grid-cols-3 text-xs">
                <div>
                  <p className="font-mono text-lg font-bold tabular-nums text-[#E5EDF7]">
                    {doctors.length} Specialists
                  </p>
                  <p className="mt-0.5 text-[#94A3B8]">
                    Across 5 clinical departments with real-time slot locks
                  </p>
                </div>
                <div>
                  <p className="font-mono text-lg font-bold tabular-nums text-[#2DD4BF]">
                    5 Languages
                  </p>
                  <p className="mt-0.5 text-[#94A3B8]">
                    English, Telugu, Hindi, Tamil & Kannada continuity
                  </p>
                </div>
                <div>
                  <p className="font-mono text-lg font-bold tabular-nums text-[#38BDF8]">
                    6-Digit Lab Code
                  </p>
                  <p className="mt-0.5 text-[#94A3B8]">
                    Verified sample stage tracking without diagnostic fabrication
                  </p>
                </div>
              </div>
            </div>

            {/* Right 6 Columns: Live Interactive MediVoice AI Assistant Panel */}
            <div className="lg:col-span-6 flex flex-col">
              <MediVoiceChatExperience mode="embedded" />
            </div>
          </section>

          {/* 4-Service Entry Points Strip */}
          <section className="space-y-4">
            <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-end">
              <div>
                <p className="text-xs font-semibold text-[#2DD4BF]">
                  One Conversational Entry Point · Four Controlled Patient Services
                </p>
                <h2 className="mt-1 font-display text-2xl font-bold text-[#E5EDF7]">
                  Routine Hospital Services Connected End-to-End
                </h2>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="flex flex-col justify-between rounded-xl border border-[#334155] bg-[#111B2E] p-6">
                <div>
                  <div className="flex items-center justify-between text-xs text-[#94A3B8]">
                    <span>01. Doctor Discovery</span>
                    <Stethoscope className="h-4 w-4 text-[#2DD4BF]" />
                  </div>
                  <h3 className="mt-3 font-display text-lg font-bold text-[#E5EDF7]">
                    Find Specialists by Symptom or Wing
                  </h3>
                  <p className="mt-2 text-xs leading-relaxed text-[#94A3B8]">
                    Explore Cardiology, Neurology, Orthopedics, Pediatrics, and General Medicine
                    physicians with live unbooked time slots.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => navigate('/doctors')}
                  className="mt-5 inline-flex items-center gap-1.5 text-xs font-semibold text-[#2DD4BF] hover:underline whitespace-nowrap"
                >
                  Browse Doctor Directory <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>

              <div className="flex flex-col justify-between rounded-xl border border-[#334155] bg-[#111B2E] p-6">
                <div>
                  <div className="flex items-center justify-between text-xs text-[#94A3B8]">
                    <span>02. Appointment Booking</span>
                    <Calendar className="h-4 w-4 text-[#38BDF8]" />
                  </div>
                  <h3 className="mt-3 font-display text-lg font-bold text-[#E5EDF7]">
                    Two-Step Explicit Confirmation
                  </h3>
                  <p className="mt-2 text-xs leading-relaxed text-[#94A3B8]">
                    Every appointment requires explicit patient confirmation before locking a slot
                    in the hospital schedule.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => navigate('/appointments')}
                  className="mt-5 inline-flex items-center gap-1.5 text-xs font-semibold text-[#38BDF8] hover:underline whitespace-nowrap"
                >
                  Manage Appointments <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>

              <div className="flex flex-col justify-between rounded-xl border border-[#334155] bg-[#111B2E] p-6">
                <div>
                  <div className="flex items-center justify-between text-xs text-[#94A3B8]">
                    <span>03. Lab Status Tracking</span>
                    <FlaskConical className="h-4 w-4 text-[#2DD4BF]" />
                  </div>
                  <h3 className="mt-3 font-display text-lg font-bold text-[#E5EDF7]">
                    6-Digit Code Verification
                  </h3>
                  <p className="mt-2 text-xs leading-relaxed text-[#94A3B8]">
                    Verify whether your diagnostic sample is Registered, Sample Collected,
                    Processing, or Completed Ready.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => navigate('/lab-status')}
                  className="mt-5 inline-flex items-center gap-1.5 text-xs font-semibold text-[#2DD4BF] hover:underline whitespace-nowrap"
                >
                  Verify Lab Code <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>

              <div className="flex flex-col justify-between rounded-xl border border-[#334155] bg-[#111B2E] p-6">
                <div>
                  <div className="flex items-center justify-between text-xs text-[#94A3B8]">
                    <span>04. Insurance Assistance</span>
                    <HeartHandshake className="h-4 w-4 text-[#38BDF8]" />
                  </div>
                  <h3 className="mt-3 font-display text-lg font-bold text-[#E5EDF7]">
                    Document-Grounded Plan Guidance
                  </h3>
                  <p className="mt-2 text-xs leading-relaxed text-[#94A3B8]">
                    Check cashless and reimbursement plans or escalate unanswered policy questions
                    to the human TPA helpdesk.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => navigate('/insurance')}
                  className="mt-5 inline-flex items-center gap-1.5 text-xs font-semibold text-[#38BDF8] hover:underline whitespace-nowrap"
                >
                  Search Insurance Plans <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </section>

          {/* How It Works (Three-Step Journey) & Hospital Campus Info */}
          <section className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            <div className="lg:col-span-7 rounded-xl border border-[#334155] bg-[#111B2E] p-7 space-y-6">
              <div>
                <p className="text-xs font-semibold text-[#2DD4BF]">How MediVoice AI Works</p>
                <h2 className="mt-1 font-display text-xl font-bold text-[#E5EDF7]">
                  Controlled Architecture from Natural Question to Confirmed Action
                </h2>
              </div>

              <div className="space-y-5">
                <div className="border-b border-[#334155]/70 pb-4">
                  <p className="text-xs font-semibold text-[#38BDF8]">01. Ask Naturally</p>
                  <p className="mt-1 text-sm text-[#E5EDF7]">
                    Speak or type in English, Telugu, Hindi, Tamil, or Kannada. MediVoice AI
                    preserves your language and conversation context across follow-up turns.
                  </p>
                </div>
                <div className="border-b border-[#334155]/70 pb-4">
                  <p className="text-xs font-semibold text-[#2DD4BF]">
                    02. Connect to Approved Hospital Workflows
                  </p>
                  <p className="mt-1 text-sm text-[#E5EDF7]">
                    Requests execute strictly through validated backend services for doctor
                    discovery, real-time slot checks, 6-digit laboratory verification, and
                    document-grounded insurance search.
                  </p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-[#38BDF8]">
                    03. Receive Verified Status or Human Support Escalation
                  </p>
                  <p className="mt-1 text-sm text-[#E5EDF7]">
                    Appointments require explicit patient confirmation. Missing insurance policy
                    details are never invented—they escalate directly to our human Insurance &amp;
                    TPA Helpdesk.
                  </p>
                </div>
              </div>
            </div>

            {/* Aarogya One Hospital Information Panel */}
            <div className="lg:col-span-5 rounded-xl border border-[#334155] bg-[#111B2E] p-7 flex flex-col justify-between space-y-6">
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-xs text-[#2DD4BF]">
                  <Building2 className="h-4 w-4" />
                  <span>About Our Hospital</span>
                </div>
                <h2 className="font-display text-xl font-bold text-[#E5EDF7]">
                  {hospital?.name || 'Aarogya One Hospital'}
                </h2>
                <p className="text-xs leading-relaxed text-[#94A3B8]">
                  {hospital?.description ||
                    'A multi-specialty tertiary care hospital equipped with integrated digital scheduling, clinical pathology tracking, and TPA insurance coordination.'}
                </p>

                <div className="space-y-2 pt-2 text-xs text-[#E5EDF7]">
                  <div className="flex items-center gap-2 text-[#94A3B8]">
                    <MapPin className="h-3.5 w-3.5 text-[#38BDF8]" />
                    <span>
                      {hospital?.address ||
                        'Health City Knowledge Park, Raidurg, Hyderabad 500081'}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-[#94A3B8]">
                    <PhoneCall className="h-3.5 w-3.5 text-[#2DD4BF]" />
                    <span>24/7 Reception & Insurance Desk: 1800-100-4200 (Ext. 400)</span>
                  </div>
                </div>

                {/* Clinical Wings List */}
                <div className="pt-2">
                  <p className="text-xs font-semibold text-[#94A3B8]">Active Clinical Wings</p>
                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-[#E5EDF7]">
                    {(hospital?.departments || []).map((dept, idx) => (
                      <React.Fragment key={dept.id}>
                        {idx > 0 && <span aria-hidden="true" className="text-[#334155]">·</span>}
                        <span>{dept.name}</span>
                      </React.Fragment>
                    ))}
                  </div>
                </div>
              </div>

              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs text-amber-200">
                <div className="flex items-center gap-2 font-semibold text-amber-300">
                  <ShieldAlert className="h-4 w-4 shrink-0" />
                  <span>Clinical Safety Boundary</span>
                </div>
                <p className="mt-1 text-amber-100/85">
                  MediVoice AI handles routine administrative workflows only. Severe symptoms (such
                  as acute chest pain or breathing difficulty) trigger immediate emergency care
                  redirection without routine booking distraction.
                </p>
              </div>
            </div>
          </section>

          {/* Specialist Directory Preview on Home Page */}
          <section className="space-y-4">
            <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-end">
              <div>
                <p className="text-xs font-semibold text-[#2DD4BF]">
                  Hospital Specialist Roster
                </p>
                <h2 className="mt-1 font-display text-2xl font-bold text-[#E5EDF7]">
                  Consult Experienced Physicians Across Clinical Departments
                </h2>
              </div>
              <button
                type="button"
                onClick={() => navigate('/doctors')}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#38BDF8] hover:underline whitespace-nowrap"
              >
                View Full Directory &amp; Open Slots <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {doctors.slice(0, 6).map((doc) => (
                <div
                  key={doc.id}
                  className="flex flex-col justify-between rounded-xl border border-[#334155] bg-[#111B2E] p-5"
                >
                  <div>
                    <div className="flex items-center gap-2 text-xs text-[#94A3B8]">
                      <span className="font-medium text-[#2DD4BF]">
                        {doc.department_name || doc.specialty}
                      </span>
                      <span aria-hidden="true">·</span>
                      <span>Aarogya One Hospital</span>
                    </div>
                    <h3 className="mt-1.5 font-display text-base font-bold text-[#E5EDF7]">
                      {doc.display_name}
                    </h3>
                    <p className="mt-0.5 text-xs text-[#94A3B8]">{doc.specialty}</p>
                  </div>

                  <div className="mt-4 flex items-center justify-between border-t border-[#334155]/70 pt-3">
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedDoctor(doc);
                        navigate('/doctors');
                      }}
                      className="text-xs font-semibold text-[#2DD4BF] hover:underline whitespace-nowrap"
                    >
                      Inspect Available Slots →
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        launchMediVoiceWithPrompt(
                          `Show me available appointment slots for ${doc.display_name}`
                        )
                      }
                      className="text-xs text-[#38BDF8] hover:underline whitespace-nowrap"
                    >
                      Ask MediVoice
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </>
      )}

      {/* ====================================================================
          DOCTOR DISCOVERY & APPOINTMENT BOOKING (`/doctors`, `/appointments`)
      ==================================================================== */}
      {(currentRoute === '/doctors' || currentRoute === '/appointments') && (
        <section className="space-y-6">
          <div className="flex flex-col justify-between gap-4 border-b border-[#334155] pb-4 sm:flex-row sm:items-end">
            <div>
              <p className="text-xs font-semibold text-[#2DD4BF]">
                Specialist Directory &amp; Real-Time Slot Reservation
              </p>
              <h2 className="mt-1 font-display text-2xl font-bold text-[#E5EDF7]">
                {currentRoute === '/appointments'
                  ? 'Book & Manage Patient Appointments'
                  : 'Explore Hospital Specialists & Open Slots'}
              </h2>
            </div>

            {/* Department & Search Filters */}
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-2.5 h-3.5 w-3.5 text-[#94A3B8]" />
                <input
                  type="text"
                  value={doctorSearchQuery}
                  onChange={(e) => setDoctorSearchQuery(e.target.value)}
                  placeholder="Search doctor or specialty..."
                  className="rounded-lg border border-[#334155] bg-[#111B2E] pl-8 pr-3 py-1.5 text-xs text-[#E5EDF7] placeholder-[#94A3B8]/60 focus:border-[#2DD4BF] focus:outline-none"
                />
              </div>

              <select
                value={selectedDepartment}
                onChange={(e) => setSelectedDepartment(e.target.value)}
                aria-label="Filter doctors by department"
                className="rounded-lg border border-[#334155] bg-[#111B2E] px-3 py-1.5 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
              >
                <option value="ALL">All Departments</option>
                {(hospital?.departments || []).map((d) => (
                  <option key={d.id} value={d.name}>
                    {d.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {bookingFeedback && (
            <div
              className={`flex items-center justify-between rounded-xl border p-4 text-xs ${
                bookingFeedback.type === 'success'
                  ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
                  : 'border-rose-500/40 bg-rose-500/10 text-rose-200'
              }`}
            >
              <div className="flex items-center gap-2">
                {bookingFeedback.type === 'success' ? (
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
                ) : (
                  <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
                )}
                <span>{bookingFeedback.message}</span>
              </div>
              <button
                type="button"
                onClick={() => setBookingFeedback(null)}
                className="underline opacity-80 hover:opacity-100"
              >
                Dismiss
              </button>
            </div>
          )}

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            {/* Specialist Directory Cards (7 Cols) */}
            <div className="lg:col-span-7 grid grid-cols-1 gap-4 sm:grid-cols-2">
              {filteredDoctors.length === 0 ? (
                <div className="sm:col-span-2 rounded-xl border border-[#334155] bg-[#111B2E] p-8 text-center text-xs text-[#94A3B8]">
                  No active specialists match your filter. Try selecting &ldquo;All Departments&rdquo;.
                </div>
              ) : (
                filteredDoctors.map((doc) => {
                  const isSelected = selectedDoctor?.id === doc.id;
                  return (
                    <div
                      key={doc.id}
                      onClick={() => setSelectedDoctor(doc)}
                      className={`cursor-pointer rounded-xl border p-5 transition-colors flex flex-col justify-between ${
                        isSelected
                          ? 'border-[#2DD4BF] bg-[#111B2E]'
                          : 'border-[#334155] bg-[#111B2E]/70 hover:border-[#38BDF8]'
                      }`}
                    >
                      <div>
                        <div className="flex items-center gap-2 text-xs text-[#94A3B8]">
                          <span className="text-[#2DD4BF] font-medium">
                            {doc.department_name || doc.specialty}
                          </span>
                          <span aria-hidden="true">·</span>
                          <span>Active Roster</span>
                        </div>
                        <h3 className="mt-1.5 font-display text-base font-bold text-[#E5EDF7]">
                          {doc.display_name}
                        </h3>
                        <p className="mt-0.5 text-xs text-[#94A3B8]">{doc.specialty}</p>
                      </div>

                      <div className="mt-4 flex items-center justify-between border-t border-[#334155]/70 pt-3">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedDoctor(doc);
                          }}
                          className="text-xs font-semibold text-[#2DD4BF] hover:underline whitespace-nowrap"
                        >
                          {isSelected ? 'Viewing Open Slots →' : 'Inspect Available Slots'}
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            launchMediVoiceWithPrompt(
                              `Show me available appointment slots for ${doc.display_name}`
                            );
                          }}
                          className="text-xs text-[#38BDF8] hover:underline whitespace-nowrap"
                        >
                          Ask MediVoice
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Right 5 Cols: Selected Doctor Slot Selector & Explicit Confirmation */}
            <div className="lg:col-span-5 rounded-xl border border-[#334155] bg-[#111B2E] p-6 space-y-5">
              {!selectedDoctor ? (
                <p className="py-10 text-center text-xs text-[#94A3B8]">
                  Select a specialist to view open appointment slots.
                </p>
              ) : (
                <>
                  <div className="border-b border-[#334155] pb-4">
                    <div className="flex items-center gap-2 text-xs text-[#94A3B8]">
                      <span className="text-[#2DD4BF] font-medium">
                        {selectedDoctor.department_name || selectedDoctor.specialty}
                      </span>
                      <span aria-hidden="true">·</span>
                      <span>Available Consultation Slots</span>
                    </div>
                    <h3 className="mt-1 font-display text-lg font-bold text-[#E5EDF7]">
                      {selectedDoctor.display_name}
                    </h3>
                    <p className="text-xs text-[#94A3B8]">{selectedDoctor.specialty}</p>
                  </div>

                  <div>
                    <label
                      htmlFor="booking-patient-reference"
                      className="block text-xs font-medium text-[#94A3B8]"
                    >
                      Patient Registration / Hospital ID
                    </label>
                    <input
                      id="booking-patient-reference"
                      type="text"
                      value={activePatientRef}
                      onChange={(e) => setActivePatientRef(e.target.value)}
                      placeholder="e.g. PAT-2024-9182"
                      className="mt-1.5 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 font-mono text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-[#94A3B8]">
                      Reason for Consultation
                    </label>
                    <select
                      value={reasonCategory}
                      onChange={(e) => setReasonCategory(e.target.value)}
                      className="mt-1.5 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                    >
                      {REASON_CATEGORIES.map((rc) => (
                        <option key={rc} value={rc}>
                          {rc}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-[#94A3B8]">
                        Available Slots ({availableSlots.length})
                      </span>
                    </div>

                    {isLoadingSlots ? (
                      <p className="py-6 text-center text-xs text-[#94A3B8]">
                        Loading open slots from hospital schedule...
                      </p>
                    ) : availableSlots.length === 0 ? (
                      <div className="mt-2 rounded-lg border border-[#334155] bg-[#0B1020] p-4 text-xs text-[#94A3B8]">
                        No unbooked slots currently open for {selectedDoctor.display_name}. Select
                        another specialist or ask MediVoice AI for alternative doctors.
                      </div>
                    ) : (
                      <div className="mt-2 grid grid-cols-2 gap-2 max-h-52 overflow-y-auto pr-1">
                        {availableSlots.map((slot) => {
                          const isChosen = selectedSlot?.id === slot.id;
                          return (
                            <button
                              key={slot.id}
                              type="button"
                              onClick={() => {
                                setSelectedSlot(slot);
                                setShowConfirmModal(false);
                              }}
                              className={`rounded-lg border p-2.5 text-left font-mono text-xs tabular-nums transition-colors ${
                                isChosen
                                  ? 'border-[#2DD4BF] bg-[#2DD4BF]/15 text-[#2DD4BF]'
                                  : 'border-[#334155] bg-[#0B1020] text-[#E5EDF7] hover:border-[#38BDF8]'
                              }`}
                            >
                              <div className="font-semibold">
                                {new Date(slot.start_time).toLocaleDateString([], {
                                  month: 'short',
                                  day: 'numeric',
                                })}
                              </div>
                              <div className="mt-0.5 text-[11px] text-[#94A3B8]">
                                {new Date(slot.start_time).toLocaleTimeString([], {
                                  hour: '2-digit',
                                  minute: '2-digit',
                                })}
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  {/* Step 1 -> Step 2 Explicit Patient Confirmation */}
                  {selectedSlot && !showConfirmModal && (
                    <button
                      type="button"
                      onClick={() => setShowConfirmModal(true)}
                      className="w-full rounded-lg bg-[#2DD4BF] px-4 py-2.5 text-xs font-semibold text-[#0B1020] hover:bg-[#2DD4BF]/90"
                    >
                      Review &amp; Confirm Slot Selection
                    </button>
                  )}

                  {selectedSlot && showConfirmModal && (
                    <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 space-y-3 text-xs">
                      <div className="flex items-center gap-2 font-semibold text-amber-300">
                        <ShieldCheck className="h-4 w-4 shrink-0" />
                        <span>Explicit Patient Booking Confirmation</span>
                      </div>
                      <div className="space-y-1 text-[#E5EDF7]">
                        <p>
                          <strong>Patient Registration ID:</strong>{' '}
                          <span className="font-mono">{activePatientRef}</span>
                        </p>
                        <p>
                          <strong>Doctor:</strong> {selectedDoctor.display_name} (
                          {selectedDoctor.specialty})
                        </p>
                        <p>
                          <strong>Date &amp; Time:</strong>{' '}
                          <span className="font-mono tabular-nums">
                            {new Date(selectedSlot.start_time).toLocaleString()}
                          </span>
                        </p>
                        <p>
                          <strong>Reason:</strong> {reasonCategory}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 pt-1">
                        <button
                          type="button"
                          disabled={isBooking}
                          onClick={() => void handleConfirmBooking()}
                          className="flex-1 rounded-lg bg-[#2DD4BF] px-3 py-2 font-semibold text-[#0B1020] hover:bg-[#2DD4BF]/90 disabled:opacity-50"
                        >
                          {isBooking ? 'Booking...' : 'Confirm & Lock Appointment'}
                        </button>
                        <button
                          type="button"
                          onClick={() => setShowConfirmModal(false)}
                          className="rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-[#94A3B8] hover:text-[#E5EDF7]"
                        >
                          Back
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Patient's Existing Appointments List (shown on /appointments) */}
          {currentRoute === '/appointments' && (
            <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-6">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#334155] pb-3.5">
                <div>
                  <h3 className="font-display text-base font-bold text-[#E5EDF7]">
                    Your Scheduled Appointments ({patientAppointments.length})
                  </h3>
                  <p className="text-xs text-[#94A3B8]">
                    Showing appointments for registration ID{' '}
                    <span className="font-mono text-[#2DD4BF]">{activePatientRef}</span>.
                  </p>
                </div>
                {selectedEntityId && (
                  <span className="font-mono text-xs text-[#38BDF8]">
                    Reference: {selectedEntityId.slice(0, 8)}
                  </span>
                )}
              </div>

              {patientAppointments.length === 0 ? (
                <p className="py-6 text-center text-xs text-[#94A3B8]">
                  No appointments recorded yet for {activePatientRef}.
                </p>
              ) : (
                <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {patientAppointments.map((appt) => (
                    <div
                      key={appt.id}
                      className="flex flex-col justify-between rounded-lg border border-[#334155] bg-[#0B1020] p-4 text-xs"
                    >
                      <div>
                        <div className="flex items-center justify-between text-[#94A3B8]">
                          <span className="font-mono">Ref: {appt.id.slice(0, 8)}</span>
                          <span
                            className={`font-mono font-semibold ${
                              appt.appointment_status === 'CONFIRMED'
                                ? 'text-[#2DD4BF]'
                                : appt.appointment_status === 'COMPLETED'
                                ? 'text-emerald-400'
                                : 'text-rose-400'
                            }`}
                          >
                            {appt.appointment_status}
                          </span>
                        </div>
                        <p className="mt-2 font-display text-sm font-bold text-[#E5EDF7]">
                          {appt.doctor_name || 'Hospital Specialist'}
                        </p>
                        <p className="text-[#94A3B8]">
                          {appt.doctor_specialty} · {appt.reason_category}
                        </p>
                        {appt.slot_start_time && (
                          <p className="mt-1.5 font-mono text-[11px] tabular-nums text-[#38BDF8]">
                            <Clock className="inline h-3 w-3 mr-1" />
                            {new Date(appt.slot_start_time).toLocaleString()}
                          </p>
                        )}
                        {appt.follow_up_recommended && (
                          <p className="mt-2 text-emerald-300">
                            Follow-up Note: {appt.follow_up_notes || 'Recommended by clinician'}
                          </p>
                        )}
                      </div>

                      {appt.appointment_status === 'CONFIRMED' && (
                        <div className="mt-3 border-t border-[#334155]/70 pt-2.5 flex justify-end">
                          <button
                            type="button"
                            disabled={cancellingId === appt.id}
                            onClick={() => void handleCancelAppointment(appt.id)}
                            className="inline-flex items-center gap-1 text-rose-400 hover:underline disabled:opacity-50"
                          >
                            <XCircle className="h-3.5 w-3.5" />
                            {cancellingId === appt.id ? 'Cancelling...' : 'Cancel Appointment'}
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* ====================================================================
          LAB REPORT 6-DIGIT VERIFICATION (`/lab-status`)
      ==================================================================== */}
      {currentRoute === '/lab-status' && (
        <section className="rounded-xl border border-[#334155] bg-[#111B2E] p-6 sm:p-8 space-y-6">
          <div className="flex flex-col justify-between gap-2 border-b border-[#334155] pb-4 sm:flex-row sm:items-end">
            <div>
              <p className="text-xs font-semibold text-[#2DD4BF]">
                Controlled Diagnostic Status Verification
              </p>
              <h2 className="mt-1 font-display text-2xl font-bold text-[#E5EDF7]">
                Check Laboratory Report Status with Your 6-Digit Code
              </h2>
            </div>
            <button
              type="button"
              onClick={() =>
                launchMediVoiceWithPrompt('I want to check my lab report status with my 6-digit code')
              }
              className="text-xs font-semibold text-[#38BDF8] hover:underline whitespace-nowrap"
            >
              Verify via MediVoice AI →
            </button>
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            {/* Left: Verification Form & Result */}
            <div className="lg:col-span-7 space-y-4">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void handleVerifyLabCode();
                }}
                className="flex flex-col gap-3 sm:flex-row"
              >
                <input
                  type="text"
                  maxLength={6}
                  value={verificationCode}
                  onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, ''))}
                  placeholder="Enter 6-digit verification code printed on your lab receipt"
                  aria-label="6-digit laboratory verification code"
                  className="h-11 flex-1 rounded-lg border border-[#334155] bg-[#0B1020] px-4 font-mono text-sm tracking-widest text-[#E5EDF7] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none tabular-nums"
                />
                <button
                  type="submit"
                  disabled={isVerifyingLab}
                  className="h-11 rounded-lg bg-[#2DD4BF] px-6 text-xs font-semibold text-[#0B1020] hover:bg-[#2DD4BF]/90 disabled:opacity-50 whitespace-nowrap"
                >
                  {isVerifyingLab ? 'Verifying Code...' : 'Verify Lab Status'}
                </button>
              </form>

              {labError && (
                <div className="flex items-start gap-2.5 rounded-lg border border-rose-500/40 bg-rose-500/10 p-4 text-xs text-rose-200">
                  <AlertCircle className="h-4 w-4 shrink-0 text-rose-400 mt-0.5" />
                  <span>{labError}</span>
                </div>
              )}

              {labResult && (
                <div className="rounded-xl border border-[#2DD4BF]/40 bg-[#0B1020] p-5 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-display text-base font-bold text-[#E5EDF7]">
                      {labResult.test_name}
                    </span>
                    <span className="font-mono text-xs font-semibold text-[#2DD4BF]">
                      Stage: {labResult.lab_status}
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed text-[#E5EDF7]">
                    {labResult.status_explanation}
                  </p>
                  <p className="text-xs text-[#38BDF8]">
                    <strong>Next Step:</strong> {labResult.next_step}
                  </p>
                  <p className="border-t border-[#334155] pt-2 text-[11px] text-[#94A3B8]">
                    {labResult.disclaimer}
                  </p>
                </div>
              )}
            </div>

            {/* Right: Patient Privacy & Stage Guide */}
            <div className="lg:col-span-5 rounded-xl border border-[#334155] bg-[#0B1020] p-5 space-y-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-[#E5EDF7]">
                <ShieldCheck className="h-4 w-4 text-[#2DD4BF]" />
                <span>How 6-Digit Lab Verification Protects Your Privacy</span>
              </div>
              <p className="text-xs leading-relaxed text-[#94A3B8]">
                Your 6-digit verification code is printed on your Aarogya One Hospital diagnostic
                collection receipt. Entering it displays only your operational processing stage—never
                raw clinical values or diagnostic interpretations on a public screen.
              </p>
              <div className="border-t border-[#334155] pt-3 space-y-1.5 text-xs text-[#94A3B8]">
                <p className="font-semibold text-[#E5EDF7]">Standard Processing Stages:</p>
                <p>
                  <span className="font-mono text-[#2DD4BF]">REGISTERED</span> — Order logged at
                  diagnostic reception
                </p>
                <p>
                  <span className="font-mono text-[#38BDF8]">SAMPLE_COLLECTED</span> — Specimen
                  received by phlebotomy team
                </p>
                <p>
                  <span className="font-mono text-[#2DD4BF]">PROCESSING</span> — Analysis underway
                  in central pathology lab
                </p>
                <p>
                  <span className="font-mono text-emerald-400">COMPLETED</span> — Report verified
                  and ready for collection
                </p>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* ====================================================================
          INSURANCE GUIDANCE & HUMAN-SUPPORT TICKET ESCALATION (`/insurance`, `/support`)
      ==================================================================== */}
      {(currentRoute === '/insurance' || currentRoute === '/support') && (
        <section className="rounded-xl border border-[#334155] bg-[#111B2E] p-6 sm:p-8 space-y-6">
          <div className="flex flex-col justify-between gap-2 border-b border-[#334155] pb-4 sm:flex-row sm:items-end">
            <div>
              <p className="text-xs font-semibold text-[#38BDF8]">
                Document-Grounded Insurance Directory &amp; TPA Escalation
              </p>
              <h2 className="mt-1 font-display text-2xl font-bold text-[#E5EDF7]">
                Hospital Insurance Plans &amp; Human-Support Escalation
              </h2>
            </div>
            {insuranceContact && (
              <span className="text-xs text-[#94A3B8]">
                Helpdesk: <strong className="text-[#E5EDF7]">{insuranceContact.phone}</strong>
              </span>
            )}
          </div>

          {/* Non-Guarantee Coverage Disclaimer */}
          <div className="rounded-lg border border-[#334155] bg-[#0B1020] p-3.5 text-xs text-[#94A3B8]">
            <strong className="text-[#E5EDF7]">Coverage Disclaimer:</strong> Listed insurance plan
            information is for general guidance only and is not a guarantee of individual
            eligibility or claim approval. Unlisted policy questions should be escalated to the
            human Insurance &amp; TPA Helpdesk below.
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            {/* Left 7 Cols: Search & Active Insurance Plans */}
            <div className="lg:col-span-7 space-y-4">
              <form
                onSubmit={(e) => void handleSearchInsurance(e)}
                className="flex flex-wrap items-center gap-2"
              >
                <input
                  type="text"
                  value={insQuery}
                  onChange={(e) => setInsQuery(e.target.value)}
                  placeholder="Search provider or plan (e.g. Aarogya Shield, Bharat Care)..."
                  className="h-10 flex-1 min-w-[200px] rounded-lg border border-[#334155] bg-[#0B1020] px-3.5 text-xs text-[#E5EDF7] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none"
                />
                <input
                  type="text"
                  value={insServiceFilter}
                  onChange={(e) => setInsServiceFilter(e.target.value)}
                  placeholder="Service (e.g. Cardiology, OPD)"
                  className="h-10 w-44 rounded-lg border border-[#334155] bg-[#0B1020] px-3 text-xs text-[#E5EDF7] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none"
                />
                <label className="flex items-center gap-1.5 text-xs text-[#E5EDF7] cursor-pointer px-2">
                  <input
                    type="checkbox"
                    checked={insCashlessOnly}
                    onChange={(e) => setInsCashlessOnly(e.target.checked)}
                    className="rounded border-[#334155]"
                  />
                  <span>Cashless Only</span>
                </label>
                <button
                  type="submit"
                  disabled={isSearchingIns}
                  className="h-10 rounded-lg bg-[#2DD4BF] px-4 text-xs font-semibold text-[#0B1020] hover:bg-[#2DD4BF]/90 whitespace-nowrap"
                >
                  {isSearchingIns ? 'Searching...' : 'Search Plans'}
                </button>
              </form>

              <div className="space-y-3 max-h-[420px] overflow-y-auto pr-1">
                {displayedProviders.length === 0 ? (
                  <div className="rounded-lg border border-[#334155] bg-[#0B1020] p-6 text-center text-xs text-[#94A3B8]">
                    No matching insurance plans found in hospital documents. Please submit a
                    Human-Support Ticket on the right so our TPA Helpdesk can verify your policy.
                  </div>
                ) : (
                  displayedProviders.map((prov) => (
                    <div
                      key={prov.id}
                      className="rounded-xl border border-[#334155] bg-[#0B1020] p-5 space-y-3"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <div className="flex items-center gap-2 text-xs text-[#94A3B8]">
                            <span className="font-mono text-[#2DD4BF]">{prov.code}</span>
                            <span aria-hidden="true">·</span>
                            <span>Support: {prov.support_contact}</span>
                          </div>
                          <h3 className="mt-0.5 font-display text-base font-bold text-[#E5EDF7]">
                            {prov.name}
                          </h3>
                        </div>
                      </div>

                      <div className="space-y-2.5 pt-1">
                        {prov.plans.map((plan) => (
                          <div
                            key={plan.id}
                            className="rounded-lg border border-[#334155]/80 bg-[#111B2E] p-3.5 text-xs space-y-1.5"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="font-semibold text-[#E5EDF7]">{plan.plan_name}</span>
                              <div className="flex items-center gap-2 text-[11px] text-[#94A3B8]">
                                <span>{plan.plan_type}</span>
                                <span aria-hidden="true">·</span>
                                <span className="text-[#2DD4BF]">
                                  {plan.cashless_available ? 'Cashless Available' : 'Reimbursement'}
                                </span>
                              </div>
                            </div>
                            <p className="text-[#94A3B8]">{plan.coverage_summary}</p>
                            <p className="text-[11px] text-[#E5EDF7]">
                              <strong>Covered Services:</strong> {plan.covered_services}
                            </p>
                            <p className="text-[11px] text-[#94A3B8]">
                              <strong>Co-pay &amp; Pre-Auth:</strong> {plan.copay_summary}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Right 5 Cols: Human-Support Escalation Ticket Form */}
            <div className="lg:col-span-5 rounded-xl border border-[#334155] bg-[#0B1020] p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-[#334155] pb-3">
                <div className="flex items-center gap-2">
                  <LifeBuoy className="h-4 w-4 text-[#38BDF8]" />
                  <h3 className="font-display text-base font-bold text-[#E5EDF7]">
                    Escalate to Human Insurance Support
                  </h3>
                </div>
              </div>

              <p className="text-xs text-[#94A3B8]">
                When policy documents do not answer your question, submit a support ticket for our
                Insurance &amp; TPA Helpdesk team.
              </p>

              {ticketFeedback && (
                <div
                  className={`rounded-lg border p-3 text-xs ${
                    ticketFeedback.type === 'success'
                      ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
                      : 'border-rose-500/40 bg-rose-500/10 text-rose-200'
                  }`}
                >
                  {ticketFeedback.message}
                </div>
              )}

              <form onSubmit={(e) => void handleCreateSupportTicket(e)} className="space-y-3">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <label className="block text-xs text-[#94A3B8]">Provider Name (Optional)</label>
                    <input
                      type="text"
                      value={ticketProvider}
                      onChange={(e) => setTicketProvider(e.target.value)}
                      placeholder="e.g. Aarogya Shield"
                      className="mt-1 w-full rounded-lg border border-[#334155] bg-[#111B2E] px-3 py-2 text-xs text-[#E5EDF7]"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-[#94A3B8]">Plan Name (Optional)</label>
                    <input
                      type="text"
                      value={ticketPlan}
                      onChange={(e) => setTicketPlan(e.target.value)}
                      placeholder="e.g. Gold Cashless Plus"
                      className="mt-1 w-full rounded-lg border border-[#334155] bg-[#111B2E] px-3 py-2 text-xs text-[#E5EDF7]"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs text-[#94A3B8]">Preferred Follow-Up</label>
                  <input
                    type="text"
                    value={ticketContactPref}
                    onChange={(e) => setTicketContactPref(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-[#334155] bg-[#111B2E] px-3 py-2 text-xs text-[#E5EDF7]"
                  />
                </div>

                <div>
                  <label className="block text-xs text-[#94A3B8]">
                    Your Policy / Coverage Question (Required)
                  </label>
                  <textarea
                    rows={3}
                    required
                    minLength={5}
                    value={ticketQuestion}
                    onChange={(e) => setTicketQuestion(e.target.value)}
                    placeholder="Describe the procedure, implant, or room-rent eligibility question you need verified..."
                    className="mt-1 w-full rounded-lg border border-[#334155] bg-[#111B2E] p-3 text-xs text-[#E5EDF7]"
                  />
                </div>

                <button
                  type="submit"
                  disabled={isSubmittingTicket}
                  className="w-full rounded-lg bg-[#38BDF8] px-4 py-2.5 text-xs font-semibold text-[#0B1020] hover:bg-[#38BDF8]/90 disabled:opacity-50"
                >
                  {isSubmittingTicket
                    ? 'Submitting Escalation Ticket...'
                    : 'Submit Human-Support Ticket'}
                </button>
              </form>

              {supportTickets.length > 0 && (
                <div className="border-t border-[#334155] pt-3 space-y-2">
                  <p className="text-xs font-semibold text-[#94A3B8]">
                    Your Submitted Tickets ({supportTickets.length})
                  </p>
                  <div className="max-h-36 space-y-1.5 overflow-y-auto pr-1">
                    {supportTickets.slice(0, 4).map((tk) => (
                      <div
                        key={tk.ticket_id}
                        className="rounded border border-[#334155] bg-[#111B2E] p-2.5 text-[11px]"
                      >
                        <div className="flex items-center justify-between font-mono">
                          <span className="text-[#2DD4BF]">#{tk.ticket_id.slice(0, 8)}</span>
                          <span className="text-[#E5EDF7]">{tk.status}</span>
                        </div>
                        <p className="mt-1 text-[#94A3B8] line-clamp-2">{tk.question}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>
      )}
    </div>
  );
};
