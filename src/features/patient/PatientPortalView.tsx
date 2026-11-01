import React from 'react';
import {
  Activity,
  ArrowRight,
  Building2,
  Calendar,
  FlaskConical,
  MapPin,
  PhoneCall,
  ShieldCheck,
  Stethoscope,
} from 'lucide-react';
import { usePlatform } from '../../context/PlatformContext';
import { MediVoiceChatPanel } from '../chat/MediVoiceChatPanel';
import { AppointmentBookingSection } from '../appointments/AppointmentBookingSection';
import { LabVerificationSection } from '../laboratory/LabVerificationSection';
import { InsuranceGuidanceSection } from '../insurance/InsuranceGuidanceSection';

export const PatientPortalView: React.FC = () => {
  const { hospital, doctors, appointments, labOrders, setActiveWorkspace } = usePlatform();

  const scrollToSection = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <div className="mx-auto max-w-[1440px] px-4 py-8 sm:px-6 lg:px-8 space-y-16">
      {/* Asymmetric Hero Section: 5-Column Editorial Proposition + 7-Column Live MediVoice AI Carrier */}
      <section className="grid grid-cols-1 items-start gap-8 lg:grid-cols-12">
        <div className="lg:col-span-5 space-y-6 pt-2">
          <div className="inline-flex items-center gap-2 rounded-lg border border-[#2DD4BF]/30 bg-[#111B2E] px-3 py-1.5 text-xs font-medium text-[#2DD4BF]">
            <Building2 className="h-3.5 w-3.5" />
            <span>
              {hospital?.name || 'Aarogya One Hospital'} • Bengaluru Tertiary Care (Synthetic Demo)
            </span>
          </div>

          <h1 className="font-display text-3xl font-extrabold tracking-tight text-[#E5EDF7] sm:text-4xl lg:text-[42px] lg:leading-[1.12]">
            Multilingual Voice-First Hospital Operations & Patient Care
          </h1>

          <p className="text-base leading-relaxed text-[#94A3B8]">
            Navigate specialist consultations, transaction-safe appointment slots, privacy-guarded 6-digit laboratory status verification, and cashless insurance guidance across English, తెలుగు, தமிழ், ಕನ್ನಡ, and हिन्दी.
          </p>

          {/* Primary Action & Quick Jump Navigation */}
          <div className="flex flex-wrap items-center gap-3 pt-1">
            <button
              type="button"
              onClick={() => scrollToSection('appointments-section')}
              className="inline-flex items-center gap-2 rounded-xl bg-[#2DD4BF] px-5 py-3 text-sm font-bold text-[#0B1020] transition-colors hover:bg-[#2DD4BF]/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#38BDF8]"
            >
              <Calendar className="h-4 w-4" />
              <span>Book Specialist Slot</span>
              <ArrowRight className="h-4 w-4" />
            </button>

            <button
              type="button"
              onClick={() => scrollToSection('lab-verification-section')}
              className="inline-flex items-center gap-2 rounded-xl border border-[#334155] bg-[#111B2E] px-4 py-3 text-sm font-semibold text-[#E5EDF7] transition-colors hover:border-[#38BDF8] hover:text-[#38BDF8]"
            >
              <FlaskConical className="h-4 w-4 text-[#38BDF8]" />
              <span>Verify 6-Digit Lab Code</span>
            </button>

            <button
              type="button"
              onClick={() => scrollToSection('insurance-section')}
              className="inline-flex items-center gap-2 rounded-xl border border-[#334155] bg-[#111B2E] px-4 py-3 text-sm font-semibold text-[#E5EDF7] transition-colors hover:border-[#2DD4BF] hover:text-[#2DD4BF]"
            >
              <ShieldCheck className="h-4 w-4 text-[#2DD4BF]" />
              <span>Insurance & TPA Desk</span>
            </button>
          </div>

          {/* Grounded Operational Snapshot (Derived Directly from Live Database Entities) */}
          <div className="grid grid-cols-3 gap-3 pt-2">
            <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-3.5">
              <span className="block font-mono text-[11px] uppercase text-[#94A3B8]">
                Active Physicians
              </span>
              <span className="mt-1 block font-mono text-2xl font-bold text-[#E5EDF7] tabular-nums">
                {doctors.length}
              </span>
              <span className="mt-0.5 block text-[11px] text-[#2DD4BF]">
                5 Clinical Specialties
              </span>
            </div>

            <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-3.5">
              <span className="block font-mono text-[11px] uppercase text-[#94A3B8]">
                Appointments
              </span>
              <span className="mt-1 block font-mono text-2xl font-bold text-[#E5EDF7] tabular-nums">
                {appointments.length}
              </span>
              <span className="mt-0.5 block text-[11px] text-[#38BDF8]">
                Row-Lock Protected
              </span>
            </div>

            <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-3.5">
              <span className="block font-mono text-[11px] uppercase text-[#94A3B8]">
                Active Lab Queue
              </span>
              <span className="mt-1 block font-mono text-2xl font-bold text-[#E5EDF7] tabular-nums">
                {labOrders.length}
              </span>
              <span className="mt-0.5 block text-[11px] text-[#2DD4BF]">
                6-Digit Code Guarded
              </span>
            </div>
          </div>

          {/* Emergency Triage Priority Notice */}
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-xs text-rose-200">
            <div className="flex items-center gap-2 font-semibold text-rose-300">
              <PhoneCall className="h-4 w-4 shrink-0" />
              <span>24/7 Emergency & Trauma Stabilization Protocol</span>
            </div>
            <p className="mt-1 leading-relaxed text-rose-100/90">
              If you are experiencing severe chest pain, acute shortness of breath, stroke symptoms, or medical emergencies, call <strong>108 / 112</strong> immediately or proceed to the Aarogya One Emergency Department. MediVoice AI automatically pauses routine outpatient booking when acute emergency symptoms are reported.
            </p>
          </div>
        </div>

        {/* Right 7 Columns: Live MediVoice AI Conversational Assistant */}
        <div className="lg:col-span-7">
          <MediVoiceChatPanel />
        </div>
      </section>

      {/* Clinical Departments & Connected Operations Bento Grid */}
      <section className="space-y-5">
        <div className="flex flex-col justify-between gap-3 border-b border-[#334155] pb-4 sm:flex-row sm:items-end">
          <div>
            <span className="font-mono text-xs font-semibold uppercase tracking-wider text-[#38BDF8]">
              Tertiary Clinical Departments
            </span>
            <h2 className="mt-1 font-display text-2xl font-bold text-[#E5EDF7]">
              Integrated Specialties & Connected Hospital Workspaces
            </h2>
          </div>
          {hospital?.address && (
            <span className="flex items-center gap-1.5 text-xs text-[#94A3B8]">
              <MapPin className="h-3.5 w-3.5 text-[#2DD4BF]" />
              {hospital.address}
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {(
            hospital?.departments || [
              {
                id: 'dept-1',
                name: 'Cardiology',
                description:
                  'Adult & pediatric cardiovascular care, ECG, ECHO, and interventional cardiology.',
              },
              {
                id: 'dept-2',
                name: 'Neurology',
                description:
                  'Comprehensive neurological disorders, stroke management, and neuro-diagnostics.',
              },
              {
                id: 'dept-3',
                name: 'Orthopedics',
                description: 'Joint replacement, trauma care, spine, and sports medicine.',
              },
              {
                id: 'dept-4',
                name: 'Pediatrics',
                description:
                  'Comprehensive child health, immunization, and pediatric subspecialties.',
              },
              {
                id: 'dept-5',
                name: 'General Medicine',
                description:
                  'Internal medicine, preventive checkups, and chronic disease management.',
              },
            ]
          ).map((dept, index) => {
            const deptDoctors = doctors.filter(
              (d) =>
                d.specialty.toLowerCase() === dept.name.toLowerCase() ||
                (d.department_name || '').toLowerCase() === dept.name.toLowerCase()
            );
            return (
              <div
                key={dept.id}
                className={`rounded-xl border border-[#334155] bg-[#111B2E] p-5 flex flex-col justify-between ${
                  index === 0 ? 'md:col-span-2' : 'md:col-span-1'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-semibold text-[#2DD4BF]">
                      0{index + 1}. {dept.name.toUpperCase()}
                    </span>
                    <Stethoscope className="h-4 w-4 text-[#38BDF8]" />
                  </div>
                  <h3 className="mt-2 font-display text-lg font-bold text-[#E5EDF7]">
                    Department of {dept.name}
                  </h3>
                  <p className="mt-1 text-xs leading-relaxed text-[#94A3B8]">
                    {dept.description}
                  </p>
                </div>

                <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-[#334155]/70 pt-3 text-xs">
                  <span className="text-[#E5EDF7] font-medium">
                    {deptDoctors.map((d) => d.display_name).join(', ') || 'Consulting Specialists'}
                  </span>
                  <button
                    type="button"
                    onClick={() => scrollToSection('appointments-section')}
                    className="font-mono text-xs font-semibold text-[#2DD4BF] hover:underline"
                  >
                    View Schedule →
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Module 1: Specialist Appointment Booking */}
      <AppointmentBookingSection />

      {/* Module 2: Six-Digit Laboratory Report Verification */}
      <LabVerificationSection />

      {/* Module 3: Hospital Insurance Providers, Plans & TPA Support Tickets */}
      <InsuranceGuidanceSection />

      {/* Quiet Hospital Footer */}
      <footer className="border-t border-[#334155] pt-8 pb-6 text-xs text-[#94A3B8]">
        <div className="flex flex-col justify-between gap-6 sm:flex-row sm:items-center">
          <div className="space-y-1">
            <div className="flex items-center gap-2 font-display text-sm font-bold text-[#E5EDF7]">
              <Activity className="h-4 w-4 text-[#2DD4BF]" />
              <span>Aarogya One Hospital • MediVoice AI Operations Platform</span>
            </div>
            <p>
              Plot 42, Outer Ring Road, Bellandur, Bengaluru, Karnataka 560103 • Synthetic Healthcare Demonstration Environment
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => setActiveWorkspace('doctor')}
              className="rounded-lg border border-[#334155] bg-[#111B2E] px-3 py-1.5 hover:border-[#2DD4BF] hover:text-[#E5EDF7]"
            >
              Doctor Workspace
            </button>
            <button
              type="button"
              onClick={() => setActiveWorkspace('lab')}
              className="rounded-lg border border-[#334155] bg-[#111B2E] px-3 py-1.5 hover:border-[#38BDF8] hover:text-[#E5EDF7]"
            >
              Laboratory Dashboard
            </button>
            <button
              type="button"
              onClick={() => setActiveWorkspace('maintenance')}
              className="rounded-lg border border-[#334155] bg-[#111B2E] px-3 py-1.5 hover:border-[#2DD4BF] hover:text-[#E5EDF7]"
            >
              Maintenance Dashboard
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
};
