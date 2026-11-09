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
  Languages,
  LifeBuoy,
  Lock,
  LogIn,
  MapPin,
  MessageSquare,
  PhoneCall,
  Search,
  ShieldCheck,
  ShieldAlert,
  Stethoscope,
  Sparkles,
  XCircle,
} from 'lucide-react';
import { usePlatform } from '../../app/PlatformContext';
import { ApiError, medivoiceApi } from '../../services/api';
import {
  AppointmentRead,
  AppointmentSlotRead,
  DoctorRead,
  InsuranceSearchResponse,
  LabVerificationResponse,
} from '../../types/api';
import { MediVoiceChatExperience } from '../chatbot/MediVoiceChatExperience';
import { ErrorBoundary } from '../../components/ErrorBoundary';
import { getPatientAppointmentReferences, rememberPatientAppointmentReference } from '../../services/patientAppointmentAccess';
import { formatHospitalDateTime, formatHospitalTime } from '../../services/formatting';

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
    navigate,
    hospital,
    doctors,
    insuranceProviders,
    insuranceContact,
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
  const [slotsError, setSlotsError] = useState<string | null>(null);
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
  const [managedAppointments, setManagedAppointments] = useState<AppointmentRead[]>([]);
  const [appointmentReferenceInput, setAppointmentReferenceInput] = useState('');
  const [isLookingUpAppointment, setIsLookingUpAppointment] = useState(false);
  const [appointmentLookupError, setAppointmentLookupError] = useState<string | null>(null);

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
  const [insuranceSearchError, setInsuranceSearchError] = useState<string | null>(null);
  const [hasSearchedInsurance, setHasSearchedInsurance] = useState(false);

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

  const handleTalkToMediVoice = () => {
    const chatSection = document.getElementById('medivoice-ai-chat');
    if (chatSection) {
      chatSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setTimeout(() => {
        const inputEl = document.getElementById('medivoice-message-input') as HTMLInputElement | null;
        if (inputEl) {
          inputEl.focus();
        }
      }, 450);
    }
  };

  useEffect(() => {
    let isCurrent = true;
    const savedReferences = getPatientAppointmentReferences();
    if (savedReferences.length) {
      void Promise.all(savedReferences.map((reference) =>
        medivoiceApi.getAppointmentByReference(reference).catch(() => null)
      )).then((records) => {
        if (isCurrent) setManagedAppointments(records.filter((record): record is AppointmentRead => Boolean(record)));
      });
    }
    return () => { isCurrent = false; };
  }, []);

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
    setSlotsError(null);
    setSelectedSlot(null);
    setShowConfirmModal(false);
    medivoiceApi
      .getDoctorSlots(selectedDoctor.id)
      .then((slots) => {
        setAvailableSlots(slots);
      })
      .catch(() => {
        setAvailableSlots([]);
        setSlotsError('We couldn’t load this doctor’s available times. Please retry or choose another doctor.');
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

  const patientAppointments = managedAppointments;

  const handleLookupAppointment = async (event: React.FormEvent) => {
    event.preventDefault();
    const reference = appointmentReferenceInput.trim();
    if (!reference) return;
    setIsLookingUpAppointment(true);
    setAppointmentLookupError(null);
    try {
      const appointment = await medivoiceApi.getAppointmentByReference(reference);
      setManagedAppointments((current) => [appointment, ...current.filter((item) => item.id !== appointment.id)]);
      rememberPatientAppointmentReference(appointment.id);
      setAppointmentReferenceInput('');
    } catch (error) {
      setAppointmentLookupError(error instanceof ApiError && error.status === 404
        ? 'We couldn’t find an appointment for that reference. Check it and try again.'
        : error instanceof ApiError ? error.message : 'We couldn’t retrieve that appointment. Please try again.');
    } finally {
      setIsLookingUpAppointment(false);
    }
  };

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
      rememberPatientAppointmentReference(created.id);
      setManagedAppointments((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setBookingFeedback({
        type: 'success',
        message: `Appointment confirmed with ${created.doctor_name || selectedDoctor.display_name}. Your private management reference is ${created.id}. It is saved in this browser session.`,
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
      const cancelled = await medivoiceApi.cancelAppointment(
        appointmentId,
        'Cancelled by patient via Aarogya One Hospital website'
      );
      setManagedAppointments((current) => current.map((appointment) => appointment.id === cancelled.id ? cancelled : appointment));
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
    setHasSearchedInsurance(true);
    setInsuranceSearchError(null);
    try {
      const res = await medivoiceApi.searchInsurance({
        q: insQuery.trim() || undefined,
        service: insServiceFilter.trim() || undefined,
        cashless: insCashlessOnly ? true : undefined,
      });
      setInsSearchRes(res);
    } catch (err) {
      setInsSearchRes(null);
      setInsuranceSearchError(err instanceof ApiError ? err.message : 'Insurance search is unavailable right now. Please retry.');
    } finally {
      setIsSearchingIns(false);
    }
  };

  const handleCreateSupportTicket = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticketQuestion.trim() || ticketQuestion.trim().length < 5 || !activePatientRef.trim()) return;
    setIsSubmittingTicket(true);
    setTicketFeedback(null);
    try {
      const created = await medivoiceApi.createInsuranceSupportTicket({
        patient_reference: activePatientRef.trim(),
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

  const displayedProviders = insSearchRes ? insSearchRes.providers : hasSearchedInsurance ? [] : insuranceProviders;

  // ============================================================================
  // Dedicated Full-Screen MediVoice AI Route (/medivoice)
  // ============================================================================
  if (currentRoute === '/medivoice') {
    return (
      <div className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8">
        <ErrorBoundary
          boundaryName="MediVoice Voice Assistant"
          level="widget"
          fallbackTitle="Voice Assistant Temporarily Unavailable"
          fallbackMessage="The MediVoice AI voice interface encountered a temporary rendering issue. You can restart the assistant or return to the patient portal."
        >
          <MediVoiceChatExperience mode="fullscreen" />
        </ErrorBoundary>
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
            className="inline-flex items-center gap-2 text-xs font-semibold text-[#61708A] hover:text-[#17233B] whitespace-nowrap shrink-0"
          >
            <ArrowLeft className="h-4 w-4" />
            Return to Public Hospital Website
          </button>
          <span className="font-mono text-xs text-[#087E75]">Staff Operations Portal</span>
        </div>

        <div className="rounded-xl border border-violet-100 bg-white p-6 sm:p-8 space-y-6">
          <div className="flex items-start gap-3.5 border-b border-violet-100 pb-5">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-[#2DD4BF]/30 bg-slate-50 text-[#087E75]">
              <Lock className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs font-semibold text-[#087E75]">
                Aarogya One Hospital · Authorized Staff Access
              </p>
              <h1 className="mt-1 font-display text-2xl font-bold text-[#17233B]">
                Staff Portal Sign-In
              </h1>
              <p className="mt-1 text-xs leading-relaxed text-[#61708A]">
                Sign in with your hospital staff credentials to access Doctor, Laboratory Operator,
                Maintenance Staff, or Administrator workspaces.
              </p>
            </div>
          </div>

          {staffProfile && (
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-[#2DD4BF]/40 bg-slate-50 p-4">
              <div>
                <p className="text-xs text-[#61708A]">Active Staff Session</p>
                <p className="font-display text-base font-bold text-[#17233B]">
                  {staffProfile.display_name} ·{' '}
                  <span className="font-mono text-xs text-[#087E75]">{staffProfile.role}</span>
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    if (staffProfile.role === 'DEMO_VIEWER') navigate('/staff/demo');
                    else if (staffProfile.role === 'DOCTOR') navigate('/doctor');
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
                  className="rounded-lg border border-violet-100 bg-white px-3 py-2 text-xs text-[#61708A] hover:text-[#17233B] whitespace-nowrap"
                >
                  Sign Out
                </button>
              </div>
            </div>
          )}

          {authError && (
            <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3.5 text-xs text-rose-900">
              {authError}
            </div>
          )}

          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (!loginUsername.trim()) return;
              if (!loginPassword) return;
              const res = await loginAsStaff(loginUsername.trim(), loginPassword);
              if (res) {
                if (res.role === 'DEMO_VIEWER') navigate('/staff/demo');
                else if (res.role === 'DOCTOR') navigate('/doctor');
                else if (res.role === 'LAB_OPERATOR') navigate('/lab');
                else navigate('/maintenance');
              }
            }}
            className="space-y-4"
          >
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2 font-semibold text-[#17233B]">
                <KeyRound className="h-4 w-4 text-[#2861B7]" />
                <span>Staff Credentials</span>
              </div>
              <span className="font-mono text-[11px] text-[#61708A]">
                Roles: Doctor · Lab Operator · Maintenance · Admin
              </span>
            </div>

            <div>
              <label
                htmlFor="portal-staff-username"
                className="block text-xs font-medium text-[#61708A]"
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
                className="mt-1.5 w-full rounded-lg border border-violet-100 bg-slate-50 px-3.5 py-2.5 font-mono text-xs text-[#17233B] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none"
              />
            </div>

            <div>
              <label
                htmlFor="portal-staff-password"
                className="block text-xs font-medium text-[#61708A]"
              >
                Password
              </label>
              <input
                id="portal-staff-password"
                type="password"
                required
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                placeholder="Enter your staff password"
                className="mt-1.5 w-full rounded-lg border border-violet-100 bg-slate-50 px-3.5 py-2.5 font-mono text-xs text-[#17233B] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none"
              />
            </div>

            <button
              type="submit"
              disabled={isAuthenticating || !loginUsername.trim() || !loginPassword}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#2DD4BF] px-4 py-3 text-xs font-semibold text-[#0B1020] transition-colors hover:bg-[#2DD4BF]/90 disabled:opacity-50"
            >
              <LogIn className="h-4 w-4" />
              {isAuthenticating ? 'Authenticating Staff Session...' : 'Sign In to Staff Workspace'}
            </button>

            <div className="flex items-start gap-2 pt-2 text-[11px] text-[#61708A]">
              <ShieldCheck className="h-4 w-4 shrink-0 text-[#087E75]" />
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
    <div className="mx-auto max-w-[1440px] space-y-14 px-4 py-8 sm:px-6 lg:px-8 text-[#17233B]">
      {/* ====================================================================
          PUBLIC PATIENT LANDING PAGE (`/`)
      ==================================================================== */}
      {currentRoute === '/' && (
        <>
          {/* Section 1: Full-Width Hero Section */}
          <section className="patient-hero w-full flex flex-col justify-between rounded-[2.25rem] p-8 sm:p-12 lg:p-16 text-white shadow-xl shadow-violet-950/10">
            <div className="space-y-6">
              <div className="flex flex-wrap items-center gap-2 text-xs text-white/75">
                <span className="font-semibold text-[#B9FFF2]">
                  Aarogya One Hospital
                </span>
                <span aria-hidden="true">·</span>
                <span>Multilingual Conversational Hospital Services</span>
                <span className="rounded-full border border-white/25 bg-white/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-white">
                  Synthetic demo
                </span>
              </div>

              <h1
                className="font-display font-bold tracking-tight text-white max-w-4xl"
                style={{
                  fontSize: 'clamp(2.4rem, 4vw, 3.6rem)',
                  lineHeight: 1.1,
                  textWrap: 'balance',
                }}
              >
                Healthcare conversations that move things forward.
              </h1>

              <p className="max-w-2xl text-base sm:text-lg leading-relaxed text-white/85">
                Discover doctors, manage appointments, check laboratory status, and get help with
                insurance through one conversational assistant connected to controlled hospital
                workflows.
              </p>

              {/* Primary & Secondary CTAs */}
              <div className="flex flex-wrap items-center gap-3.5 pt-2">
                <button
                  type="button"
                  onClick={handleTalkToMediVoice}
                  className="inline-flex items-center gap-2.5 rounded-full bg-white px-6 py-3.5 text-sm font-semibold text-[#5D43D3] shadow-lg shadow-violet-950/20 transition-all hover:-translate-y-0.5 hover:shadow-xl whitespace-nowrap shrink-0 cursor-pointer"
                >
                  <MessageSquare className="h-4.5 w-4.5 text-[#5D43D3]" />
                  Talk to MediVoice
                </button>
                <button
                  type="button"
                  onClick={() => navigate('/doctors')}
                  className="inline-flex items-center gap-2.5 rounded-full border border-white/35 bg-white/10 px-6 py-3.5 text-sm font-semibold text-white backdrop-blur transition-all hover:bg-white/20 whitespace-nowrap shrink-0 cursor-pointer"
                >
                  Find Doctors
                  <ArrowRight className="h-4.5 w-4.5 text-[#B9FFF2]" />
                </button>
              </div>
            </div>

            {/* Hospital Trust & Safety Boundaries */}
            <div className="mt-12 border-t border-white/25 pt-6 grid grid-cols-1 gap-6 sm:grid-cols-3 text-xs sm:text-sm">
              <div>
                <p className="font-mono text-xl sm:text-2xl font-bold tabular-nums text-white">
                  {doctors.length || 7} Specialists
                </p>
                <p className="mt-1 text-white/70">
                  Across 5 clinical departments with real-time slot locks
                </p>
              </div>
              <div>
                <p className="font-mono text-xl sm:text-2xl font-bold tabular-nums text-[#B9FFF2]">
                  5 Languages
                </p>
                <p className="mt-1 text-white/70">
                  English, Telugu, Hindi, Tamil & Kannada continuity
                </p>
              </div>
              <div>
                <p className="font-mono text-xl sm:text-2xl font-bold tabular-nums text-[#C5D9FF]">
                  6-Digit Lab Code
                </p>
                <p className="mt-1 text-white/70">
                  Verified sample stage tracking without diagnostic fabrication
                </p>
              </div>
            </div>
          </section>

          {/* Section 2: Full-Width MediVoice AI Chat */}
          <section id="medivoice-ai-chat" className="w-full scroll-mt-6">
            <ErrorBoundary
              boundaryName="MediVoice Conversational Assistant"
              level="widget"
              fallbackTitle="Conversational Assistant Temporarily Unavailable"
              fallbackMessage="The interactive hospital assistant encountered an issue. Tap below to restart your conversation or use direct booking below."
            >
              <MediVoiceChatExperience mode="fullwidth" />
            </ErrorBoundary>
          </section>

          {/* 4-Service Entry Points Strip */}
          <section className="space-y-4">
            <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-end">
              <div>
                <p className="text-xs font-semibold text-[#7657FF]">
                  One Conversational Entry Point · Four Controlled Patient Services
                </p>
                <h2 className="mt-1 font-display text-2xl font-bold text-[#17233B]">
                  Routine Hospital Services Connected End-to-End
                </h2>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="flex flex-col justify-between rounded-xl border border-violet-100 bg-white p-6">
                <div>
                  <div className="flex items-center justify-between text-xs text-[#61708A]">
                    <span>01. Doctor Discovery</span>
                    <Stethoscope className="h-4 w-4 text-[#087E75]" />
                  </div>
                  <h3 className="mt-3 font-display text-lg font-bold text-[#17233B]">
                    Find Specialists by Symptom or Wing
                  </h3>
                  <p className="mt-2 text-xs leading-relaxed text-[#61708A]">
                    Explore Cardiology, Neurology, Orthopedics, Pediatrics, and General Medicine
                    physicians with live unbooked time slots.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => navigate('/doctors')}
                  className="mt-5 inline-flex items-center gap-1.5 text-xs font-semibold text-[#087E75] hover:underline whitespace-nowrap"
                >
                  Browse Doctor Directory <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>

              <div className="flex flex-col justify-between rounded-xl border border-violet-100 bg-white p-6">
                <div>
                  <div className="flex items-center justify-between text-xs text-[#61708A]">
                    <span>02. Appointment Booking</span>
                    <Calendar className="h-4 w-4 text-[#2861B7]" />
                  </div>
                  <h3 className="mt-3 font-display text-lg font-bold text-[#17233B]">
                    Two-Step Explicit Confirmation
                  </h3>
                  <p className="mt-2 text-xs leading-relaxed text-[#61708A]">
                    Every appointment requires explicit patient confirmation before locking a slot
                    in the hospital schedule.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => navigate('/appointments')}
                  className="mt-5 inline-flex items-center gap-1.5 text-xs font-semibold text-[#2861B7] hover:underline whitespace-nowrap"
                >
                  Manage Appointments <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>

              <div className="flex flex-col justify-between rounded-xl border border-violet-100 bg-white p-6">
                <div>
                  <div className="flex items-center justify-between text-xs text-[#61708A]">
                    <span>03. Lab Status Tracking</span>
                    <FlaskConical className="h-4 w-4 text-[#087E75]" />
                  </div>
                  <h3 className="mt-3 font-display text-lg font-bold text-[#17233B]">
                    6-Digit Code Verification
                  </h3>
                  <p className="mt-2 text-xs leading-relaxed text-[#61708A]">
                    Verify whether your diagnostic sample is Registered, Sample Collected,
                    Processing, or Completed Ready.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => navigate('/lab-status')}
                  className="mt-5 inline-flex items-center gap-1.5 text-xs font-semibold text-[#087E75] hover:underline whitespace-nowrap"
                >
                  Verify Lab Code <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>

              <div className="flex flex-col justify-between rounded-xl border border-violet-100 bg-white p-6">
                <div>
                  <div className="flex items-center justify-between text-xs text-[#61708A]">
                    <span>04. Insurance Assistance</span>
                    <HeartHandshake className="h-4 w-4 text-[#2861B7]" />
                  </div>
                  <h3 className="mt-3 font-display text-lg font-bold text-[#17233B]">
                    Document-Grounded Plan Guidance
                  </h3>
                  <p className="mt-2 text-xs leading-relaxed text-[#61708A]">
                    Check cashless and reimbursement plans or escalate unanswered policy questions
                    to the human TPA helpdesk.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => navigate('/insurance')}
                  className="mt-5 inline-flex items-center gap-1.5 text-xs font-semibold text-[#2861B7] hover:underline whitespace-nowrap"
                >
                  Search Insurance Plans <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </section>

          {/* How It Works (Three-Step Journey) & Hospital Campus Info */}
          <section className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            <div className="lg:col-span-7 rounded-xl border border-violet-100 bg-white p-7 space-y-6">
              <div>
                <p className="text-xs font-semibold text-[#087E75]">How MediVoice AI Works</p>
                <h2 className="mt-1 font-display text-xl font-bold text-[#17233B]">
                  Controlled Architecture from Natural Question to Confirmed Action
                </h2>
              </div>

              <div className="space-y-5">
                <div className="border-b border-violet-100/70 pb-4">
                  <p className="text-xs font-semibold text-[#2861B7]">01. Ask Naturally</p>
                  <p className="mt-1 text-sm text-[#17233B]">
                    Speak or type in English, Telugu, Hindi, Tamil, or Kannada. MediVoice AI
                    preserves your language and conversation context across follow-up turns.
                  </p>
                </div>
                <div className="border-b border-violet-100/70 pb-4">
                  <p className="text-xs font-semibold text-[#087E75]">
                    02. Connect to Approved Hospital Workflows
                  </p>
                  <p className="mt-1 text-sm text-[#17233B]">
                    Requests execute strictly through validated backend services for doctor
                    discovery, real-time slot checks, 6-digit laboratory verification, and
                    document-grounded insurance search.
                  </p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-[#2861B7]">
                    03. Receive Verified Status or Human Support Escalation
                  </p>
                  <p className="mt-1 text-sm text-[#17233B]">
                    Appointments require explicit patient confirmation. Missing insurance policy
                    details are never invented—they escalate directly to our human Insurance &amp;
                    TPA Helpdesk.
                  </p>
                </div>
              </div>
            </div>

            {/* Aarogya One Hospital Information Panel */}
            <div className="lg:col-span-5 rounded-xl border border-violet-100 bg-white p-7 flex flex-col justify-between space-y-6">
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-xs text-[#087E75]">
                  <Building2 className="h-4 w-4" />
                  <span>About Our Hospital</span>
                </div>
                <h2 className="font-display text-xl font-bold text-[#17233B]">
                  {hospital?.name || 'Aarogya One Hospital'}
                </h2>
                <p className="text-xs leading-relaxed text-[#61708A]">
                  {hospital?.description ||
                    'Explore sample workflows for doctor discovery, appointment scheduling, lab status checks, and insurance guidance.'}
                </p>

                <div className="space-y-2 pt-2 text-xs text-[#17233B]">
                  <div className="flex items-center gap-2 text-[#61708A]">
                    <MapPin className="h-3.5 w-3.5 text-[#2861B7]" />
                    <span>
                      {hospital?.address || 'Hospital location has not been configured.'}
                    </span>
                  </div>
                  {insuranceContact && (
                    <div className="flex items-start gap-2 text-[#61708A]">
                      <PhoneCall className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#087E75]" />
                      <span>
                        {insuranceContact.desk_name}: {insuranceContact.contact_number || insuranceContact.phone}
                        {' · '}{insuranceContact.desk_location || insuranceContact.location}
                        {insuranceContact.hours || insuranceContact.operating_hours ? ` · ${insuranceContact.hours || insuranceContact.operating_hours}` : ''}
                        {insuranceContact.is_synthetic_demo && <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-900">Demo contact</span>}
                      </span>
                    </div>
                  )}
                </div>

                {/* Clinical Wings List */}
                <div className="pt-2">
                  <p className="text-xs font-semibold text-[#61708A]">Active Clinical Wings</p>
                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-[#17233B]">
                    {(hospital?.departments || []).map((dept, idx) => (
                      <React.Fragment key={dept.id}>
                        {idx > 0 && <span aria-hidden="true" className="text-[#334155]">·</span>}
                        <span>{dept.name}</span>
                      </React.Fragment>
                    ))}
                  </div>
                </div>
              </div>

              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3.5 text-xs text-amber-950">
                <div className="flex items-center gap-2 font-semibold text-amber-900">
                  <ShieldAlert className="h-4 w-4 shrink-0" />
                  <span>Clinical Safety Boundary</span>
                </div>
                <p className="mt-1 text-amber-900">
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
                <p className="text-xs font-semibold text-[#087E75]">
                  Hospital Specialist Roster
                </p>
                <h2 className="mt-1 font-display text-2xl font-bold text-[#17233B]">
                  Consult Experienced Physicians Across Clinical Departments
                </h2>
              </div>
              <button
                type="button"
                onClick={() => navigate('/doctors')}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#2861B7] hover:underline whitespace-nowrap"
              >
                View Full Directory &amp; Open Slots <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {doctors.slice(0, 6).map((doc) => (
                <div
                  key={doc.id}
                  className="flex flex-col justify-between rounded-xl border border-violet-100 bg-white p-5"
                >
                  <div>
                    <div className="flex items-center gap-2 text-xs text-[#61708A]">
                      <span className="font-medium text-[#087E75]">
                        {doc.department_name || doc.specialty}
                      </span>
                      <span aria-hidden="true">·</span>
                      <span>Aarogya One Hospital</span>
                    </div>
                    <h3 className="mt-1.5 font-display text-base font-bold text-[#17233B]">
                      {doc.display_name}
                    </h3>
                    <p className="mt-0.5 text-xs text-[#61708A]">{doc.specialty}</p>
                  </div>

                  <div className="mt-4 flex items-center justify-between border-t border-violet-100/70 pt-3">
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedDoctor(doc);
                        navigate('/doctors');
                      }}
                      className="text-xs font-semibold text-[#087E75] hover:underline whitespace-nowrap"
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
                      className="text-xs text-[#2861B7] hover:underline whitespace-nowrap"
                    >
                      Ask MediVoice
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Patient confidence and review preview. Reviews are deliberately
              identified as illustrative because this demo has no review API. */}
          <section className="overflow-hidden rounded-[2rem] border border-violet-100 bg-white shadow-[0_24px_70px_rgba(67,61,122,.08)]">
            <div className="grid lg:grid-cols-12">
              <div className="relative overflow-hidden bg-gradient-to-br from-[#F0ECFF] via-[#F7F5FF] to-[#EAF8FF] p-7 sm:p-10 lg:col-span-4 lg:p-12">
                <div className="absolute -right-12 -top-12 h-44 w-44 rounded-full border-[24px] border-white/50" aria-hidden="true" />
                <div className="relative">
                  <div className="inline-flex items-center gap-2 rounded-full border border-violet-100 bg-white/80 px-3 py-1.5 text-[11px] font-semibold text-violet-700">
                    <Sparkles className="h-3.5 w-3.5" /> Patient experience preview
                  </div>
                  <h2 className="mt-5 font-display text-3xl font-bold leading-tight text-[#17233B]">
                    Care feels better when the next step is clear.
                  </h2>
                  <p className="mt-3 text-sm leading-relaxed text-slate-600">
                    MediVoice brings everyday hospital tasks into one helpful conversation, with clear choices and human support when you need it.
                  </p>
                  <div className="mt-7 rounded-2xl border border-white bg-white/85 p-5 shadow-sm">
                    <p className="font-display text-xl font-bold text-[#17233B]">No rating claims</p>
                    <p className="mt-1 text-xs text-slate-500">This demo does not collect or publish patient reviews.</p>
                    <div className="mt-4 flex items-center gap-3 border-t border-slate-100 pt-4">
                      <div className="flex -space-x-2" aria-hidden="true">
                        {['bg-violet-300', 'bg-sky-300', 'bg-teal-300', 'bg-rose-300'].map((color, i) => <span key={i} className={`h-7 w-7 rounded-full border-2 border-white ${color}`} />)}
                      </div>
                    <p className="text-xs text-slate-600"><strong className="text-slate-900">Built around clear next steps</strong><br />A product concept preview</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="p-6 sm:p-9 lg:col-span-8 lg:p-10">
                <div className="flex flex-wrap items-end justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[.14em] text-[#7657FF]">Product concept examples</p>
                    <h3 className="mt-1 font-display text-2xl font-bold text-[#17233B]">Small details that make routine tasks clearer</h3>
                  </div>
                  <span className="rounded-full bg-violet-50 px-3 py-1.5 text-[11px] font-medium text-violet-800">Illustrative examples · not patient reviews</span>
                </div>
                <div className="mt-6 grid gap-4 md:grid-cols-3">
                  {[
                    { quote: 'Review the selected doctor, open time, and visit reason before confirming a booking.', name: 'Appointment booking', tint: 'bg-violet-50 text-violet-700' },
                    { quote: 'Use the verification code from your receipt to check the current sample stage.', name: 'Laboratory status', tint: 'bg-sky-50 text-blue-700' },
                    { quote: 'Escalate policy questions when plan documents do not provide an answer.', name: 'Insurance support', tint: 'bg-teal-50 text-teal-700' },
                  ].map((review) => (
                    <article key={review.name} className="flex min-h-52 flex-col rounded-2xl border border-slate-100 bg-[#FCFCFE] p-5">
                      <div className="flex items-center justify-between">
                        <Sparkles className={`h-5 w-5 ${review.tint.split(' ')[1]}`} />
                      </div>
                      <p className="mt-4 flex-1 text-sm leading-relaxed text-slate-700">{review.quote}</p>
                      <div className="mt-4 border-t border-slate-100 pt-3">
                        <p className="text-xs font-semibold text-slate-900">{review.name}</p>
                        <p className="mt-0.5 text-[11px] text-slate-500">Current product workflow</p>
                      </div>
                    </article>
                  ))}
                </div>
                <p className="mt-4 text-[11px] leading-relaxed text-slate-500">These are feature descriptions, not patient testimonials. No patient reviews or ratings are published in this demo.</p>
              </div>
            </div>
          </section>

          {/* Value story: editorial split instead of another row of cards. */}
          <section className="grid gap-6 lg:grid-cols-12 lg:items-center">
            <div className="lg:col-span-5">
              <p className="text-xs font-semibold uppercase tracking-[.14em] text-[#4387FF]">Made for the moments in between</p>
              <h2 className="mt-2 font-display text-3xl font-bold leading-tight text-[#17233B] sm:text-4xl">Less searching. More knowing what comes next.</h2>
              <p className="mt-4 max-w-xl text-sm leading-relaxed text-slate-600">From finding the right specialist to checking a sample update, the assistant helps you move through routine steps at your own pace.</p>
              <button type="button" onClick={() => launchMediVoiceWithPrompt()} className="mt-6 inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-[#7657FF] to-[#4387FF] px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-violet-100 transition-transform hover:-translate-y-0.5">
                Start a conversation <ArrowRight className="h-4 w-4" />
              </button>
            </div>
            <div className="relative overflow-hidden rounded-[2rem] bg-[#17233B] p-7 text-white sm:p-9 lg:col-span-7">
              <div className="absolute -right-10 -top-16 h-64 w-64 rounded-full bg-violet-500/30 blur-3xl" aria-hidden="true" />
              <div className="relative grid gap-6 sm:grid-cols-2">
                <div className="rounded-2xl border border-white/10 bg-white/[.06] p-5">
                  <Languages className="h-5 w-5 text-[#7DE8D8]" />
                  <h3 className="mt-4 font-display text-lg font-bold">Your language, your pace</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-300">Chat in English, Telugu, Hindi, Tamil, or Kannada, by typing or voice when supported by your device.</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[.06] p-5">
                  <ShieldCheck className="h-5 w-5 text-[#BFB0FF]" />
                  <h3 className="mt-4 font-display text-lg font-bold">You stay in control</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-300">Review the doctor, time, and reason before confirming an appointment. Your confirmation is required to book.</p>
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/[.06] p-5 sm:col-span-2">
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[.12em] text-[#FFC76A]">A clear handoff</p>
                      <h3 className="mt-1 font-display text-lg font-bold">When a human should step in, we make that the next step.</h3>
                    </div>
                    <button type="button" onClick={() => navigate('/insurance')} className="inline-flex items-center gap-2 rounded-full border border-white/20 px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-white/10">Insurance help <ArrowRight className="h-3.5 w-3.5" /></button>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* Patient-friendly FAQ focused on the actual supported workflows. */}
          <section className="rounded-[2rem] bg-[#F2F0FF] p-6 sm:p-10">
            <div className="grid gap-8 lg:grid-cols-12">
              <div className="lg:col-span-4">
                <p className="text-xs font-semibold uppercase tracking-[.14em] text-violet-700">A few helpful answers</p>
                <h2 className="mt-2 font-display text-3xl font-bold text-[#17233B]">Before you get started</h2>
                <p className="mt-3 text-sm leading-relaxed text-slate-600">Here’s what MediVoice can help with today.</p>
              </div>
              <div className="space-y-3 lg:col-span-8">
                {[
                  ['Can MediVoice diagnose a health concern?', 'No. MediVoice supports routine hospital tasks such as scheduling, lab status verification, and insurance guidance. It is not a diagnosis service. For urgent symptoms, seek emergency care.'],
                  ['Does MediVoice book an appointment automatically?', 'No. You review the selected doctor and available time, then confirm before the booking request is submitted.'],
                  ['Does an insurance plan listing guarantee coverage?', 'No. Plan information is guidance only. Individual coverage depends on your policy and insurer; unanswered questions can be sent to the hospital support team.'],
                ].map(([question, answer], i) => (
                  <details key={question} className="group rounded-2xl border border-white bg-white px-5 py-4 open:shadow-sm">
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold text-[#17233B]">
                      <span>{question}</span><span className="text-xl text-violet-600 transition-transform group-open:rotate-45" aria-hidden="true">+</span>
                    </summary>
                    <p className="mt-3 max-w-3xl text-sm leading-relaxed text-slate-600">{answer}</p>
                  </details>
                ))}
              </div>
            </div>
          </section>
        </>
      )}

      {/* ====================================================================
          DOCTOR DISCOVERY & APPOINTMENT BOOKING (`/doctors`, `/appointments`)
      ==================================================================== */}
      {(currentRoute === '/doctors' || currentRoute === '/appointments') && (
        <section className="space-y-6">
          <div className="flex flex-col justify-between gap-4 border-b border-violet-100 pb-4 sm:flex-row sm:items-end">
            <div>
              <p className="text-xs font-semibold text-[#087E75]">
                Specialist Directory &amp; Real-Time Slot Reservation
              </p>
              <h2 className="mt-1 font-display text-2xl font-bold text-[#17233B]">
                {currentRoute === '/appointments'
                  ? 'Book & Manage Patient Appointments'
                  : 'Explore Hospital Specialists & Open Slots'}
              </h2>
            </div>

            {/* Department & Search Filters */}
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-2.5 h-3.5 w-3.5 text-[#61708A]" />
                <input
                  type="text"
                  value={doctorSearchQuery}
                  onChange={(e) => setDoctorSearchQuery(e.target.value)}
                  placeholder="Search doctor or specialty..."
                  className="rounded-lg border border-violet-100 bg-white pl-8 pr-3 py-1.5 text-xs text-[#17233B] placeholder-[#94A3B8]/60 focus:border-[#2DD4BF] focus:outline-none"
                />
              </div>

              <select
                value={selectedDepartment}
                onChange={(e) => setSelectedDepartment(e.target.value)}
                aria-label="Filter doctors by department"
                className="rounded-lg border border-violet-100 bg-white px-3 py-1.5 text-xs text-[#17233B] focus:border-[#2DD4BF] focus:outline-none"
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
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
                  : 'border-rose-200 bg-rose-50 text-rose-900'
              }`}
            >
              <div className="flex items-center gap-2">
                {bookingFeedback.type === 'success' ? (
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-700" />
                ) : (
                  <AlertCircle className="h-4 w-4 shrink-0 text-rose-700" />
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
                <div className="sm:col-span-2 rounded-xl border border-violet-100 bg-white p-8 text-center text-xs text-[#61708A]">
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
                          ? 'border-[#2DD4BF] bg-white'
                          : 'border-violet-100 bg-white/70 hover:border-[#38BDF8]'
                      }`}
                    >
                      <div>
                        <div className="flex items-center gap-2 text-xs text-[#61708A]">
                          <span className="text-[#087E75] font-medium">
                            {doc.department_name || doc.specialty}
                          </span>
                          <span aria-hidden="true">·</span>
                          <span>Active Roster</span>
                        </div>
                        <h3 className="mt-1.5 font-display text-base font-bold text-[#17233B]">
                          {doc.display_name}
                        </h3>
                        <p className="mt-0.5 text-xs text-[#61708A]">{doc.specialty}</p>
                      </div>

                      <div className="mt-4 flex items-center justify-between border-t border-violet-100/70 pt-3">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedDoctor(doc);
                          }}
                          className="text-xs font-semibold text-[#087E75] hover:underline whitespace-nowrap"
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
                          className="text-xs text-[#2861B7] hover:underline whitespace-nowrap"
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
            <div className="lg:col-span-5 rounded-xl border border-violet-100 bg-white p-6 space-y-5">
              {!selectedDoctor ? (
                <p className="py-10 text-center text-xs text-[#61708A]">
                  Select a specialist to view open appointment slots.
                </p>
              ) : (
                <>
                  <div className="border-b border-violet-100 pb-4">
                    <div className="flex items-center gap-2 text-xs text-[#61708A]">
                      <span className="text-[#087E75] font-medium">
                        {selectedDoctor.department_name || selectedDoctor.specialty}
                      </span>
                      <span aria-hidden="true">·</span>
                      <span>Available Consultation Slots</span>
                    </div>
                    <h3 className="mt-1 font-display text-lg font-bold text-[#17233B]">
                      {selectedDoctor.display_name}
                    </h3>
                    <p className="text-xs text-[#61708A]">{selectedDoctor.specialty}</p>
                  </div>

                  <div>
                    <label
                      htmlFor="booking-patient-reference"
                      className="block text-xs font-medium text-[#61708A]"
                    >
                      Patient Registration / Hospital ID
                    </label>
                    <input
                      id="booking-patient-reference"
                      type="text"
                      value={activePatientRef}
                      onChange={(e) => setActivePatientRef(e.target.value)}
                      placeholder="Enter your registration ID"
                      className="mt-1.5 w-full rounded-lg border border-violet-100 bg-slate-50 px-3 py-2 font-mono text-xs text-[#17233B] focus:border-[#2DD4BF] focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-[#61708A]">
                      Reason for Consultation
                    </label>
                    <select
                      value={reasonCategory}
                      onChange={(e) => setReasonCategory(e.target.value)}
                      className="mt-1.5 w-full rounded-lg border border-violet-100 bg-slate-50 px-3 py-2 text-xs text-[#17233B] focus:border-[#2DD4BF] focus:outline-none"
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
                      <span className="text-xs font-medium text-[#61708A]">
                        Available Slots ({availableSlots.length})
                      </span>
                    </div>

                    {isLoadingSlots ? (
                      <p className="py-6 text-center text-xs text-[#61708A]">
                        Loading open slots from hospital schedule...
                      </p>
                    ) : slotsError ? (
                      <div role="alert" className="mt-2 rounded-lg border border-rose-200 bg-rose-50 p-4 text-xs text-rose-900">
                        <p>{slotsError}</p>
                        <button type="button" onClick={() => { setIsLoadingSlots(true); setSlotsError(null); void medivoiceApi.getDoctorSlots(selectedDoctor.id).then(setAvailableSlots).catch(() => setSlotsError('We couldn’t load this doctor’s available times. Please retry or choose another doctor.')).finally(() => setIsLoadingSlots(false)); }} className="mt-2 font-semibold text-violet-800 underline">Try again</button>
                      </div>
                    ) : availableSlots.length === 0 ? (
                      <div className="mt-2 rounded-lg border border-violet-100 bg-slate-50 p-4 text-xs text-[#61708A]">
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
                                  ? 'border-[#2DD4BF] bg-[#2DD4BF]/15 text-[#087E75]'
                                  : 'border-violet-100 bg-slate-50 text-[#17233B] hover:border-[#38BDF8]'
                              }`}
                            >
                              <div className="font-semibold">
                                {new Date(slot.start_time).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', month: 'short', day: 'numeric' })}
                              </div>
                              <div className="mt-0.5 text-[11px] text-[#61708A]">
                                {formatHospitalTime(slot.start_time)}
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
                      disabled={!activePatientRef.trim()}
                      onClick={() => setShowConfirmModal(true)}
                        className="w-full rounded-lg bg-[#7657FF] px-4 py-2.5 text-xs font-semibold text-white hover:bg-[#6544F0] disabled:cursor-not-allowed disabled:opacity-50"
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
                      <div className="space-y-1 text-[#17233B]">
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
                            {formatHospitalDateTime(selectedSlot.start_time)}
                          </span>
                        </p>
                        <p>
                          <strong>Reason:</strong> {reasonCategory}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 pt-1">
                        <button
                          type="button"
                          disabled={isBooking || !activePatientRef.trim()}
                          onClick={() => void handleConfirmBooking()}
                          className="flex-1 rounded-lg bg-[#2DD4BF] px-3 py-2 font-semibold text-[#0B1020] hover:bg-[#2DD4BF]/90 disabled:opacity-50"
                        >
                          {isBooking ? 'Booking...' : 'Confirm & Lock Appointment'}
                        </button>
                        <button
                          type="button"
                          onClick={() => setShowConfirmModal(false)}
                          className="rounded-lg border border-violet-100 bg-slate-50 px-3 py-2 text-[#61708A] hover:text-[#17233B]"
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

          {/* Patient appointment access uses the random booking reference, not a patient ID lookup. */}
          {currentRoute === '/appointments' && (
            <div className="rounded-2xl border border-violet-100 bg-white p-6 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3.5">
                <div>
                  <h3 className="font-display text-lg font-bold text-[#17233B]">
                    Your Appointments ({patientAppointments.length})
                  </h3>
                  <p className="mt-1 max-w-2xl text-sm text-slate-600">
                    Use the private appointment reference from your booking confirmation. A hospital ID alone cannot retrieve appointment details.
                  </p>
                </div>
              </div>

              <form onSubmit={(event) => void handleLookupAppointment(event)} className="mt-4 flex flex-col gap-2 sm:flex-row">
                <label htmlFor="appointment-management-reference" className="sr-only">Private appointment reference</label>
                <input id="appointment-management-reference" autoComplete="off" value={appointmentReferenceInput} onChange={(event) => setAppointmentReferenceInput(event.target.value)} placeholder="Paste your private appointment reference" className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-violet-500 focus:outline-none focus:ring-2 focus:ring-violet-100" />
                <button type="submit" disabled={isLookingUpAppointment || !appointmentReferenceInput.trim()} className="rounded-xl bg-violet-600 px-5 py-3 text-sm font-semibold text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50">{isLookingUpAppointment ? 'Looking up…' : 'Find appointment'}</button>
              </form>
              {appointmentLookupError && <p role="alert" className="mt-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{appointmentLookupError}</p>}

              {patientAppointments.length === 0 ? (
                <div className="mt-5 rounded-2xl bg-slate-50 px-5 py-6 text-center">
                  <Calendar className="mx-auto h-6 w-6 text-violet-500" />
                  <p className="mt-2 text-sm font-semibold text-slate-800">No appointment references loaded</p>
                  <p className="mt-1 text-sm text-slate-600">New bookings appear here. This browser session keeps their references for you.</p>
                </div>
              ) : (
                <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {patientAppointments.map((appt) => (
                    <div
                      key={appt.id}
                      className="flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-4 text-sm"
                    >
                      <div>
                        <div className="flex items-center justify-between text-slate-600">
                          <span className="text-xs font-semibold">Appointment status</span>
                          <span
                            className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                              appt.appointment_status === 'CONFIRMED'
                                ? 'bg-teal-50 text-teal-800'
                                : appt.appointment_status === 'COMPLETED'
                                ? 'bg-emerald-50 text-emerald-800'
                                : 'bg-rose-50 text-rose-800'
                            }`}
                          >
                            {appt.appointment_status}
                          </span>
                        </div>
                        <p className="mt-3 font-display text-base font-bold text-slate-900">
                          {appt.doctor_name || 'Hospital Specialist'}
                        </p>
                        <p className="text-sm text-slate-600">
                          {appt.doctor_specialty} · {appt.reason_category}
                        </p>
                        {appt.slot_start_time && (
                          <p className="mt-2 inline-flex items-center gap-1.5 text-sm font-medium text-blue-800">
                            <Clock className="h-4 w-4" />
                            {formatHospitalDateTime(appt.slot_start_time)}
                          </p>
                        )}
                        {appt.follow_up_recommended && (
                          <p className="mt-2 rounded-lg bg-emerald-50 p-2 text-xs text-emerald-900">
                            Follow-up recommendation: {appt.follow_up_notes || 'Recommended by clinician'}
                          </p>
                        )}
                        <div className="mt-3 rounded-xl bg-violet-50 p-3">
                          <p className="text-[11px] font-semibold uppercase tracking-wide text-violet-800">Private management reference</p>
                          <p className="mt-1 break-all font-mono text-xs text-violet-950">{appt.id}</p>
                          <p className="mt-1 text-[11px] text-violet-800">Keep this code private. It can be used to view or cancel this booking.</p>
                        </div>
                      </div>

                      {appt.appointment_status === 'CONFIRMED' && (
                        <div className="mt-3 border-t border-slate-100 pt-3 flex justify-end">
                          <button
                            type="button"
                            disabled={cancellingId === appt.id}
                            onClick={() => void handleCancelAppointment(appt.id)}
                            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-50"
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
        <section className="rounded-xl border border-violet-100 bg-white p-6 sm:p-8 space-y-6">
          <div className="flex flex-col justify-between gap-2 border-b border-violet-100 pb-4 sm:flex-row sm:items-end">
            <div>
              <p className="text-xs font-semibold text-[#087E75]">
                Controlled Diagnostic Status Verification
              </p>
              <h2 className="mt-1 font-display text-2xl font-bold text-[#17233B]">
                Check Laboratory Report Status with Your 6-Digit Code
              </h2>
            </div>
            <button
              type="button"
              onClick={() =>
                launchMediVoiceWithPrompt('I want to check my lab report status with my 6-digit code')
              }
              className="text-xs font-semibold text-[#2861B7] hover:underline whitespace-nowrap"
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
                  className="h-11 flex-1 rounded-lg border border-violet-100 bg-slate-50 px-4 font-mono text-sm tracking-widest text-[#17233B] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none tabular-nums"
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
                <div role="alert" className="flex items-start gap-2.5 rounded-lg border border-rose-200 bg-rose-50 p-4 text-xs text-rose-900">
                  <AlertCircle className="h-4 w-4 shrink-0 text-rose-700 mt-0.5" />
                  <span>{labError}</span>
                </div>
              )}

              {labResult && (
                <div className="rounded-xl border border-[#2DD4BF]/40 bg-slate-50 p-5 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-display text-base font-bold text-[#17233B]">
                      {labResult.test_name}
                    </span>
                    <span className="font-mono text-xs font-semibold text-[#087E75]">
                      Stage: {labResult.lab_status}
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed text-[#17233B]">
                    {labResult.status_explanation}
                  </p>
                  <p className="text-xs text-[#2861B7]">
                    <strong>Next Step:</strong> {labResult.next_step}
                  </p>
                  <p className="border-t border-violet-100 pt-2 text-[11px] text-[#61708A]">
                    {labResult.disclaimer}
                  </p>
                </div>
              )}
            </div>

            {/* Right: Patient Privacy & Stage Guide */}
            <div className="lg:col-span-5 rounded-xl border border-violet-100 bg-slate-50 p-5 space-y-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-[#17233B]">
                <ShieldCheck className="h-4 w-4 text-[#087E75]" />
                <span>How 6-Digit Lab Verification Protects Your Privacy</span>
              </div>
              <p className="text-xs leading-relaxed text-[#61708A]">
                Use the private 6-digit code provided with your lab receipt. It displays your current
                processing stage and next step, without showing clinical results.
              </p>
              <div className="border-t border-violet-100 pt-3 space-y-1.5 text-xs text-[#61708A]">
                <p className="font-semibold text-[#17233B]">Standard Processing Stages:</p>
                <p>
                  <span className="font-mono text-[#087E75]">REGISTERED</span> — Order logged at
                  diagnostic reception
                </p>
                <p>
                  <span className="font-mono text-[#2861B7]">SAMPLE_COLLECTED</span> — Specimen
                  received by phlebotomy team
                </p>
                <p>
                  <span className="font-mono text-[#087E75]">PROCESSING</span> — Analysis underway
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
        <section className="rounded-xl border border-violet-100 bg-white p-6 sm:p-8 space-y-6">
          <div className="flex flex-col justify-between gap-2 border-b border-violet-100 pb-4 sm:flex-row sm:items-end">
            <div>
              <p className="text-xs font-semibold text-[#2861B7]">
                Document-Grounded Insurance Directory &amp; TPA Escalation
              </p>
              <h2 className="mt-1 font-display text-2xl font-bold text-[#17233B]">
                Hospital Insurance Plans &amp; Human-Support Escalation
              </h2>
            </div>
            {insuranceContact && (
              <span className="text-xs text-[#61708A]">
                Helpdesk: <strong className="text-[#17233B]">{insuranceContact.phone}</strong>
              </span>
            )}
          </div>

          {/* Non-Guarantee Coverage Disclaimer */}
          <div className="rounded-lg border border-violet-100 bg-slate-50 p-3.5 text-xs text-[#61708A]">
            <strong className="text-[#17233B]">Coverage Disclaimer:</strong> Listed insurance plan
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
                  className="h-10 flex-1 min-w-[200px] rounded-lg border border-violet-100 bg-slate-50 px-3.5 text-xs text-[#17233B] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none"
                />
                <input
                  type="text"
                  value={insServiceFilter}
                  onChange={(e) => setInsServiceFilter(e.target.value)}
                  placeholder="Service (e.g. Cardiology, OPD)"
                  className="h-10 w-44 rounded-lg border border-violet-100 bg-slate-50 px-3 text-xs text-[#17233B] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none"
                />
                <label className="flex items-center gap-1.5 text-xs text-[#17233B] cursor-pointer px-2">
                  <input
                    type="checkbox"
                    checked={insCashlessOnly}
                    onChange={(e) => setInsCashlessOnly(e.target.checked)}
                    className="rounded border-violet-100"
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
                {insuranceSearchError ? (
                  <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-6 text-center text-xs text-rose-900">
                    <p>{insuranceSearchError}</p>
                    <button type="button" onClick={() => void handleSearchInsurance()} className="mt-3 font-semibold text-violet-800 underline">Retry search</button>
                  </div>
                ) : displayedProviders.length === 0 ? (
                  <div className="rounded-lg border border-violet-100 bg-slate-50 p-6 text-center text-xs text-[#61708A]">
                    {hasSearchedInsurance ? 'No matching plans were found. Check your spelling or contact the insurance desk for policy-specific guidance.' : 'No insurance plans are available right now.'}
                  </div>
                ) : (
                  displayedProviders.map((prov) => (
                    <div
                      key={prov.id}
                      className="rounded-xl border border-violet-100 bg-slate-50 p-5 space-y-3"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <div className="flex items-center gap-2 text-xs text-[#61708A]">
                            <span className="font-mono text-[#087E75]">{prov.code}</span>
                            <span aria-hidden="true">·</span>
                            <span>Support: {prov.support_contact}</span>
                          </div>
                          <h3 className="mt-0.5 font-display text-base font-bold text-[#17233B]">
                            {prov.name}
                          </h3>
                        </div>
                      </div>

                      <div className="space-y-2.5 pt-1">
                        {prov.plans.map((plan) => (
                          <div
                            key={plan.id}
                            className="rounded-lg border border-violet-100/80 bg-white p-3.5 text-xs space-y-1.5"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="font-semibold text-[#17233B]">{plan.plan_name}</span>
                              <div className="flex items-center gap-2 text-[11px] text-[#61708A]">
                                <span>{plan.plan_type}</span>
                                <span aria-hidden="true">·</span>
                                <span className="text-[#087E75]">
                                  {plan.cashless_available ? 'Cashless Available' : 'Reimbursement'}
                                </span>
                              </div>
                            </div>
                            <p className="text-[#61708A]">{plan.coverage_summary}</p>
                            <p className="text-[11px] text-[#17233B]">
                              <strong>Covered Services:</strong> {plan.covered_services}
                            </p>
                            <p className="text-[11px] text-[#61708A]">
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
            <div className="lg:col-span-5 rounded-xl border border-violet-100 bg-slate-50 p-5 space-y-4">
              <div className="flex items-center justify-between border-b border-violet-100 pb-3">
                <div className="flex items-center gap-2">
                  <LifeBuoy className="h-4 w-4 text-[#2861B7]" />
                  <h3 className="font-display text-base font-bold text-[#17233B]">
                    Escalate to Human Insurance Support
                  </h3>
                </div>
              </div>

              <p className="text-xs text-[#61708A]">
                When policy documents do not answer your question, submit a support ticket for our
                Insurance &amp; TPA Helpdesk team.
              </p>

              {ticketFeedback && (
                <div
                  className={`rounded-lg border p-3 text-xs ${
                    ticketFeedback.type === 'success'
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
                      : 'border-rose-200 bg-rose-50 text-rose-900'
                  }`}
                >
                  {ticketFeedback.message}
                </div>
              )}

              <form onSubmit={(e) => void handleCreateSupportTicket(e)} className="space-y-3">
                <div>
                  <label htmlFor="insurance-patient-reference" className="block text-xs text-[#61708A]">Hospital reference for routing (Required)</label>
                  <input id="insurance-patient-reference" type="text" required value={activePatientRef} onChange={(e) => setActivePatientRef(e.target.value)} placeholder="Enter your registration ID" className="mt-1 w-full rounded-lg border border-violet-100 bg-white px-3 py-2 text-xs text-[#17233B]" />
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <label className="block text-xs text-[#61708A]">Provider Name (Optional)</label>
                    <input
                      type="text"
                      value={ticketProvider}
                      onChange={(e) => setTicketProvider(e.target.value)}
                      placeholder="e.g. Aarogya Shield"
                      className="mt-1 w-full rounded-lg border border-violet-100 bg-white px-3 py-2 text-xs text-[#17233B]"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-[#61708A]">Plan Name (Optional)</label>
                    <input
                      type="text"
                      value={ticketPlan}
                      onChange={(e) => setTicketPlan(e.target.value)}
                      placeholder="e.g. Gold Cashless Plus"
                      className="mt-1 w-full rounded-lg border border-violet-100 bg-white px-3 py-2 text-xs text-[#17233B]"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs text-[#61708A]">Preferred Follow-Up</label>
                  <input
                    type="text"
                    value={ticketContactPref}
                    onChange={(e) => setTicketContactPref(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-violet-100 bg-white px-3 py-2 text-xs text-[#17233B]"
                  />
                </div>

                <div>
                  <label className="block text-xs text-[#61708A]">
                    Your Policy / Coverage Question (Required)
                  </label>
                  <textarea
                    rows={3}
                    required
                    minLength={5}
                    value={ticketQuestion}
                    onChange={(e) => setTicketQuestion(e.target.value)}
                    placeholder="Describe the procedure, implant, or room-rent eligibility question you need verified..."
                    className="mt-1 w-full rounded-lg border border-violet-100 bg-white p-3 text-xs text-[#17233B]"
                  />
                </div>

                <button
                  type="submit"
                  disabled={isSubmittingTicket || !activePatientRef.trim()}
                  className="w-full rounded-lg bg-[#38BDF8] px-4 py-2.5 text-xs font-semibold text-[#0B1020] hover:bg-[#38BDF8]/90 disabled:opacity-50"
                >
                  {isSubmittingTicket
                    ? 'Submitting Escalation Ticket...'
                    : 'Submit Human-Support Ticket'}
                </button>
              </form>

            </div>
          </div>
        </section>
      )}
    </div>
  );
};
