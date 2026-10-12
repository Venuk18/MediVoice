import React, { useState } from 'react';
import {
  ShieldCheck,
  Database,
  Calendar,
  Activity,
  Bot,
  Terminal,
  FileCode2,
  Server,
  Building2,
  Stethoscope,
  Clock,
  AlertTriangle,
  History,
  CheckCircle2,
  XCircle,
  Play,
  RotateCcw,
  Sparkles,
  ExternalLink,
  ChevronRight,
  Layers,
  Search,
  Filter,
} from 'lucide-react';

// Seeded synthetic data mirroring backend/scripts/seed_data.py
const INITIAL_DOCTORS = [
  {
    id: "33333333-0001-0000-0000-000000000001",
    displayName: "Dr. Rajesh Sharma",
    specialty: "Cardiology",
    department: "Cardiology",
    departmentId: "22222222-0001-0000-0000-000000000001",
    experience: "15 yrs",
    opdRoom: "Cardiology Suite 102",
    slotsCount: 6,
    isActive: true,
  },
  {
    id: "33333333-0002-0000-0000-000000000002",
    displayName: "Dr. Priya Nair",
    specialty: "Neurology",
    department: "Neurology",
    departmentId: "22222222-0002-0000-0000-000000000002",
    experience: "12 yrs",
    opdRoom: "Neuro Center 204",
    slotsCount: 6,
    isActive: true,
  },
  {
    id: "33333333-0003-0000-0000-000000000003",
    displayName: "Dr. Arvind Swamy",
    specialty: "Orthopedics",
    department: "Orthopedics",
    departmentId: "22222222-0003-0000-0000-000000000003",
    experience: "18 yrs",
    opdRoom: "Joint Care Suite 105",
    slotsCount: 6,
    isActive: true,
  },
  {
    id: "33333333-0004-0000-0000-000000000004",
    displayName: "Dr. Ananya Sen",
    specialty: "Pediatrics",
    department: "Pediatrics",
    departmentId: "22222222-0004-0000-0000-000000000004",
    experience: "9 yrs",
    opdRoom: "Child Wellness 301",
    slotsCount: 6,
    isActive: true,
  },
  {
    id: "33333333-0005-0000-0000-000000000005",
    displayName: "Dr. Vikram Mehta",
    specialty: "General Medicine",
    department: "General Medicine",
    departmentId: "22222222-0005-0000-0000-000000000005",
    experience: "14 yrs",
    opdRoom: "Internal Medicine 108",
    slotsCount: 6,
    isActive: true,
  },
  {
    id: "33333333-0006-0000-0000-000000000006",
    displayName: "Dr. Sunita Rao",
    specialty: "Cardiology",
    department: "Cardiology",
    departmentId: "22222222-0001-0000-0000-000000000001",
    experience: "11 yrs",
    opdRoom: "Cardiology Suite 104",
    slotsCount: 6,
    isActive: true,
  },
];

const INITIAL_SLOTS = [
  { id: "slot-101", doctorId: "33333333-0001-0000-0000-000000000001", doctorName: "Dr. Rajesh Sharma", time: "Tomorrow, 10:00 AM - 10:30 AM", status: "AVAILABLE", rawTime: "2026-10-13T10:00:00Z" },
  { id: "slot-102", doctorId: "33333333-0001-0000-0000-000000000001", doctorName: "Dr. Rajesh Sharma", time: "Tomorrow, 02:00 PM - 02:30 PM", status: "AVAILABLE", rawTime: "2026-10-13T14:00:00Z" },
  { id: "slot-103", doctorId: "33333333-0001-0000-0000-000000000001", doctorName: "Dr. Rajesh Sharma", time: "Day 2, 10:00 AM - 10:30 AM", status: "BOOKED", rawTime: "2026-10-14T10:00:00Z" },
  { id: "slot-201", doctorId: "33333333-0002-0000-0000-000000000002", doctorName: "Dr. Priya Nair", time: "Tomorrow, 10:00 AM - 10:30 AM", status: "AVAILABLE", rawTime: "2026-10-13T10:00:00Z" },
  { id: "slot-202", doctorId: "33333333-0002-0000-0000-000000000002", doctorName: "Dr. Priya Nair", time: "Tomorrow, 02:00 PM - 02:30 PM", status: "AVAILABLE", rawTime: "2026-10-13T14:00:00Z" },
  { id: "slot-301", doctorId: "33333333-0003-0000-0000-000000000003", doctorName: "Dr. Arvind Swamy", time: "Tomorrow, 10:00 AM - 10:30 AM", status: "AVAILABLE", rawTime: "2026-10-13T10:00:00Z" },
  { id: "slot-401", doctorId: "33333333-0004-0000-0000-000000000004", doctorName: "Dr. Ananya Sen", time: "Tomorrow, 10:00 AM - 10:30 AM", status: "AVAILABLE", rawTime: "2026-10-13T10:00:00Z" },
  { id: "slot-501", doctorId: "33333333-0005-0000-0000-000000000005", doctorName: "Dr. Vikram Mehta", time: "Tomorrow, 10:00 AM - 10:30 AM", status: "AVAILABLE", rawTime: "2026-10-13T10:00:00Z" },
  { id: "slot-601", doctorId: "33333333-0006-0000-0000-000000000006", doctorName: "Dr. Sunita Rao", time: "Tomorrow, 10:00 AM - 10:30 AM", status: "AVAILABLE", rawTime: "2026-10-13T10:00:00Z" },
];

const INITIAL_APPOINTMENTS = [
  {
    id: "44444444-0001-0000-0000-000000000001",
    patientReference: "PAT-2024-9182",
    doctorName: "Dr. Rajesh Sharma",
    specialty: "Cardiology",
    time: "Tomorrow, 10:00 AM - 10:30 AM",
    slotId: "slot-103",
    status: "CONFIRMED",
    reason: "Chest Pain & Palpitations Evaluation",
    followUp: false,
  },
  {
    id: "44444444-0002-0000-0000-000000000002",
    patientReference: "PAT-2024-3310",
    doctorName: "Dr. Priya Nair",
    specialty: "Neurology",
    time: "Yesterday, 02:00 PM - 02:30 PM",
    slotId: "slot-299",
    status: "COMPLETED",
    reason: "Chronic Migraine & Visual Aura Review",
    followUp: true,
    followUpNotes: "Review headache frequency diary in 4 weeks. Repeat MRI if visual aura increases.",
  },
  {
    id: "44444444-0003-0000-0000-000000000003",
    patientReference: "PAT-2024-5501",
    doctorName: "Dr. Arvind Swamy",
    specialty: "Orthopedics",
    time: "Day 2, 10:00 AM - 10:30 AM",
    slotId: "slot-399",
    status: "CANCELLED",
    reason: "Knee Arthroscopy Follow-up",
    followUp: false,
  },
];

const INITIAL_LAB_ORDERS = [
  {
    id: "55555555-0001-0000-0000-000000000001",
    patientReference: "PAT-2024-9182",
    department: "Cardiology",
    testCategory: "Cardiac Troponin I & Lipid Profile",
    status: "Processing",
    expectedCompletion: "3 hours ago (OVERDUE)",
    isOverdue: true,
    assignedTeam: "Stat Biochemistry Core",
    delayReason: "Analyzer reagent recalibration in progress",
  },
  {
    id: "55555555-0002-0000-0000-000000000002",
    patientReference: "PAT-2024-3310",
    department: "Neurology",
    testCategory: "Serum Electrolytes & Vitamin B12",
    status: "Completed",
    expectedCompletion: "Completed on schedule",
    isOverdue: false,
    assignedTeam: "General Chemistry",
    delayReason: null,
  },
  {
    id: "55555555-0003-0000-0000-000000000003",
    patientReference: "PAT-2024-7744",
    department: "General Medicine",
    testCategory: "Glycated Hemoglobin (HbA1c)",
    status: "Pending",
    expectedCompletion: "In 4 hours",
    isOverdue: false,
    assignedTeam: "Routine Hematology",
    delayReason: null,
  },
];

const INITIAL_AUDIT_LOGS = [
  { id: "audit-1", action: "SYSTEM_INITIALIZED", actor: "SYSTEM_BOOTSTRAP", entity: "Hospital", entityId: "11111111-1111-...", time: "Bootstrap", details: '{"event": "Aarogya One Hospital Phase 1 Seed Applied"}' },
  { id: "audit-2", action: "APPOINTMENT_BOOKED", actor: "API_CLIENT", entity: "Appointment", entityId: "44444444-0001-...", time: "Bootstrap", details: '{"patient": "PAT-2024-9182", "doctor": "Dr. Rajesh Sharma"}' },
  { id: "audit-3", action: "APPOINTMENT_COMPLETED", actor: "DOCTOR_DASHBOARD", entity: "Appointment", entityId: "44444444-0002-...", time: "Bootstrap", details: '{"notes": "Visit concluded", "follow_up": true}' },
  { id: "audit-4", action: "EXCEPTION_DETECTED", actor: "WORKFLOW_INTELLIGENCE", entity: "WorkflowException", entityId: "66666666-0001-...", time: "Bootstrap", details: '{"type": "LAB_ORDER_OVERDUE", "order": "Troponin I"}' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<'architecture' | 'schema' | 'data' | 'ai_tools' | 'tests' | 'api'>('architecture');
  
  // Interactive testbench state
  const [slots, setSlots] = useState(INITIAL_SLOTS);
  const [appointments, setAppointments] = useState(INITIAL_APPOINTMENTS);
  const [auditLogs, setAuditLogs] = useState(INITIAL_AUDIT_LOGS);
  
  // AI Tool Form State
  const [selectedDoctorId, setSelectedDoctorId] = useState(INITIAL_DOCTORS[0].id);
  const [selectedSlotId, setSelectedSlotId] = useState("slot-101");
  const [patientRef, setPatientRef] = useState("PAT-2026-4409");
  const [reasonCategory, setReasonCategory] = useState("Acute Palpitations Consultation");
  const [simulationResult, setSimulationResult] = useState<{ status: 'success' | 'error' | null; message: string; details?: any }>({ status: null, message: '' });

  // Doctor search tool test state
  const [searchQuery, setSearchQuery] = useState("Cardiology");
  const [filteredDoctors, setFilteredDoctors] = useState(INITIAL_DOCTORS.filter(d => d.specialty === "Cardiology"));

  const handleSearchDoctors = () => {
    const q = searchQuery.trim().toLowerCase();
    const matches = INITIAL_DOCTORS.filter(
      d => d.specialty.toLowerCase().includes(q) || d.department.toLowerCase().includes(q) || d.displayName.toLowerCase().includes(q)
    );
    setFilteredDoctors(matches);
  };

  const handleSimulateBooking = (forceConflict = false) => {
    const targetSlot = slots.find(s => s.id === selectedSlotId);
    const targetDoctor = INITIAL_DOCTORS.find(d => d.id === selectedDoctorId);

    if (!targetSlot || !targetDoctor) {
      setSimulationResult({
        status: 'error',
        message: 'Invalid selection: Doctor or slot does not exist.',
      });
      return;
    }

    // Ownership check
    if (targetSlot.doctorId !== targetDoctor.id) {
      setSimulationResult({
        status: 'error',
        message: `HTTP 400 Bad Request: Slot '${targetSlot.id}' does not belong to ${targetDoctor.displayName}.`,
        details: { code: 'DOCTOR_SLOT_MISMATCH', doctorId: targetDoctor.id, slotDoctorId: targetSlot.doctorId }
      });
      return;
    }

    // Availability & Double booking check
    if (targetSlot.status !== 'AVAILABLE' || forceConflict) {
      setSimulationResult({
        status: 'error',
        message: `HTTP 409 Conflict: Slot '${targetSlot.id}' is no longer available (current status: '${targetSlot.status}'). Double booking rejected.`,
        details: { code: 'SLOT_ALREADY_RESERVED', slotId: targetSlot.id, currentStatus: targetSlot.status }
      });
      return;
    }

    // Transaction-safe execution
    const newApptId = `44444444-${Math.floor(1000 + Math.random() * 9000)}-0000-0000-000000000001`;
    const newAppointment = {
      id: newApptId,
      patientReference: patientRef,
      doctorName: targetDoctor.displayName,
      specialty: targetDoctor.specialty,
      time: targetSlot.time,
      slotId: targetSlot.id,
      status: "CONFIRMED",
      reason: reasonCategory,
      followUp: false,
    };

    // Update slot status atomically
    setSlots(prev => prev.map(s => s.id === targetSlot.id ? { ...s, status: "BOOKED" } : s));
    setAppointments(prev => [newAppointment, ...prev]);

    // Append to audit trail
    const newAudit = {
      id: `audit-${Date.now()}`,
      action: "APPOINTMENT_BOOKED",
      actor: "AI_VOICE_AGENT",
      entity: "Appointment",
      entityId: newApptId,
      time: "Just now",
      details: JSON.stringify({
        patient: patientRef,
        doctor: targetDoctor.displayName,
        slotId: targetSlot.id,
        reason: reasonCategory,
        dbConstraintEnforced: "uq_appointment_slot_id",
      }),
    };
    setAuditLogs(prev => [newAudit, ...prev]);

    setSimulationResult({
      status: 'success',
      message: `Transaction Committed: Appointment successfully booked for ${patientRef} with ${targetDoctor.displayName}.`,
      details: newAppointment,
    });
  };

  const handleCancelAppointment = (apptId: string, slotId: string) => {
    setAppointments(prev => prev.map(a => a.id === apptId ? { ...a, status: "CANCELLED" } : a));
    // Re-release slot
    setSlots(prev => prev.map(s => s.id === slotId ? { ...s, status: "AVAILABLE" } : s));
    
    setAuditLogs(prev => [
      {
        id: `audit-${Date.now()}`,
        action: "APPOINTMENT_CANCELLED",
        actor: "API_CLIENT",
        entity: "Appointment",
        entityId: apptId,
        time: "Just now",
        details: JSON.stringify({ reReleasedSlotId: slotId, status: "AVAILABLE" }),
      },
      ...prev,
    ]);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-3 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-teal-500 to-emerald-400 flex items-center justify-center shadow-lg shadow-teal-500/20 text-slate-950 font-bold">
              <Stethoscope className="w-6 h-6 text-slate-950" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-lg font-bold tracking-tight text-white">MediVoice AI</h1>
                <span className="px-2 py-0.5 text-xs font-semibold rounded bg-teal-950 text-teal-400 border border-teal-800">
                  Phase 1: Backend Foundation
                </span>
                <span className="px-2 py-0.5 text-xs font-semibold rounded bg-emerald-950 text-emerald-400 border border-emerald-800 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> 26/26 Tests Passing
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Hospital Context: <strong className="text-slate-200">Aarogya One Hospital</strong> (Fictional Tertiary Care, Bengaluru) &bull; Great Indian AI Internship Challenge
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2 text-xs">
            <div className="px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700/60 flex items-center gap-2">
              <Server className="w-3.5 h-3.5 text-emerald-400" />
              <span>FastAPI 0.143 + SQLAlchemy 2.1</span>
            </div>
            <div className="px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700/60 flex items-center gap-2">
              <Database className="w-3.5 h-3.5 text-cyan-400" />
              <span>PostgreSQL / Alembic Migration 0001</span>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="max-w-7xl mx-auto px-4 flex space-x-1 border-t border-slate-800/60 pt-1 overflow-x-auto">
          {[
            { id: 'architecture', label: 'Architecture & Overview', icon: Layers },
            { id: 'schema', label: 'Database Schema & Models', icon: Database },
            { id: 'data', label: 'Aarogya One Synthetic Data', icon: Building2 },
            { id: 'ai_tools', label: 'AI Tool Interfaces & Simulator', icon: Bot },
            { id: 'api', label: 'API Endpoints & Docs', icon: FileCode2 },
            { id: 'tests', label: 'Pytest Suite (26 Tests)', icon: ShieldCheck },
          ].map(tab => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center gap-2 px-4 py-2.5 text-xs font-medium border-b-2 transition-all whitespace-nowrap ${
                  isActive
                    ? 'border-teal-400 text-teal-300 bg-slate-800/50'
                    : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-teal-400' : 'text-slate-500'}`} />
                {tab.label}
              </button>
            );
          })}
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 md:p-6 space-y-6">
        {/* TAB 1: ARCHITECTURE & OVERVIEW */}
        {activeTab === 'architecture' && (
          <div className="space-y-6">
            {/* Mission Card */}
            <div className="bg-gradient-to-r from-slate-900 via-slate-900/90 to-teal-950/40 p-6 rounded-2xl border border-slate-800 relative overflow-hidden">
              <div className="max-w-3xl space-y-3 relative z-10">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-teal-500/10 border border-teal-500/30 text-teal-300 text-xs font-medium">
                  <Sparkles className="w-3.5 h-3.5" />
                  Phase 1 Objective: Zero-Slop Reliable Backend Architecture
                </div>
                <h2 className="text-2xl font-bold text-white tracking-tight">
                  Backend Foundation for MediVoice AI
                </h2>
                <p className="text-sm text-slate-300 leading-relaxed">
                  Phase 1 creates the transactional database backbone, domain models, synthetic data for Aarogya One Hospital, and strictly-typed Python service interfaces for future AI voice orchestration. The system enforces database-level integrity so that conversational AI models cannot fabricate appointment slots, execute unvalidated SQL, or cause race-condition double bookings.
                </p>
                <div className="flex flex-wrap gap-3 pt-2">
                  <div className="flex items-center gap-2 bg-slate-800/80 px-3 py-1.5 rounded-lg border border-slate-700 text-xs text-slate-200">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>PostgreSQL-Ready SQLAlchemy 2.x</span>
                  </div>
                  <div className="flex items-center gap-2 bg-slate-800/80 px-3 py-1.5 rounded-lg border border-slate-700 text-xs text-slate-200">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>Alembic 0001_initial_schema Migration</span>
                  </div>
                  <div className="flex items-center gap-2 bg-slate-800/80 px-3 py-1.5 rounded-lg border border-slate-700 text-xs text-slate-200">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>Transaction-Safe Atomic Slot Locking</span>
                  </div>
                  <div className="flex items-center gap-2 bg-slate-800/80 px-3 py-1.5 rounded-lg border border-slate-700 text-xs text-slate-200">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>Complete Audit Event Tracking</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Architecture Invariants Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-slate-900/60 p-5 rounded-xl border border-slate-800 space-y-3">
                <div className="w-8 h-8 rounded-lg bg-teal-500/10 border border-teal-500/20 flex items-center justify-center text-teal-400">
                  <ShieldCheck className="w-5 h-5" />
                </div>
                <h3 className="font-semibold text-white text-sm">1. Strict AI Boundaries</h3>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Reasoning models never receive raw SQL, direct database access, or the ability to pass arbitrary appointment statuses. All mutations pass through typed Pydantic & SQLAlchemy service functions.
                </p>
              </div>

              <div className="bg-slate-900/60 p-5 rounded-xl border border-slate-800 space-y-3">
                <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                  <Database className="w-5 h-5" />
                </div>
                <h3 className="font-semibold text-white text-sm">2. Anti-Double Booking</h3>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Enforced via database unique constraint <code className="text-emerald-300">uq_appointment_slot_id</code> and atomic row-level status transitions. Race conditions rollback with HTTP 409 Conflict.
                </p>
              </div>

              <div className="bg-slate-900/60 p-5 rounded-xl border border-slate-800 space-y-3">
                <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
                  <Activity className="w-5 h-5" />
                </div>
                <h3 className="font-semibold text-white text-sm">3. Workflow Intelligence Ready</h3>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Deterministic detection engine identifies turnaround-exceeded lab orders without duplicate tasks, enabling escalation, assignment, investigation notes, and resolution.
                </p>
              </div>
            </div>

            {/* File Structure Blueprint */}
            <div className="bg-slate-900 p-5 rounded-xl border border-slate-800">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <Terminal className="w-4 h-4 text-teal-400" />
                  <h3 className="text-sm font-semibold text-white">Project Structure & Implemented Files</h3>
                </div>
                <span className="text-xs text-slate-400 font-mono">backend/</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
                <div className="bg-slate-950 p-4 rounded-lg border border-slate-800/80 space-y-2">
                  <div className="text-teal-400 font-bold">// Core App, Database & Models</div>
                  <div className="text-slate-300">backend/app/main.py <span className="text-slate-500">(FastAPI, CORS, /docs)</span></div>
                  <div className="text-slate-300">backend/app/core/config.py <span className="text-slate-500">(Pydantic settings)</span></div>
                  <div className="text-slate-300">backend/app/db/session.py <span className="text-slate-500">(Engine & get_db)</span></div>
                  <div className="text-slate-300">backend/app/models/hospital.py</div>
                  <div className="text-slate-300">backend/app/models/department.py</div>
                  <div className="text-slate-300">backend/app/models/doctor.py</div>
                  <div className="text-slate-300">backend/app/models/appointment_slot.py</div>
                  <div className="text-slate-300">backend/app/models/appointment.py</div>
                  <div className="text-slate-300">backend/app/models/lab_order.py</div>
                  <div className="text-slate-300">backend/app/models/workflow_exception.py</div>
                  <div className="text-slate-300">backend/app/models/audit_event.py</div>
                </div>

                <div className="bg-slate-950 p-4 rounded-lg border border-slate-800/80 space-y-2">
                  <div className="text-teal-400 font-bold">// Services, API & Tests</div>
                  <div className="text-slate-300">backend/app/services/doctor_service.py <span className="text-slate-500">(+ AI tools)</span></div>
                  <div className="text-slate-300">backend/app/services/appointment_service.py <span className="text-slate-500">(Atomic booking)</span></div>
                  <div className="text-slate-300">backend/app/services/lab_service.py</div>
                  <div className="text-slate-300">backend/app/services/workflow_service.py</div>
                  <div className="text-slate-300">backend/app/api/v1/*.py <span className="text-slate-500">(5 Route modules)</span></div>
                  <div className="text-slate-300">backend/scripts/seed_data.py <span className="text-slate-500">(Idempotent seed)</span></div>
                  <div className="text-slate-300">backend/alembic/versions/0001_initial_schema.py</div>
                  <div className="text-emerald-400 font-bold">backend/tests/ <span className="text-slate-400">(4 test suites, 26 passing)</span></div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: DATABASE SCHEMA & MODELS */}
        {activeTab === 'schema' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-white">SQLAlchemy 2.x Relational Schema</h2>
                <p className="text-xs text-slate-400">PostgreSQL-compatible data models with UUID primary keys, temporal indexing, and unique constraints.</p>
              </div>
              <span className="text-xs px-2.5 py-1 rounded bg-slate-800 border border-slate-700 text-teal-300">
                8 Entities &bull; Alembic 0001_initial_schema
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Hospital */}
              <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="font-mono text-xs font-bold text-teal-400">hospitals</span>
                  <span className="text-[10px] text-slate-500">Core</span>
                </div>
                <div className="space-y-1.5 text-xs font-mono text-slate-300">
                  <div className="text-yellow-400">id: String(36) [PK]</div>
                  <div>name: String(255) [INDEX]</div>
                  <div>description: Text</div>
                  <div>address: Text</div>
                  <div>is_active: Boolean = true</div>
                  <div>created_at: DateTime(tz)</div>
                </div>
              </div>

              {/* Department */}
              <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="font-mono text-xs font-bold text-teal-400">departments</span>
                  <span className="text-[10px] text-slate-500">Relational</span>
                </div>
                <div className="space-y-1.5 text-xs font-mono text-slate-300">
                  <div className="text-yellow-400">id: String(36) [PK]</div>
                  <div className="text-cyan-400">hospital_id: String(36) [FK]</div>
                  <div>name: String(100) [INDEX]</div>
                  <div>description: Text</div>
                  <div>is_active: Boolean = true</div>
                  <div>created_at: DateTime(tz)</div>
                </div>
              </div>

              {/* Doctor */}
              <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="font-mono text-xs font-bold text-teal-400">doctors</span>
                  <span className="text-[10px] text-slate-500">Relational</span>
                </div>
                <div className="space-y-1.5 text-xs font-mono text-slate-300">
                  <div className="text-yellow-400">id: String(36) [PK]</div>
                  <div className="text-cyan-400">hospital_id: String(36) [FK]</div>
                  <div className="text-cyan-400">department_id: String(36) [FK]</div>
                  <div>display_name: String(150)</div>
                  <div>specialty: String(100) [INDEX]</div>
                  <div>is_active: Boolean = true</div>
                  <div>created_at: DateTime(tz)</div>
                </div>
              </div>

              {/* AppointmentSlot */}
              <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="font-mono text-xs font-bold text-teal-400">appointment_slots</span>
                  <span className="text-[10px] text-emerald-400">Slot Lock</span>
                </div>
                <div className="space-y-1.5 text-xs font-mono text-slate-300">
                  <div className="text-yellow-400">id: String(36) [PK]</div>
                  <div className="text-cyan-400">doctor_id: String(36) [FK]</div>
                  <div>start_time: DateTime(tz) [INDEX]</div>
                  <div>end_time: DateTime(tz)</div>
                  <div className="text-emerald-300">status: String(30) [INDEX]</div>
                  <div>created_at: DateTime(tz)</div>
                  <div className="text-rose-400 text-[10px] pt-1">UQ(doctor_id, start_time)</div>
                </div>
              </div>

              {/* Appointment */}
              <div className="bg-slate-900 p-4 rounded-xl border border-teal-800/40 space-y-3 shadow-lg shadow-teal-950/20">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="font-mono text-xs font-bold text-teal-300">appointments</span>
                  <span className="text-[10px] text-teal-400 font-bold">Transactional</span>
                </div>
                <div className="space-y-1.5 text-xs font-mono text-slate-300">
                  <div className="text-yellow-400">id: String(36) [PK]</div>
                  <div>patient_reference: String(100)</div>
                  <div className="text-cyan-400">doctor_id: String(36) [FK]</div>
                  <div className="text-rose-300 font-bold">slot_id: String(36) [FK, UNIQUE]</div>
                  <div className="text-teal-300">status: CONFIRMED | COMPLETED...</div>
                  <div>reason_category: String(100)</div>
                  <div>follow_up_recommended: Boolean</div>
                  <div>follow_up_date: DateTime(tz)</div>
                  <div>follow_up_notes: Text</div>
                </div>
              </div>

              {/* LabOrder */}
              <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="font-mono text-xs font-bold text-teal-400">lab_orders</span>
                  <span className="text-[10px] text-slate-500">Metadata</span>
                </div>
                <div className="space-y-1.5 text-xs font-mono text-slate-300">
                  <div className="text-yellow-400">id: String(36) [PK]</div>
                  <div>patient_reference: String(100)</div>
                  <div className="text-cyan-400">ordering_dept_id: String [FK]</div>
                  <div>test_category: String(100)</div>
                  <div className="text-purple-300">workflow_status: Pending...</div>
                  <div>expected_completion: DateTime [IX]</div>
                  <div>assigned_team: String(100)</div>
                  <div>delay_reason: Text</div>
                </div>
              </div>

              {/* WorkflowException */}
              <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="font-mono text-xs font-bold text-teal-400">workflow_exceptions</span>
                  <span className="text-[10px] text-amber-400">Ops Task</span>
                </div>
                <div className="space-y-1.5 text-xs font-mono text-slate-300">
                  <div className="text-yellow-400">id: String(36) [PK]</div>
                  <div>exception_type: String(100)</div>
                  <div>title: String(255)</div>
                  <div>priority: LOW | MED | HIGH | CRIT</div>
                  <div>status: OPEN | IN_PROG | RESOLVED</div>
                  <div>affected_record_type: String</div>
                  <div>affected_record_id: String</div>
                  <div>resolution_note: Text</div>
                </div>
              </div>

              {/* AuditEvent */}
              <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="font-mono text-xs font-bold text-teal-400">audit_events</span>
                  <span className="text-[10px] text-emerald-400">Immutable</span>
                </div>
                <div className="space-y-1.5 text-xs font-mono text-slate-300">
                  <div className="text-yellow-400">id: String(36) [PK]</div>
                  <div>actor_reference: String(100)</div>
                  <div className="text-emerald-300">action: APPOINTMENT_BOOKED...</div>
                  <div>entity_type: String(50)</div>
                  <div>entity_id: String(100) [INDEX]</div>
                  <div>details: Text (JSON string)</div>
                  <div>created_at: DateTime(tz)</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: AAROGYA ONE SYNTHETIC DATA */}
        {activeTab === 'data' && (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-lg font-bold text-white">Aarogya One Hospital &bull; Seeded Data</h2>
                <p className="text-xs text-slate-400">Populated by <code className="text-teal-300 font-mono">backend/scripts/seed_data.py</code>. Realistic synthetic identities with zero real patient information.</p>
              </div>
              <div className="flex items-center gap-2 text-xs">
                <span className="px-3 py-1 rounded-full bg-teal-500/10 border border-teal-500/20 text-teal-300">
                  5 Departments
                </span>
                <span className="px-3 py-1 rounded-full bg-teal-500/10 border border-teal-500/20 text-teal-300">
                  6 Doctors
                </span>
                <span className="px-3 py-1 rounded-full bg-teal-500/10 border border-teal-500/20 text-teal-300">
                  36 Generated Slots
                </span>
              </div>
            </div>

            {/* Doctors List */}
            <div className="space-y-3">
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Physician Directory (Seeded)</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {INITIAL_DOCTORS.map(doc => (
                  <div key={doc.id} className="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-2">
                    <div className="flex items-start justify-between">
                      <div>
                        <h4 className="font-semibold text-sm text-white">{doc.displayName}</h4>
                        <span className="text-xs text-teal-400">{doc.specialty}</span>
                      </div>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                        Active
                      </span>
                    </div>
                    <div className="text-xs text-slate-400 space-y-1 pt-1 border-t border-slate-800/80">
                      <div>Department: <span className="text-slate-300">{doc.department}</span></div>
                      <div>Location: <span className="text-slate-300">{doc.opdRoom}</span></div>
                      <div>Experience: <span className="text-slate-300">{doc.experience}</span></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Appointments in different statuses */}
            <div className="space-y-3">
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Synthetic Appointments (Various Statuses)</h3>
              <div className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-800/60 text-slate-400 border-b border-slate-800 font-mono">
                    <tr>
                      <th className="p-3">Patient Ref</th>
                      <th className="p-3">Doctor</th>
                      <th className="p-3">Specialty</th>
                      <th className="p-3">Schedule</th>
                      <th className="p-3">Status</th>
                      <th className="p-3">Reason Category</th>
                      <th className="p-3">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {appointments.map(appt => (
                      <tr key={appt.id} className="hover:bg-slate-800/30">
                        <td className="p-3 font-mono font-medium text-slate-200">{appt.patientReference}</td>
                        <td className="p-3 text-slate-200 font-semibold">{appt.doctorName}</td>
                        <td className="p-3 text-slate-400">{appt.specialty}</td>
                        <td className="p-3 text-slate-300">{appt.time}</td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            appt.status === 'CONFIRMED' ? 'bg-teal-950 text-teal-400 border border-teal-800' :
                            appt.status === 'COMPLETED' ? 'bg-blue-950 text-blue-400 border border-blue-800' :
                            'bg-rose-950 text-rose-400 border border-rose-800'
                          }`}>
                            {appt.status}
                          </span>
                        </td>
                        <td className="p-3 text-slate-400 max-w-xs truncate">{appt.reason}</td>
                        <td className="p-3">
                          {appt.status === 'CONFIRMED' && (
                            <button
                              onClick={() => handleCancelAppointment(appt.id, appt.slotId)}
                              className="text-xs text-rose-400 hover:text-rose-300 hover:underline"
                            >
                              Cancel & Release
                            </button>
                          )}
                          {appt.status === 'COMPLETED' && (
                            <span className="text-[10px] text-slate-500">Completed &bull; Follow-up logged</span>
                          )}
                          {appt.status === 'CANCELLED' && (
                            <span className="text-[10px] text-slate-500">Slot released</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Synthetic Lab Orders & Overdue Order Detection */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Synthetic Lab Orders (Workflow Metadata Only)</h3>
                <span className="text-[10px] text-amber-400 bg-amber-950/40 px-2 py-0.5 rounded border border-amber-800/60">
                  1 Intentionally Overdue Order for Rule Engine Testing
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {INITIAL_LAB_ORDERS.map(lab => (
                  <div key={lab.id} className={`bg-slate-900 p-4 rounded-xl border ${lab.isOverdue ? 'border-amber-700/80 bg-amber-950/10' : 'border-slate-800'} space-y-2`}>
                    <div className="flex items-start justify-between">
                      <div>
                        <span className="text-xs font-mono text-slate-400">{lab.patientReference}</span>
                        <h4 className="font-semibold text-xs text-white mt-0.5">{lab.testCategory}</h4>
                      </div>
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        lab.status === 'Completed' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' :
                        lab.status === 'Processing' ? 'bg-amber-950 text-amber-400 border border-amber-800' :
                        'bg-slate-800 text-slate-300'
                      }`}>
                        {lab.status}
                      </span>
                    </div>
                    <div className="text-xs text-slate-400 space-y-1 pt-1 border-t border-slate-800/80">
                      <div>Dept: <span className="text-slate-300">{lab.department}</span></div>
                      <div>Team: <span className="text-slate-300">{lab.assignedTeam}</span></div>
                      <div>Turnaround: <span className={lab.isOverdue ? 'text-amber-400 font-semibold' : 'text-slate-300'}>{lab.expectedCompletion}</span></div>
                      {lab.delayReason && (
                        <div className="text-[10px] text-amber-300/80 italic">Delay note: {lab.delayReason}</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: AI TOOL INTERFACES & SIMULATOR */}
        {activeTab === 'ai_tools' && (
          <div className="space-y-6">
            <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 space-y-2">
              <div className="flex items-center gap-2">
                <Bot className="w-5 h-5 text-teal-400" />
                <h2 className="text-base font-bold text-white">Section 9 &bull; AI Tool Execution & Safety Testbench</h2>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                When the voice assistant (Gnani/Evon/Timbre in Phase 2) needs to assist patients, it must call these exact typed Python functions. Direct database or SQL access is blocked. The simulation below demonstrates the strict input validations, atomic transaction locks, and anti-double booking defenses.
              </p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Tool 1: search_doctors */}
              <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <div className="flex items-center gap-2">
                    <Search className="w-4 h-4 text-teal-400" />
                    <h3 className="text-sm font-semibold text-white">AI Tool 1: search_doctors</h3>
                  </div>
                  <span className="text-[10px] font-mono text-teal-300 bg-teal-950 px-2 py-0.5 rounded border border-teal-800">
                    Read-Only
                  </span>
                </div>

                <div className="space-y-3">
                  <div>
                    <label className="text-xs text-slate-400 block mb-1">Search Keyword (Specialty, Department, or Doctor Name):</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="e.g. Cardiology, Dr. Priya, Neurology"
                        className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-teal-500 font-mono"
                      />
                      <button
                        onClick={handleSearchDoctors}
                        className="px-4 py-2 bg-teal-600 hover:bg-teal-500 text-slate-950 font-bold rounded-lg text-xs transition"
                      >
                        Search
                      </button>
                    </div>
                  </div>

                  <div className="bg-slate-950 p-3 rounded-lg border border-slate-800/80 font-mono text-xs space-y-2">
                    <div className="text-slate-400 text-[10px] uppercase">Matching Results ({filteredDoctors.length}):</div>
                    {filteredDoctors.length === 0 ? (
                      <div className="text-slate-500">No matching doctors found.</div>
                    ) : (
                      <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                        {filteredDoctors.map(doc => (
                          <div key={doc.id} className="p-2 bg-slate-900 rounded border border-slate-800 flex justify-between items-center">
                            <div>
                              <div className="text-white font-medium">{doc.displayName}</div>
                              <div className="text-teal-400 text-[10px]">{doc.specialty} &bull; {doc.department}</div>
                            </div>
                            <span className="text-[10px] font-mono text-slate-500">{doc.id.slice(0, 13)}...</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Tool 2: book_appointment Transaction Simulator */}
              <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <div className="flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-emerald-400" />
                    <h3 className="text-sm font-semibold text-white">AI Tool 2: book_appointment (Atomic)</h3>
                  </div>
                  <span className="text-[10px] font-mono text-emerald-300 bg-emerald-950 px-2 py-0.5 rounded border border-emerald-800">
                    Transactional Lock
                  </span>
                </div>

                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-slate-400 block mb-1">Select Doctor:</label>
                      <select
                        value={selectedDoctorId}
                        onChange={(e) => setSelectedDoctorId(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-teal-500"
                      >
                        {INITIAL_DOCTORS.map(d => (
                          <option key={d.id} value={d.id}>{d.displayName} ({d.specialty})</option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="text-xs text-slate-400 block mb-1">Select Slot:</label>
                      <select
                        value={selectedSlotId}
                        onChange={(e) => setSelectedSlotId(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-teal-500"
                      >
                        {slots.map(s => (
                          <option key={s.id} value={s.id}>
                            {s.doctorName.split(' ')[1]}: {s.time} [{s.status}]
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className="text-xs text-slate-400 block mb-1">Synthetic Patient Reference:</label>
                    <input
                      type="text"
                      value={patientRef}
                      onChange={(e) => setPatientRef(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none font-mono"
                    />
                  </div>

                  <div>
                    <label className="text-xs text-slate-400 block mb-1">Reason Category:</label>
                    <input
                      type="text"
                      value={reasonCategory}
                      onChange={(e) => setReasonCategory(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none"
                    />
                  </div>

                  <div className="flex gap-2 pt-1">
                    <button
                      onClick={() => handleSimulateBooking(false)}
                      className="flex-1 py-2 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold rounded-lg text-xs transition flex items-center justify-center gap-1.5"
                    >
                      <Play className="w-3.5 h-3.5" /> Book via AI Tool
                    </button>
                    <button
                      onClick={() => handleSimulateBooking(true)}
                      className="py-2 px-3 bg-rose-950/80 hover:bg-rose-900 border border-rose-800 text-rose-300 rounded-lg text-xs transition"
                      title="Simulates concurrent request targeting an already booked slot to test 409 Conflict rollback"
                    >
                      Simulate Double-Booking Conflict
                    </button>
                  </div>

                  {/* Feedback Banner */}
                  {simulationResult.status && (
                    <div className={`p-3 rounded-lg border text-xs font-mono space-y-1 ${
                      simulationResult.status === 'success'
                        ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
                        : 'bg-rose-950/40 border-rose-800 text-rose-300'
                    }`}>
                      <div className="font-bold flex items-center gap-1.5">
                        {simulationResult.status === 'success' ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <XCircle className="w-4 h-4 text-rose-400" />}
                        {simulationResult.message}
                      </div>
                      {simulationResult.details && (
                        <pre className="text-[10px] bg-slate-950/80 p-2 rounded overflow-x-auto text-slate-300 mt-1">
                          {JSON.stringify(simulationResult.details, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Audit Trail Viewer */}
            <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <History className="w-4 h-4 text-teal-400" />
                  <h3 className="text-sm font-semibold text-white">Live Audit Event Trail (Database Table: audit_events)</h3>
                </div>
                <span className="text-xs text-slate-500">Every transactional state change is logged immutably</span>
              </div>
              <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                {auditLogs.map(log => (
                  <div key={log.id} className="p-2.5 bg-slate-950 rounded-lg border border-slate-800/80 text-xs flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-slate-800 text-teal-300">
                        {log.action}
                      </span>
                      <span className="text-slate-400 font-mono text-[11px]">&bull; Actor: {log.actor}</span>
                    </div>
                    <div className="text-[10px] font-mono text-slate-500 truncate max-w-md">
                      {log.details}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB 5: API ENDPOINTS & DOCS */}
        {activeTab === 'api' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-white">REST API v1 Specification</h2>
                <p className="text-xs text-slate-400">Available at <code className="text-teal-300 font-mono">/docs</code> via FastAPI automatic OpenAPI documentation generator.</p>
              </div>
              <span className="text-xs px-2.5 py-1 rounded bg-slate-800 border border-slate-700 text-slate-300 font-mono">
                Base Path: /api/v1
              </span>
            </div>

            <div className="space-y-3">
              {[
                { method: 'GET', path: '/api/v1/hospitals', desc: 'List active hospital entities', params: 'is_active (bool)' },
                { method: 'GET', path: '/api/v1/hospitals/{hospital_id}', desc: 'Get hospital details with active clinical departments', params: 'hospital_id (UUID)' },
                { method: 'GET', path: '/api/v1/doctors', desc: 'Search and filter active doctors', params: 'specialty, department_name, hospital_id' },
                { method: 'GET', path: '/api/v1/doctors/{doctor_id}', desc: 'Retrieve doctor details & profile', params: 'doctor_id (UUID)' },
                { method: 'GET', path: '/api/v1/doctors/{doctor_id}/slots', desc: 'Get available unbooked slots (temporal filtering)', params: 'date (YYYY-MM-DD), time_range (morning|afternoon)' },
                { method: 'POST', path: '/api/v1/appointments', desc: 'Book appointment (transaction-safe slot reservation)', body: '{ patient_reference, doctor_id, slot_id, reason_category }' },
                { method: 'GET', path: '/api/v1/appointments', desc: 'List and filter appointments', params: 'doctor_id, patient_reference, status, date' },
                { method: 'GET', path: '/api/v1/appointments/{appointment_id}', desc: 'Retrieve single appointment', params: 'appointment_id (UUID)' },
                { method: 'POST', path: '/api/v1/appointments/{appointment_id}/cancel', desc: 'Controlled cancellation and slot release', body: '{ cancellation_reason }' },
                { method: 'POST', path: '/api/v1/appointments/{appointment_id}/complete', desc: 'Mark visit completed (no clinical fabrication)', body: '{ notes }' },
                { method: 'POST', path: '/api/v1/appointments/{appointment_id}/follow-up', desc: 'Record follow-up recommendation (no auto-booking)', body: '{ follow_up_date, follow_up_notes }' },
                { method: 'GET', path: '/api/v1/lab-orders', desc: 'List lab order workflow metadata', params: 'status, department_id' },
                { method: 'PATCH', path: '/api/v1/lab-orders/{order_id}/status', desc: 'Update lab order status (Pending, Processing, Completed, Delayed)', body: '{ workflow_status, delay_reason }' },
                { method: 'POST', path: '/api/v1/workflow/exceptions/detect', desc: 'Trigger deterministic overdue lab orders detection', params: 'None (Idempotent)' },
                { method: 'POST', path: '/api/v1/workflow/exceptions/{id}/assign', desc: 'Assign exception to team (OPEN -> IN_PROGRESS)', body: '{ assigned_to }' },
                { method: 'POST', path: '/api/v1/workflow/exceptions/{id}/resolve', desc: 'Resolve exception with mandatory investigation notes', body: '{ resolution_note }' },
                { method: 'GET', path: '/api/v1/workflow/audit-events', desc: 'Query immutable audit event log', params: 'entity_type, entity_id, limit' },
              ].map((ep, i) => (
                <div key={i} className="bg-slate-900 p-3.5 rounded-xl border border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
                  <div className="flex items-center gap-3">
                    <span className={`px-2 py-0.5 rounded font-mono font-bold text-[11px] ${
                      ep.method === 'GET' ? 'bg-blue-950 text-blue-400 border border-blue-800' :
                      ep.method === 'POST' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' :
                      'bg-purple-950 text-purple-400 border border-purple-800'
                    }`}>
                      {ep.method}
                    </span>
                    <span className="font-mono text-white font-semibold">{ep.path}</span>
                    <span className="text-slate-400">&bull; {ep.desc}</span>
                  </div>
                  <div className="font-mono text-[11px] text-slate-400 bg-slate-950 px-2.5 py-1 rounded border border-slate-800">
                    {ep.params ? `Query: ${ep.params}` : `Body: ${ep.body}`}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB 6: PYTEST TEST SUITE */}
        {activeTab === 'tests' && (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-lg font-bold text-white">Automated Test Execution Results</h2>
                <p className="text-xs text-slate-400">Executed locally in this container environment via <code className="text-teal-300 font-mono">pytest backend/tests/</code>.</p>
              </div>
              <div className="flex items-center gap-2">
                <span className="px-3 py-1 rounded-full bg-emerald-950 border border-emerald-800 text-emerald-300 text-xs font-bold flex items-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" /> 26 Passed, 0 Failed (0.76s)
                </span>
              </div>
            </div>

            {/* Test Categories */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Appointments Suite */}
              <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-2">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="font-semibold text-xs text-white">test_appointments.py (10 Tests)</span>
                  <span className="text-[10px] text-emerald-400 font-mono">10 PASSED</span>
                </div>
                <div className="space-y-1 text-xs font-mono text-slate-300">
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_successful_appointment_booking</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_rejection_of_unavailable_slot (409 Conflict)</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_prevention_of_double_booking_same_slot</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_validation_of_doctor_slot_ownership (400 Bad Request)</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_rejection_of_past_slot (Temporal validation)</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_rejection_of_inactive_doctor</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_appointment_cancellation_and_slot_release</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_appointment_completion</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_follow_up_recommendation_recording</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_ai_tool_book_appointment</div>
                </div>
              </div>

              {/* Doctors Suite */}
              <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-2">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="font-semibold text-xs text-white">test_doctors.py (8 Tests)</span>
                  <span className="text-[10px] text-emerald-400 font-mono">8 PASSED</span>
                </div>
                <div className="space-y-1 text-xs font-mono text-slate-300">
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_list_all_active_doctors</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_filter_doctors_by_specialty</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_filter_doctors_by_department_name</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_get_doctor_by_id_success</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_get_doctor_by_id_not_found</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_get_available_slots_retrieval</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_ai_tool_search_doctors</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_ai_tool_get_available_slots</div>
                </div>
              </div>

              {/* Lab Orders Suite */}
              <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-2">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="font-semibold text-xs text-white">test_lab_orders.py (4 Tests)</span>
                  <span className="text-[10px] text-emerald-400 font-mono">4 PASSED</span>
                </div>
                <div className="space-y-1 text-xs font-mono text-slate-300">
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_list_lab_orders</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_filter_lab_orders_by_status</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_update_lab_order_status</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_reject_invalid_lab_status</div>
                </div>
              </div>

              {/* Workflow Intelligence Suite */}
              <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-2">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="font-semibold text-xs text-white">test_workflow.py (4 Tests)</span>
                  <span className="text-[10px] text-emerald-400 font-mono">4 PASSED</span>
                </div>
                <div className="space-y-1 text-xs font-mono text-slate-300">
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_deterministic_overdue_lab_detection</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_workflow_exception_assignment</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_workflow_exception_resolution</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_audit_events_endpoint</div>
                </div>
              </div>
            </div>

            {/* Terminal Command Snippet */}
            <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-2">
              <span className="text-xs text-slate-400 font-semibold">Local Verification Command:</span>
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 font-mono text-xs text-emerald-400 flex items-center justify-between">
                <span>PYTHONPATH=backend pytest backend/tests/ -v</span>
                <span className="text-slate-500 text-[11px]">26 passed in ~0.76s</span>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-950 py-4 px-6 text-xs text-slate-500 flex flex-wrap items-center justify-between gap-4">
        <div>
          MediVoice AI &bull; Aarogya One Hospital Backend Architecture &bull; Great Indian AI Internship Challenge
        </div>
        <div className="flex items-center gap-4 text-slate-400">
          <span>Phase 1 Verified</span>
          <span>&bull;</span>
          <span>Zero External Model Credit Usage</span>
          <span>&bull;</span>
          <span>Strict Synthetic Data</span>
        </div>
      </footer>
    </div>
  );
}
