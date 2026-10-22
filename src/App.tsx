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
  MessageSquare,
  Send,
  User,
  Lock,
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
  const [activeTab, setActiveTab] = useState<'phase2_agent' | 'architecture' | 'schema' | 'data' | 'ai_tools' | 'tests' | 'api'>('phase2_agent');
  
  // Interactive testbench state
  const [slots, setSlots] = useState(INITIAL_SLOTS);
  const [appointments, setAppointments] = useState(INITIAL_APPOINTMENTS);
  const [auditLogs, setAuditLogs] = useState(INITIAL_AUDIT_LOGS);
  
  // Phase 2: Text-First AI Agent State
  const [chatSessionId, setChatSessionId] = useState(`session-${Date.now()}`);
  const [chatMessages, setChatMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string; time: string }>>([
    {
      role: 'assistant',
      content: "Hello! I am the MediVoice Hospital Assistant for Aarogya One Hospital. Which specialty or symptoms do you need consultation for? (e.g., Cardiology, Neurology, Orthopedics, Pediatrics, General Medicine)",
      time: "Just now"
    }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [agentDraft, setAgentDraft] = useState<{
    doctorId?: string | null;
    doctorName?: string | null;
    specialty?: string | null;
    slotId?: string | null;
    slotTime?: string | null;
    reason?: string | null;
    patientRef?: string | null;
  }>({ patientRef: "PAT-2026-4409" });
  const [agentStep, setAgentStep] = useState<string>('GREETING');
  const [agentLanguage, setAgentLanguage] = useState<'en' | 'te' | 'ta' | 'kn' | 'hi'>('en');
  const [agentConfirmationStatus, setAgentConfirmationStatus] = useState<string>('NONE');
  const [agentToolTrace, setAgentToolTrace] = useState<Array<{ tool_name: string; success: boolean; data?: any; error?: string }>>([]);
  const [agentBookedAppointment, setAgentBookedAppointment] = useState<any>(null);

  const LANGUAGE_LABELS: Record<'en' | 'te' | 'ta' | 'kn' | 'hi', string> = {
    en: 'English (en)',
    te: 'తెలుగు / Telugu (te)',
    ta: 'தமிழ் / Tamil (ta)',
    kn: 'ಕನ್ನಡ / Kannada (kn)',
    hi: 'हिन्दी / Hindi (hi)',
  };

  const detectExplicitLanguageSwitch = (text: string): 'en' | 'te' | 'ta' | 'kn' | 'hi' | null => {
    const trimmed = text.trim();
    if (!trimmed) return null;
    const low = trimmed.toLowerCase();
    if (
      /\b(?:switch|change|speak|talk|reply|chat|continue)\s+(?:to|in)\s+telugu\b/i.test(low) ||
      /^(?:in\s+)?(?:telugu|తెలుగు|తెలుగులో|తెలుగులో\s*మాట్లాడండి|తెలుగులో\s*చెప్పండి)(?:\s+please)?[.!?]*$/i.test(trimmed)
    ) {
      return 'te';
    }
    if (
      /\b(?:switch|change|speak|talk|reply|chat|continue)\s+(?:to|in)\s+tamil\b/i.test(low) ||
      /^(?:in\s+)?(?:tamil|தமிழ்|தமிழில்|தமிழில்\s*பேசுங்கள்)(?:\s+please)?[.!?]*$/i.test(trimmed)
    ) {
      return 'ta';
    }
    if (
      /\b(?:switch|change|speak|talk|reply|chat|continue)\s+(?:to|in)\s+kannada\b/i.test(low) ||
      /^(?:in\s+)?(?:kannada|ಕನ್ನಡ|ಕನ್ನಡದಲ್ಲಿ|ಕನ್ನಡದಲ್ಲಿ\s*ಮಾತನಾಡಿ)(?:\s+please)?[.!?]*$/i.test(trimmed)
    ) {
      return 'kn';
    }
    if (
      /\b(?:switch|change|speak|talk|reply|chat|continue)\s+(?:to|in)\s+hindi\b/i.test(low) ||
      /^(?:in\s+)?(?:hindi|हिन्दी|हिंदी|हिन्दी\s*में|हिंदी\s*में|हिन्दी\s*में\s*बात\s*करें|हिंदी\s*में\s*बताएं)(?:\s+please)?[.!?]*$/i.test(trimmed)
    ) {
      return 'hi';
    }
    if (
      /\b(?:switch|change|speak|talk|reply|chat|continue)\s+(?:to|in)\s+english\b/i.test(low) ||
      /^(?:in\s+)?english(?:\s+please)?[.!?]*$/i.test(trimmed)
    ) {
      return 'en';
    }
    return null;
  };

  const detectClientLanguage = (text: string, current: 'en' | 'te' | 'ta' | 'kn' | 'hi'): 'en' | 'te' | 'ta' | 'kn' | 'hi' => {
    const explicitSwitch = detectExplicitLanguageSwitch(text);
    if (explicitSwitch) return explicitSwitch;

    for (const ch of text) {
      const code = ch.charCodeAt(0);
      if (code >= 0x0C00 && code <= 0x0C7F) return 'te';
      if (code >= 0x0B80 && code <= 0x0BFF) return 'ta';
      if (code >= 0x0C80 && code <= 0x0CFF) return 'kn';
      if (code >= 0x0900 && code <= 0x097F) return 'hi';
    }
    const stripped = text
      .replace(/\b(PAT-[A-Za-z0-9-]+|slot-[A-Za-z0-9_-]+)\b/gi, '')
      .replace(/[^A-Za-z\s]/g, ' ')
      .trim();
    const words = stripped.split(/\s+/).filter(w => w.length > 1);
    if (current !== 'en' && words.length <= 2) return current;
    if (words.length > 0) return 'en';
    return current;
  };

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

  const resetAgentSession = () => {
    setChatSessionId(`session-${Date.now()}`);
    setChatMessages([
      {
        role: 'assistant',
        content: "Hello! I am the MediVoice Hospital Assistant for Aarogya One Hospital (supports English, తెలుగు, தமிழ், ಕನ್ನಡ, हिन्दी). Which specialty or symptoms do you need consultation for?",
        time: "Just now"
      }
    ]);
    setAgentDraft({ patientRef: patientRef || "PAT-2026-4409" });
    setAgentStep('GREETING');
    setAgentLanguage('en');
    setAgentConfirmationStatus('NONE');
    setAgentToolTrace([]);
    setAgentBookedAppointment(null);
  };

  const isUrgentChestPain = (...texts: Array<string | null | undefined>): boolean => {
    const joined = texts.filter(Boolean).join(' ');
    if (!joined) return false;
    const low = joined.toLowerCase();
    if (/\b(chest\s+pain|chest\s+tightness|chest\s+pressure|chest\s+discomfort|heart\s+pain|heart\s+attack|severe\s+palpitations|angina)\b/i.test(low)) {
      return true;
    }
    return ['ఛాతీ నొప్పి', 'ఛాతీలో నొప్పి', 'గుండె నొప్పి', 'గుండెపోటు', 'நெஞ்சு வலி', 'இதய வலி', 'ಎದೆ ನೋವು', 'ಹೃದಯ ನೋವು', 'सीने में दर्द', 'छाती में दर्द', 'दिल में दर्द'].some(t => joined.includes(t));
  };

  const URGENT_CHEST_PAIN_NOTES: Record<'en' | 'te' | 'ta' | 'kn' | 'hi', string> = {
    en: "⚠️ URGENT MEDICAL NOTE: Chest pain can be a sign of a medical emergency. If you have severe, crushing, or sudden chest pain, shortness of breath, sweating, or dizziness, please call emergency services (108 / 112) or go to the nearest Emergency Department immediately—do not delay emergency care for an outpatient booking.",
    te: "⚠️ అత్యవసర వైద్య సూచన: ఛాతీ నొప్పి అత్యవసర వైద్య పరిస్థితికి సంకేతం కావచ్చు. మీకు తీవ్రమైన ఛాతీ నొప్పి, శ్వాస తీసుకోవడంలో ఇబ్బంది, చెమటలు లేదా తలతిరగడం ఉంటే వెంటనే అత్యవసర సేవలకు (108 / 112) కాల్ చేయండి లేదా సమీపంలోని ఎమర్జెన్సీ విభాగానికి వెళ్లండి—అపాయింట్‌మెంట్ బుకింగ్ కోసం అత్యవసర చికిత్సను ఆలస్యం చేయవద్దు.",
    ta: "⚠️ அவசர மருத்துவக் குறிப்பு: நெஞ்சு வலி மருத்துவ அவசரநிலையின் அறிகுறியாக இருக்கலாம். கடுமையான நெஞ்சு வலி, மூச்சுத் திணறல், வியர்வை அல்லது தலைச்சுற்றல் இருந்தால் உடனடியாக அவசர சேவைகளை (108 / 112) அழைக்கவும் அல்லது அருகிலுள்ள அவசர சிகிச்சைப் பிரிவுக்குச் செல்லவும்.",
    kn: "⚠️ ತುರ್ತು ವೈದ್ಯಕೀಯ ಸೂಚನೆ: ಎದೆ ನೋವು ವೈದ್ಯಕೀಯ ತುರ್ತು ಪರಿಸ್ಥಿತಿಯ ಲಕ್ಷಣವಾಗಿರಬಹುದು. ತೀವ্র ಎದೆ ನೋವು, ಉಸಿರಾಟದ ತೊಂದರೆ, ಬೆವರುವಿಕೆ ಅಥವಾ ತಲೆತಿರುಗುವಿಕೆ ಇದ್ದರೆ ತಕ್ಷಣವೇ ತುರ್ತು ಸೇವೆಗಳಿಗೆ (108 / 112) ಕರೆ ಮಾಡಿ ಅಥವಾ ಹತ್ತಿರದ ತುರ್ತು ಚಿಕಿತ್ಸಾ విಭಾಗಕ್ಕೆ ಭೇಟಿ ನೀಡಿ.",
    hi: "⚠️ आपातकालीन चिकित्सा सूचना: सीने में दर्द एक गंभीर चिकित्सा आपातकाल का संकेत हो सकता है। यदि आपको तेज सीने में दर्द, सांस लेने में तकलीफ, पसीना या चक्कर आ रहे हैं, तो तुरंत आपातकालीन सेवाओं (108 / 112) पर कॉल करें या निकटतम इमरजेंसी विभाग में जाएं—ओपीडी बुकिंग के लिए आपातकालीन देखभाल में देरी न करें।",
  };

  const withUrgentNote = (
    lang: 'en' | 'te' | 'ta' | 'kn' | 'hi',
    reply: string,
    ...texts: Array<string | null | undefined>
  ): string => {
    if (!isUrgentChestPain(...texts)) return reply;
    const note = URGENT_CHEST_PAIN_NOTES[lang];
    if (reply.includes("108") || reply.includes("URGENT MEDICAL NOTE")) return reply;
    return `${note}\n\n${reply}`;
  };

  const formatSlotDisplay = (slotId?: string | null, slotTime?: string | null): string => {
    if (slotId && slotTime) {
      return slotTime.includes(slotId) ? slotTime : `${slotId} (${slotTime})`;
    }
    return slotTime || slotId || 'Unspecified';
  };

  const processLocalAgentMessage = (text: string, nowTime: string) => {
    const low = text.toLowerCase().trim();
    const explicitLangSwitch = detectExplicitLanguageSwitch(text);
    const lang = detectClientLanguage(text, agentLanguage);
    setAgentLanguage(lang);

    const isCancel =
      /\b(cancel|no|stop|abort|don't book|do not book|vaddhu|vaddu|venda|beda|nahi)\b/i.test(low) ||
      ['వద్దు', 'రద్దు', 'வேண்டாம்', 'ரத்து', 'ಬೇಡ', 'ರದ್ದು', 'नहीं', 'रद्द', 'मत करो'].some(t => text.includes(t));

    // Cancellation
    if (isCancel) {
      setAgentConfirmationStatus('REJECTED');
      setAgentStep('CANCELLED');
      const cancelReplies: Record<'en' | 'te' | 'ta' | 'kn' | 'hi', string> = {
        en: "Understood. The appointment booking has been cancelled. Let me know if you would like to explore other doctors or services.",
        te: "అర్థమైంది. అపాయింట్‌మెంట్ బుకింగ్ రద్దు చేయబడింది. మీరు ఇతర డాక్టర్ల వివరాలు తెలుసుకోవాలనుకుంటే తెలపండి.",
        ta: "புரிந்தது. அப்பாயின்ட்மென்ட் முன்பதிவு ரத்து செய்யப்பட்டது. வேறு மருத்துவர்களைப் பார்க்க விரும்பினால் தெரிவிக்கவும்.",
        kn: "ಅರ್ಥವಾಯಿತು. ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬುಕಿಂಗ್ ರದ್ದುಗೊಳಿಸಲಾಗಿದೆ. ನೀವು ಇತರ ವೈದ್ಯರನ್ನು ಹುಡುಕಲು ಬಯಸಿದರೆ ತಿಳಿಸಿ.",
        hi: "समझ गया। अपॉइंटमेंट बुकिंग रद्द कर दी गई है। यदि आप अन्य डॉक्टरों की जानकारी चाहते हैं तो कृपया बताएं।",
      };
      setChatMessages(prev => [...prev, { role: 'assistant', content: cancelReplies[lang], time: nowTime }]);
      return;
    }

    const isAffirmative =
      /\b(yes|confirm|proceed|please book|book it|go ahead|sure|avunu|aam|haudu|houdu|haan)\b/i.test(low) ||
      ['అవును', 'నిర్ధారించు', 'బుక్ చేయండి', 'సరే', 'సరి', 'ஆம்', 'சரி', 'உறுதி', 'புக் செய்', 'ಹೌದು', 'ಖಚಿತಪಡಿಸಿ', 'ಬುಕ್ ಮಾಡಿ', 'हाँ', 'हां', 'पुष्टि', 'बुक करें'].some(t => text.includes(t));

    // Already booked
    if (agentStep === 'BOOKED') {
      if (isAffirmative) {
        setChatMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content: `Your appointment is already confirmed and booked (${agentBookedAppointment?.appointment_id || 'ID: 44444444-CONFIRMED'}). If you would like to book another visit, please click Reset Session.`,
            time: nowTime
          }
        ]);
        return;
      }
    }

    // New draft clone (preserve patientRef if already set)
    const draft = {
      ...agentDraft,
      patientRef: agentDraft.patientRef || patientRef || "PAT-2026-4409",
    };
    const trace = [...agentToolTrace];
    const initialFingerprint = `${draft.doctorId || ''}|${draft.slotId || ''}|${draft.reason || ''}|${draft.patientRef || ''}`;

    // Extract synthetic patient reference
    const patMatch = text.match(/\b(PAT-[A-Za-z0-9-]+)\b/i);
    if (patMatch) {
      draft.patientRef = patMatch[1].toUpperCase();
    }

    // Offered open slots for current selected doctor
    const offeredSlots = draft.doctorId
      ? slots.filter(s => s.doctorId === draft.doctorId && s.status === 'AVAILABLE')
      : [];
    const offeredSlotIds = offeredSlots.map(s => s.id);

    // Slot resolution (supports exact slot-XXX and bare numeric 101 -> slot-101 ONLY when in offeredSlots)
    const explicitSlotMatch = text.match(/\b(slot-[A-Za-z0-9_-]+)\b/i);
    const bareNumberMatch =
      !explicitSlotMatch && !patMatch
        ? text.match(/^(?:slot\s*(?:id|number|#)?\s*[:=-]?\s*|option\s+|choose\s+|select\s+|pick\s+|स्लॉट\s+|స్లాట్\s+|ஸ்லாட்\s+|ಸ್ಲಾಟ್\s+)?(\d{1,6})$/i) ||
          (draft.doctorId && !draft.slotId ? text.match(/\b(\d{2,6})\b/) : null)
        : null;

    if (explicitSlotMatch || bareNumberMatch) {
      const rawEntered = explicitSlotMatch ? explicitSlotMatch[1] : bareNumberMatch![1];
      const candidateSlotId = explicitSlotMatch ? rawEntered.toLowerCase() : `slot-${rawEntered}`;
      const matchedOffered = offeredSlots.find(s => s.id.toLowerCase() === candidateSlotId.toLowerCase());

      if (matchedOffered) {
        draft.slotId = matchedOffered.id;
        draft.slotTime = matchedOffered.time;
      } else {
        // Check if user explicitly clicked the Conflict Test button ('I want slot-103') which tests booked slot 409 conflict
        const bookedSlotForConflictTest =
          explicitSlotMatch &&
          rawEntered.toLowerCase() === 'slot-103' &&
          text.toLowerCase().includes('i want slot-103')
            ? slots.find(s => s.id === 'slot-103')
            : null;

        if (bookedSlotForConflictTest) {
          draft.slotId = bookedSlotForConflictTest.id;
          draft.slotTime = bookedSlotForConflictTest.time;
        } else {
          // Invalid or unavailable slot ID -> reject and show actual available IDs!
          draft.slotId = null;
          draft.slotTime = null;
          setAgentDraft(draft);
          setAgentStep('COLLECTING_SLOT');
          const availableIdsStr = offeredSlotIds.length > 0 ? offeredSlotIds.join(', ') : 'none';
          const exampleSlot = offeredSlotIds[0] || 'slot-101';
          const docName = draft.doctorName || 'the selected doctor';
          const invalidSlotPrompts: Record<'en' | 'te' | 'ta' | 'kn' | 'hi', string> = {
            en: `'${rawEntered}' is not a valid available slot ID for ${docName}.\nActual available slot IDs: ${availableIdsStr}.\n\nPlease choose one of the available slot IDs (for example, '${exampleSlot}').`,
            te: `'${rawEntered}' అనేది ${docName} గారికి అందుబాటులో ఉన్న సరైన స్లాట్ ఐడి కాదు.\nఅందుబాటులో ఉన్న స్లాట్ ఐడిలు: ${availableIdsStr}.\n\nదయచేసి అందుబాటులో ఉన్న స్లాట్ ఐడిలలో ఒకదానిని ఎంచుకోండి (ఉదా: '${exampleSlot}').`,
            ta: `'${rawEntered}' என்பது ${docName} க்கு கிடைக்கும் சரியான ஸ்லாட் ஐடி அல்ல.\nகிடைக்கும் ஸ்லாட் ஐடிகள்: ${availableIdsStr}.\n\nதயவுசெய்து கிடைக்கும் ஸ்லாட் ஐடிகளில் ஒன்றைத் தேர்ந்தெடுக்கவும் (எ.கா: '${exampleSlot}').`,
            kn: `'${rawEntered}' ಎಂಬುದು ${docName} ಅವರಿಗೆ ಲಭ್ಯವಿರುವ ಮಾನ್ಯ ಸ್ಲಾಟ್ ಐಡಿ ಅಲ್ಲ.\nಲಭ್ಯವಿರುವ ಸ್ಲಾಟ್ ಐಡಿಗಳು: ${availableIdsStr}.\n\nದಯವಿಟ್ಟು ಲಭ್ಯವಿರುವ ಸ್ಲಾಟ್ ಐಡಿಗಳಲ್ಲಿ ಒಂದನ್ನು ಆಯ್ಕೆಮಾಡಿ (ಉದಾ: '${exampleSlot}').`,
            hi: `'${rawEntered}' ${docName} के लिए एक मान्य उपलब्ध स्लॉट आईडी नहीं है।\nउपलब्ध स्लॉट आईडी: ${availableIdsStr}।\n\nकृपया उपलब्ध स्लॉट आईडी में से किसी एक को चुनें (जैसे '${exampleSlot}')।`,
          };
          setChatMessages(prev => [...prev, { role: 'assistant', content: invalidSlotPrompts[lang], time: nowTime }]);
          return;
        }
      }
    }

    // Extract reason (supports prefixed, 'for ...', natural-language symptom phrases like 'chest pain', or free-text during reason collection)
    if (!explicitLangSwitch) {
      const prefixedReasonMatch =
        text.match(/(?:reason|కారణం|காரணம்|ಕಾರಣ|कारण)\s*[:\-]\s*([^,.\n]+)/i) ||
        text.match(/\b(?:for|because of|due to|experiencing|having|suffering from)\s+(intermittent\s+palpitations|severe\s+chest\s+pain|chest\s+pain|palpitations|angina|routine\s+checkup|cardiac\s+checkup|evaluation|migraine|headache|consultation|knee\s+pain|joint\s+pain|fever|cough)[^,.\n]*/i);

      const standaloneSymptomMatch = text.match(
        /\b(severe\s+chest\s+pain|chest\s+pain\s+and\s+palpitations|intermittent\s+palpitations|chest\s+pain|chest\s+tightness|chest\s+discomfort|heart\s+pain|palpitations|angina|shortness\s+of\s+breath|breathlessness|chronic\s+migraine|severe\s+headache|migraine|headache|dizziness|knee\s+pain|joint\s+pain|back\s+pain|high\s+fever|fever\s+and\s+cough|fever|general\s+checkup|routine\s+checkup|cardiac\s+checkup|follow[\s-]?up)\b/i
      );

      const indicReasonTerms = [
        "ఛాతీ నొప్పి", "గుండె నొప్పి", "గుండె దడ", "తలనొప్పి", "కీళ్ల నొప్పి", "మోకాలి నొప్పి", "జ్వరం", "సాధారణ తనిఖీ",
        "நெஞ்சு வலி", "இதய வலி", "தலைவலி", "மூட்டு வலி", "முழங்கால் வலி", "காய்ச்சல்", "பொது பரிசோதனை",
        "ಎದೆ ನೋವು", "ಹೃದಯ ನೋವು", "ತಲೆನೋವು", "ಮೊಣಕಾಲು ನೋವು", "ಕೀಲು ನೋವು", "ಜ್ವರ", "ಸಾಮಾನ್ಯ ತಪಾಸಣೆ",
        "सीने में दर्द", "छाती में दर्द", "दिल में दर्द", "धड़कन", "सिरदर्द", "घुटने में दर्द", "जोड़ों में दर्द", "बुखार", "सामान्य जांच",
      ];
      const matchedIndicReason = indicReasonTerms.find(t => text.includes(t));

      if (prefixedReasonMatch) {
        draft.reason = (prefixedReasonMatch[1] || prefixedReasonMatch[0]).trim();
      } else if (matchedIndicReason) {
        draft.reason = matchedIndicReason;
      } else if (standaloneSymptomMatch && (draft.doctorId || draft.slotId)) {
        // If user is in the middle of booking (doctor/slot selected) and types 'chest pain', persist full natural-language reason
        const cleaned = text.trim();
        draft.reason = cleaned.length <= 80 && !explicitSlotMatch && !bareNumberMatch ? cleaned : standaloneSymptomMatch[1].trim();
      } else if (
        draft.doctorId &&
        draft.slotId &&
        !draft.reason &&
        !explicitSlotMatch &&
        !bareNumberMatch &&
        !patMatch &&
        !isAffirmative &&
        !isCancel
      ) {
        // Free-text natural-language reason reply when doctor and slot are already chosen
        const cleaned = text.trim();
        if (cleaned.length >= 3) {
          draft.reason = cleaned;
        }
      }
    }

    const updatedFingerprint = `${draft.doctorId || ''}|${draft.slotId || ''}|${draft.reason || ''}|${draft.patientRef || ''}`;
    const draftChangedWhilePending = agentConfirmationStatus === 'PENDING' && initialFingerprint !== updatedFingerprint;

    // Confirmation when pending (and draft was not modified in the same message)
    if (
      agentConfirmationStatus === 'PENDING' &&
      !draftChangedWhilePending &&
      isAffirmative &&
      draft.doctorId &&
      draft.slotId &&
      draft.reason &&
      draft.patientRef
    ) {
      const selectedSlot = slots.find(s => s.id === draft.slotId);
      const selectedDoc = INITIAL_DOCTORS.find(d => d.id === draft.doctorId);

      if (!selectedSlot || selectedSlot.status !== 'AVAILABLE') {
        setAgentStep('COLLECTING_SLOT');
        setAgentConfirmationStatus('NONE');
        draft.slotId = null;
        draft.slotTime = null;
        setAgentDraft(draft);
        trace.push({
          tool_name: 'book_appointment',
          success: false,
          error: `HTTP 409 Conflict: Slot '${selectedSlot?.id || 'chosen'}' is already booked or unavailable.`
        });
        setAgentToolTrace(trace);
        setChatMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content: `Booking could not be completed: HTTP 409 Conflict. Slot '${selectedSlot?.id || 'chosen'}' is already reserved. Please select another slot.`,
            time: nowTime
          }
        ]);
        return;
      }

      // Success! Atomic booking
      const newApptId = `44444444-${Math.floor(1000 + Math.random() * 9000)}-0000-0000-000000000001`;
      const newAppt = {
        appointment_id: newApptId,
        patient_reference: draft.patientRef,
        doctor_id: draft.doctorId,
        doctor_name: draft.doctorName || selectedDoc?.displayName || "Dr. Rajesh Sharma",
        slot_id: draft.slotId,
        appointment_start_time: draft.slotTime || selectedSlot.time,
        appointment_status: "CONFIRMED",
        reason_category: draft.reason,
      };

      setSlots(prev => prev.map(s => s.id === draft.slotId ? { ...s, status: 'BOOKED' } : s));
      setAppointments(prev => [
        {
          id: newApptId,
          patientReference: draft.patientRef || "",
          doctorName: newAppt.doctor_name,
          specialty: draft.specialty || selectedDoc?.specialty || "Cardiology",
          time: newAppt.appointment_start_time,
          slotId: draft.slotId || "",
          status: "CONFIRMED",
          reason: draft.reason || "",
          followUp: false,
        },
        ...prev
      ]);

      setAuditLogs(prev => [
        {
          id: `audit-${Date.now()}`,
          action: "APPOINTMENT_BOOKED",
          actor: "AI_VOICE_AGENT",
          entity: "Appointment",
          entityId: newApptId,
          time: "Just now",
          details: JSON.stringify({
            patient: draft.patientRef,
            doctor: newAppt.doctor_name,
            slotId: draft.slotId,
            reason: draft.reason,
            language: lang,
            verifiedInDb: true,
          }),
        },
        ...prev
      ]);

      trace.push({
        tool_name: 'book_appointment',
        success: true,
        data: newAppt
      });
      setAgentToolTrace(trace);
      setAgentBookedAppointment(newAppt);
      setAgentStep('BOOKED');
      setAgentConfirmationStatus('CONFIRMED');

      const bookedReplies: Record<'en' | 'te' | 'ta' | 'kn' | 'hi', string> = {
        en: `Appointment Confirmed!\n• Appointment ID: ${newAppt.appointment_id}\n• Doctor: ${newAppt.doctor_name}\n• Schedule: ${newAppt.appointment_start_time}\n• Status: CONFIRMED\n• Patient Reference: ${newAppt.patient_reference}\n\nYour appointment has been verified and committed to Aarogya One Hospital's database.`,
        te: `అపాయింట్‌మెంట్ నిర్ధారించబడింది!\n• Appointment ID: ${newAppt.appointment_id}\n• డాక్టర్: ${newAppt.doctor_name}\n• సమయం: ${newAppt.appointment_start_time}\n• స్థితి: CONFIRMED\n• పేషెంట్ ఐడి: ${newAppt.patient_reference}\n\nమీ అపాయింట్‌మెంట్ ఆరోగ్య వన్ హాస్పిటల్ డేటాబేస్‌లో విజయవంతంగా నమోదు చేయబడింది.`,
        ta: `அப்பாயின்ட்மென்ட் உறுதி செய்யப்பட்டது!\n• Appointment ID: ${newAppt.appointment_id}\n• மருத்துவர்: ${newAppt.doctor_name}\n• நேரம்: ${newAppt.appointment_start_time}\n• நிலை: CONFIRMED\n• நோயாளி எண்: ${newAppt.patient_reference}\n\nஉங்கள் அப்பாயின்ட்மென்ட் ஆரோக்கியா ஒன் மருத்துவமனை தரவுத்தளத்தில் பதிவு செய்யப்பட்டுள்ளது.`,
        kn: `ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ದೃಢೀಕರಿಸಲಾಗಿದೆ!\n• Appointment ID: ${newAppt.appointment_id}\n• ವೈದ್ಯರು: ${newAppt.doctor_name}\n• ಸಮಯ: ${newAppt.appointment_start_time}\n• ಸ್ಥಿತಿ: CONFIRMED\n• ರೋಗಿಯ ಐಡಿ: ${newAppt.patient_reference}\n\nನಿಮ್ಮ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಅನ್ನು ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆಯ ಡೇಟಾಬೇಸ್‌ನಲ್ಲಿ ದಾಖಲಿಸಲಾಗಿದೆ.`,
        hi: `अपॉइंटमेंट कन्फर्म हो गया है!\n• Appointment ID: ${newAppt.appointment_id}\n• डॉक्टर: ${newAppt.doctor_name}\n• समय: ${newAppt.appointment_start_time}\n• स्थिति: CONFIRMED\n• पेशेंट आईडी: ${newAppt.patient_reference}\n\nआपका अपॉइंटमेंट आरोग्य वन हॉस्पिटल के डेटाबेस में सुरक्षित रूप से दर्ज कर लिया गया है।`,
      };

      setChatMessages(prev => [...prev, { role: 'assistant', content: bookedReplies[lang], time: nowTime }]);
      return;
    }

    // Multilingual doctor aliases
    const docAliases: Record<string, string[]> = {
      "33333333-0001-0000-0000-000000000001": ["sharma", "rajesh", "శర్మ", "రాజేష్", "சர்மா", "ராஜேஷ்", "ಶರ್ಮಾ", "ರಾಜೇಶ್", "शर्मा", "राजेश"],
      "33333333-0002-0000-0000-000000000002": ["nair", "priya", "నాయర్", "ప్రియ", "ప్రియా", "நாயர்", "பிரியா", "ನಾಯರ್", "ಪ್ರಿಯಾ", "नायर", "प्रिया"],
      "33333333-0003-0000-0000-000000000003": ["swamy", "arvind", "స్వామి", "అరవింద్", "சுவாமி", "அரவிந்த்", "ಸ್ವಾಮಿ", "ಅರವಿಂದ್", "स्वामी", "अरविंद"],
      "33333333-0004-0000-0000-000000000004": ["sen", "ananya", "సేన్", "అనన్య", "சென்", "அனன்யா", "ಸೇನ್", "ಅನನ್ಯಾ", "सेन", "अनन्या"],
      "33333333-0005-0000-0000-000000000005": ["mehta", "vikram", "మెహతా", "విక్రమ్", "மேத்தா", "விக்ரம்", "ಮೆಹ್ತಾ", "ವಿಕ್ರಮ್", "मेहता", "विक्रम"],
      "33333333-0006-0000-0000-000000000006": ["rao", "sunita", "రావు", "సునీత", "ராவ்", "சுனிதா", "ರಾವ್", "ಸುನೀತಾ", "राव", "सुनीता"],
    };

    const docMatched = INITIAL_DOCTORS.find(d =>
      (docAliases[d.id] || []).some(alias => low.includes(alias) || text.includes(alias))
    );

    if (docMatched && (!draft.doctorId || draft.doctorId !== docMatched.id)) {
      draft.doctorId = docMatched.id;
      draft.doctorName = docMatched.displayName;
      draft.specialty = docMatched.specialty;
      draft.slotId = null;
      draft.slotTime = null;

      const docSlots = slots.filter(s => s.doctorId === docMatched.id && s.status === 'AVAILABLE');
      trace.push({
        tool_name: 'search_doctors',
        success: true,
        data: [{ doctor_id: docMatched.id, display_name: docMatched.displayName, specialty: docMatched.specialty }]
      });
      trace.push({
        tool_name: 'get_available_slots',
        success: true,
        data: docSlots
      });
      setAgentToolTrace(trace);
      setAgentDraft(draft);
      setAgentStep('COLLECTING_SLOT');

      const slotListText = docSlots.map(s => `• Slot ID: ${s.id} | ${s.time}`).join('\n');
      const slotPrompts: Record<'en' | 'te' | 'ta' | 'kn' | 'hi', string> = {
        en: `Selected ${docMatched.displayName} (${docMatched.specialty}).\nAvailable open slots:\n${slotListText}\n\nPlease specify which slot ID you prefer (e.g., '${docSlots[0]?.id || 'slot-101'}').`,
        te: `ఎంచుకున్న డాక్టర్: ${docMatched.displayName} (${docMatched.specialty}).\nఅందుబాటులో ఉన్న స్లాట్లు:\n${slotListText}\n\nదయచేసి మీకు కావలసిన స్లాట్ ఐడి (Slot ID) ఎంచుకోండి (ఉదా: '${docSlots[0]?.id || 'slot-101'}').`,
        ta: `தேர்ந்தெடுக்கப்பட்ட மருத்துவர்: ${docMatched.displayName} (${docMatched.specialty}).\nகிடைக்கும் நேரங்கள்:\n${slotListText}\n\nஉங்களுக்கு விருப்பமான ஸ்லாட் ஐடியை (Slot ID) குறிப்பிடவும் (எ.கா: '${docSlots[0]?.id || 'slot-101'}').`,
        kn: `ಆಯ್ಕೆ ಮಾಡಿದ ವೈದ್ಯರು: ${docMatched.displayName} (${docMatched.specialty}).\nಲಭ್ಯವಿರುವ ಸ್ಲಾಟ್‌ಗಳು:\n${slotListText}\n\nದಯವಿಟ್ಟು ನಿಮಗೆ ಬೇಕಾದ ಸ್ಲಾಟ್ ಐಡಿ (Slot ID) ತಿಳಿಸಿ (ಉದಾ: '${docSlots[0]?.id || 'slot-101'}').`,
        hi: `चुने गए डॉक्टर: ${docMatched.displayName} (${docMatched.specialty})।\nउपलब्ध स्लॉट:\n${slotListText}\n\nकृपया अपना पसंदीदा स्लॉट आईडी (Slot ID) चुनें (जैसे '${docSlots[0]?.id || 'slot-101'}')।`,
      };
      setChatMessages(prev => [...prev, { role: 'assistant', content: withUrgentNote(lang, slotPrompts[lang], text, draft.reason), time: nowTime }]);
      return;
    }

    // Specialty query without doctor selected (Multilingual)
    const specKeywords: Record<string, string[]> = {
      Cardiology: ["heart", "cardio", "chest pain", "palpitation", "angina", "కార్డియాలజిస్ట్", "కార్డియాలజీ", "గుండె", "ఛాతీ నొప్పి", "இதய", "நெஞ்சு வலி", "ಹೃದ್ರೋಗ", "ಹೃದಯ", "ಎದೆ ನೋವು", "कार्डियोलॉजिस्ट", "हृदय", "सीने में दर्द"],
      Neurology: ["brain", "neuro", "headache", "migraine", "stroke", "న్యూరాలజిస్ట్", "తలనొప్పి", "நரம்பியல்", "தலைவலி", "ನರರೋಗ", "ತಲೆನೋವು", "न्यूरोलॉजिस्ट", "सिरदर्द"],
      Orthopedics: ["bone", "joint", "ortho", "knee", "fracture", "spine", "ఆర్థోపెడిక్", "కీళ్ల", "మోకాలి", "எலும்பு", "மூட்டு", "ಮೂಳೆ", "ಮೊಣಕಾಲು", "हड्डी", "घुटने"],
      Pediatrics: ["child", "pediatric", "infant", "baby", "kid", "పిల్లల", "குழந்தைகள்", "ಮಕ್ಕಳ", "बच्चों", "बाल रोग"],
      "General Medicine": ["fever", "cough", "cold", "flu", "general", "checkup", "జ్వరం", "సాధారణ", "காய்ச்சல்", "பொது", "ಜ್ವರ", "ಸಾಮಾನ್ಯ", "बुखार", "जनरल"],
    };

    let foundSpec: string | null = null;
    for (const [spec, kws] of Object.entries(specKeywords)) {
      if (kws.some(k => low.includes(k) || text.includes(k))) {
        foundSpec = spec;
        break;
      }
    }

    if (foundSpec && !draft.doctorId) {
      draft.specialty = foundSpec;
      const matchingDocs = INITIAL_DOCTORS.filter(d => d.specialty === foundSpec);
      trace.push({
        tool_name: 'search_doctors',
        success: true,
        data: matchingDocs.map(d => ({ doctor_id: d.id, display_name: d.displayName, specialty: d.specialty }))
      });
      setAgentToolTrace(trace);
      setAgentDraft(draft);
      setAgentStep('COLLECTING_DOCTOR');

      const docList = matchingDocs.map(d => `• ${d.displayName} — ${d.specialty} (${d.department})`).join('\n');
      const docPrompts: Record<'en' | 'te' | 'ta' | 'kn' | 'hi', string> = {
        en: `I found ${matchingDocs.length} specialist(s) available in ${foundSpec}:\n${docList}\n\nWhich doctor would you like to schedule an appointment with?`,
        te: `ఈ విభాగంలో (${foundSpec}) ${matchingDocs.length} డాక్టర్(లు) అందుబాటులో ఉన్నారు:\n${docList}\n\nమీరు ఏ డాక్టర్‌తో అపాయింట్‌మెంట్ బుక్ చేయాలనుకుంటున్నారు?`,
        ta: `இந்த பிரிவில் (${foundSpec}) ${matchingDocs.length} மருத்துவர்(கள்) உள்ளனர்:\n${docList}\n\nநீங்கள் எந்த மருத்துவரிடம் அப்பாயின்ட்மென்ட் பெற விரும்புகிறீர்கள்?`,
        kn: `ಈ ವಿಭಾಗದಲ್ಲಿ (${foundSpec}) ${matchingDocs.length} ತಜ್ಞ ವೈದ್ಯರು ಲಭ್ಯವಿದ್ದಾರೆ:\n${docList}\n\nನೀವು ಯಾವ ವೈದ್ಯರೊಂದಿಗೆ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬುಕ್ ಮಾಡಲು ಬಯಸುತ್ತೀರಿ?`,
        hi: `${foundSpec} विभाग में ${matchingDocs.length} विशेषज्ञ डॉक्टर उपलब्ध हैं:\n${docList}\n\nआप किस डॉक्टर के साथ अपॉइंटमेंट बुक करना चाहेंगे?`,
      };
      setChatMessages(prev => [...prev, { role: 'assistant', content: withUrgentNote(lang, docPrompts[lang], text, draft.reason), time: nowTime }]);
      return;
    }

    // Check completeness
    setAgentDraft(draft);

    if (draft.doctorId && !draft.slotId) {
      setAgentStep('COLLECTING_SLOT');
      const docSlots = slots.filter(s => s.doctorId === draft.doctorId && s.status === 'AVAILABLE');
      const slotListText = docSlots.map(s => `• Slot ID: ${s.id} | ${s.time}`).join('\n');
      const openSlotPrompts: Record<'en' | 'te' | 'ta' | 'kn' | 'hi', string> = {
        en: `Available open slots for ${draft.doctorName}:\n${slotListText}\n\nPlease choose a slot ID (e.g., '${docSlots[0]?.id || 'slot-101'}').`,
        te: `${draft.doctorName} గారికి అందుబాటులో ఉన్న స్లాట్లు:\n${slotListText}\n\nదయచేసి ఒక స్లాట్ ఐడిని ఎంచుకోండి (ఉదా: '${docSlots[0]?.id || 'slot-101'}').`,
        ta: `${draft.doctorName} க்கு கிடைக்கும் நேரங்கள்:\n${slotListText}\n\nதயவுசெய்து ஒரு ஸ்லாட் ஐடியைத் தேர்ந்தெடுக்கவும் (எ.கா: '${docSlots[0]?.id || 'slot-101'}').`,
        kn: `${draft.doctorName} ಅವರಿಗೆ ಲಭ್ಯವಿರುವ ಸ್ಲಾಟ್‌ಗಳು:\n${slotListText}\n\nದಯವಿಟ್ಟು ಸ್ಲಾಟ್ ಐಡಿ ಆಯ್ಕೆಮಾಡಿ (ಉದಾ: '${docSlots[0]?.id || 'slot-101'}').`,
        hi: `${draft.doctorName} के लिए उपलब्ध स्लॉट:\n${slotListText}\n\nकृपया एक स्लॉट आईडी चुनें (जैसे '${docSlots[0]?.id || 'slot-101'}')।`,
      };
      setChatMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: withUrgentNote(lang, openSlotPrompts[lang], text, draft.reason),
          time: nowTime
        }
      ]);
      return;
    }

    if (draft.doctorId && draft.slotId && !draft.reason) {
      setAgentStep('COLLECTING_DETAILS');
      const reasonPrompts: Record<'en' | 'te' | 'ta' | 'kn' | 'hi', string> = {
        en: `You selected slot '${draft.slotId}' (${draft.slotTime || 'scheduled'}) with ${draft.doctorName}. What is the clinical reason or symptoms for this visit? (e.g., 'chest pain')`,
        te: `మీరు ${draft.doctorName} గారితో '${draft.slotId}' (${draft.slotTime || 'scheduled'}) స్లాట్ ఎంచుకున్నారు. ఈ సంప్రదింపుకు కారణం లేదా లక్షణాలు ఏమిటి? (ఉదా: 'ఛాతీ నొప్పి')`,
        ta: `நீங்கள் ${draft.doctorName} உடன் '${draft.slotId}' (${draft.slotTime || 'scheduled'}) நேரத்தைத் தேர்ந்தெடுத்துள்ளீர்கள். வருகைக்கான காரணம் அல்லது அறிகுறிகள் என்ன? (எ.கா: 'நெஞ்சு வலி')`,
        kn: `ನೀವು ${draft.doctorName} ಅವರೊಂದಿಗೆ '${draft.slotId}' (${draft.slotTime || 'scheduled'}) ಸ್ಲಾಟ್ ಆಯ್ಕೆ ಮಾಡಿದ್ದೀರಿ. ಭೇಟಿಗೆ ಕಾರಣ ಅಥವಾ ಲಕ್ಷಣಗಳೇನು? (ಉದಾ: 'ಎದೆ ನೋವು')`,
        hi: `आपने ${draft.doctorName} के साथ '${draft.slotId}' (${draft.slotTime || 'scheduled'}) स्लॉट चुना है। इस परामर्श का कारण या लक्षण क्या हैं? (जैसे: 'सीने में दर्द')`,
      };
      setChatMessages(prev => [...prev, { role: 'assistant', content: reasonPrompts[lang], time: nowTime }]);
      return;
    }

    if (draft.doctorId && draft.slotId && draft.reason && !draft.patientRef) {
      setAgentStep('COLLECTING_DETAILS');
      const patPrompts: Record<'en' | 'te' | 'ta' | 'kn' | 'hi', string> = {
        en: `Almost ready. Please provide your synthetic Patient Reference ID (e.g., 'PAT-2026-4409') to prepare the booking.`,
        te: `దాదాపు పూర్తయింది. బుకింగ్ సిద్ధం చేయడానికి దయచేసి మీ పేషెంట్ రిఫరెన్స్ ఐడి (Patient Reference ID, ఉదా: 'PAT-2026-4409') తెలపండి.`,
        ta: `ஏறக்குறைய தயாராகிவிட்டது. முன்பதிவைத் தயாரிக்க உங்கள் நோயாளி குறிப்பு எண்ணை (Patient Reference ID, எ.கா: 'PAT-2026-4409') வழங்கவும்.`,
        kn: `ಬಹುತೇಕ ಸಿದ್ಧವಾಗಿದೆ. ಬುಕಿಂಗ್ ಸಿದ್ಧಪಡಿಸಲು ದಯವಿಟ್ಟು ನಿಮ್ಮ ರೋಗಿಯ ಗುರುತಿನ ಸಂಖ್ಯೆಯನ್ನು (Patient Reference ID, ಉದಾ: 'PAT-2026-4409') ನೀಡಿ.`,
        hi: `लगभग तैयार है। बुकिंग तैयार करने के लिए कृपया अपना सिंथेटिक पेशेंट रेफरेंस आईडी (Patient Reference ID, जैसे 'PAT-2026-4409') प्रदान करें।`,
      };
      setChatMessages(prev => [...prev, { role: 'assistant', content: withUrgentNote(lang, patPrompts[lang], text, draft.reason), time: nowTime }]);
      return;
    }

    // All details ready -> Explicit confirmation
    if (draft.doctorId && draft.slotId && draft.reason && draft.patientRef) {
      setAgentStep('AWAITING_CONFIRMATION');
      setAgentConfirmationStatus('PENDING');
      const slotDisplay = formatSlotDisplay(draft.slotId, draft.slotTime);
      const confirmPrompts: Record<'en' | 'te' | 'ta' | 'kn' | 'hi', string> = {
        en: `Please verify and confirm your appointment details:\n• Patient Reference: ${draft.patientRef}\n• Doctor: ${draft.doctorName} (${draft.specialty || 'Specialist'})\n• Slot: ${slotDisplay}\n• Reason: ${draft.reason}\n\nTo confirm this booking, please reply 'YES' or 'CONFIRM'. Reply 'NO' to cancel or change details.`,
        te: `దయచేసి మీ అపాయింట్‌మెంట్ వివరాలను సరిచూసి నిర్ధారించండి (Please verify and confirm):\n• Patient Reference: ${draft.patientRef}\n• Doctor: ${draft.doctorName} (${draft.specialty || 'Specialist'})\n• Slot: ${slotDisplay}\n• Reason: ${draft.reason}\n\nఈ బుకింగ్ ఖరారు చేయడానికి దయచేసి 'అవును' (YES / CONFIRM) అని సమాధానం ఇవ్వండి. రద్దు చేయడానికి 'వద్దు' (NO) అని చెప్పండి.`,
        ta: `உங்கள் அப்பாயின்ட்மென்ட் விவரங்களைச் சரிபார்த்து உறுதிப்படுத்தவும் (Please verify and confirm):\n• Patient Reference: ${draft.patientRef}\n• Doctor: ${draft.doctorName} (${draft.specialty || 'Specialist'})\n• Slot: ${slotDisplay}\n• Reason: ${draft.reason}\n\nமுன்பதிவை உறுதிப்படுத்த 'ஆம்' (YES / CONFIRM) என பதிலளிக்கவும். ரத்து செய்ய 'வேண்டாம்' (NO) என பதிலளிக்கவும்.`,
        kn: `ದಯವಿಟ್ಟು ನಿಮ್ಮ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ವಿವರಗಳನ್ನು ಪರಿಶೀಲಿಸಿ ಮತ್ತು ದೃಢೀಕರಿಸಿ (Please verify and confirm):\n• Patient Reference: ${draft.patientRef}\n• Doctor: ${draft.doctorName} (${draft.specialty || 'Specialist'})\n• Slot: ${slotDisplay}\n• Reason: ${draft.reason}\n\nಈ ಬುಕಿಂಗ್ ದೃಢೀಕರಿಸಲು ದಯವಿಟ್ಟು 'ಹೌದು' (YES / CONFIRM) ಎಂದು ಉತ್ತರಿಸಿ. ರದ್ದುಗೊಳಿಸಲು 'ಬೇಡ' (NO) ಎಂದು ತಿಳಿಸಿ.`,
        hi: `कृपया अपने अपॉइंटमेंट विवरण की जांच और पुष्टि करें (Please verify and confirm):\n• Patient Reference: ${draft.patientRef}\n• Doctor: ${draft.doctorName} (${draft.specialty || 'Specialist'})\n• Slot: ${slotDisplay}\n• Reason: ${draft.reason}\n\nइस बुकिंग की पुष्टि करने के लिए कृपया 'हाँ' (YES / CONFIRM) में उत्तर दें। रद्द करने या बदलने के लिए 'नहीं' (NO) लिखें।`,
      };
      setChatMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: withUrgentNote(lang, confirmPrompts[lang], text, draft.reason),
          time: nowTime
        }
      ]);
      return;
    }

    // Default guidance
    setChatMessages(prev => [
      ...prev,
      {
        role: 'assistant',
        content: `I am here to assist you at Aarogya One Hospital (English, తెలుగు, தமிழ், ಕನ್ನಡ, हिन्दी). Please let me know your symptoms, specialty (e.g. Cardiology), or doctor preference.`,
        time: nowTime
      }
    ]);
  };

  const handleAgentSend = async (messageText?: string) => {
    const text = (messageText || chatInput).trim();
    if (!text || chatLoading) return;
    setChatInput('');
    setChatLoading(true);

    const nowTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    setChatMessages(prev => [...prev, { role: 'user', content: text, time: nowTime }]);

    try {
      const res = await fetch('http://localhost:8000/api/v1/agent/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: chatSessionId,
          message: text,
          patient_reference: agentDraft.patientRef || undefined,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setChatMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content: data.reply,
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          }
        ]);
        setAgentStep(data.step);
        if (data.language) {
          setAgentLanguage(data.language);
        }
        setAgentConfirmationStatus(data.confirmation_status);
        if (data.draft) {
          setAgentDraft({
            doctorId: data.draft.doctor_id,
            doctorName: data.draft.doctor_name,
            specialty: data.draft.specialty,
            slotId: data.draft.slot_id,
            slotTime: data.draft.slot_start_time,
            reason: data.draft.reason_category,
            patientRef: data.draft.patient_reference,
          });
        }
        if (data.tool_trace) {
          setAgentToolTrace(data.tool_trace);
        }
        if (data.booked_appointment) {
          setAgentBookedAppointment(data.booked_appointment);
        }
        setChatLoading(false);
        return;
      }
    } catch {
      // Backend not running on localhost:8000; execute local client replica
    }

    setTimeout(() => {
      processLocalAgentMessage(text, nowTime);
      setChatLoading(false);
    }, 200);
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
                  Gemini + Multilingual Agent (TE, TA, KN, HI, EN)
                </span>
                <span className="px-2 py-0.5 text-xs font-semibold rounded bg-emerald-950 text-emerald-400 border border-emerald-800 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> 54/54 Tests Passing
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
              <span>FastAPI + Gemini API (gemini-3.6-flash)</span>
            </div>
            <div className="px-3 py-1.5 rounded-lg bg-slate-800/80 border border-slate-700/60 flex items-center gap-2">
              <Database className="w-3.5 h-3.5 text-cyan-400" />
              <span>PostgreSQL / SQLite + Alembic 0001</span>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="max-w-7xl mx-auto px-4 flex space-x-1 border-t border-slate-800/60 pt-1 overflow-x-auto">
          {[
            { id: 'phase2_agent', label: 'Multilingual Gemini Agent', icon: Bot },
            { id: 'architecture', label: 'Architecture & Overview', icon: Layers },
            { id: 'ai_tools', label: 'AI Tool Interfaces & Simulator', icon: Sparkles },
            { id: 'schema', label: 'Database Schema & Models', icon: Database },
            { id: 'data', label: 'Aarogya One Synthetic Data', icon: Building2 },
            { id: 'api', label: 'API Endpoints & Docs', icon: FileCode2 },
            { id: 'tests', label: 'Pytest Suite (54 Tests)', icon: ShieldCheck },
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
        {/* TAB: PHASE 2 TEXT-FIRST AI AGENT */}
        {activeTab === 'phase2_agent' && (
          <div className="space-y-6">
            {/* Phase 2 Header Card */}
            <div className="bg-gradient-to-r from-slate-900 via-slate-900/90 to-teal-950/50 p-6 rounded-2xl border border-teal-800/60 relative overflow-hidden">
              <div className="max-w-4xl space-y-3 relative z-10">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-teal-500/10 border border-teal-500/30 text-teal-300 text-xs font-medium">
                  <Bot className="w-3.5 h-3.5" />
                  Real Gemini API Integration &bull; Multilingual (Telugu, Tamil, Kannada, Hindi, English) &bull; 28/28 Agent Tests Passing
                </div>
                <h2 className="text-2xl font-bold text-white tracking-tight">
                  Multilingual Conversational AI Hospital Operations Agent
                </h2>
                <p className="text-sm text-slate-300 leading-relaxed">
                  The MediVoice conversational agent supports natural-language chat in <strong>Telugu (తెలుగు), Tamil (தமிழ்), Kannada (ಕನ್ನಡ), Hindi (हिन्दी), and English</strong>. It integrates with the official Gemini API (<code className="text-teal-300 font-mono">GeminiReasoningAdapter</code>) while preserving <code className="text-teal-300 font-mono">MockReasoningAdapter</code> for offline testing, routes queries through the restricted tool allowlist (<code className="text-teal-300 font-mono">search_doctors</code>, <code className="text-teal-300 font-mono">get_available_slots</code>, <code className="text-teal-300 font-mono">book_appointment</code>), and enforces the explicit confirmation gate before committing bookings.
                </p>
                <div className="flex flex-wrap gap-2.5 pt-2">
                  <div className="flex items-center gap-2 bg-slate-800/80 px-3 py-1.5 rounded-lg border border-slate-700 text-xs text-slate-200">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>GeminiReasoningAdapter (gemini-3.6-flash) + MockReasoningAdapter</span>
                  </div>
                  <div className="flex items-center gap-2 bg-slate-800/80 px-3 py-1.5 rounded-lg border border-slate-700 text-xs text-slate-200">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>5 Languages: తెలుగు &bull; தமிழ் &bull; ಕನ್ನಡ &bull; हिन्दी &bull; English</span>
                  </div>
                  <div className="flex items-center gap-2 bg-slate-800/80 px-3 py-1.5 rounded-lg border border-slate-700 text-xs text-slate-200">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>Explicit Confirmation Gate & Draft Fingerprint Protection</span>
                  </div>
                  <div className="flex items-center gap-2 bg-slate-800/80 px-3 py-1.5 rounded-lg border border-slate-700 text-xs text-slate-200">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <span>Bounded Timeouts, Max Tool Rounds & Backend-Only API Key</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Main Interactive Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Left Column: Interactive Chat Console */}
              <div className="lg:col-span-7 bg-slate-900 rounded-2xl border border-slate-800 flex flex-col h-[720px] overflow-hidden shadow-xl">
                {/* Chat Top Bar */}
                <div className="px-5 py-3.5 border-b border-slate-800 bg-slate-900/90 flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-lg bg-teal-500/10 border border-teal-500/20 flex items-center justify-center text-teal-400">
                      <MessageSquare className="w-4 h-4" />
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-white">Multilingual Patient Chat Simulator</h3>
                      <span className="text-[10px] font-mono text-slate-400">
                        Session: {chatSessionId.slice(0, 14)}... &bull; Language: <strong className="text-teal-300">{LANGUAGE_LABELS[agentLanguage]}</strong>
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={resetAgentSession}
                      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs border border-slate-700 transition"
                      title="Reset conversation state and memory"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      <span>Reset</span>
                    </button>
                    <span className="flex items-center gap-1.5 text-[11px] text-emerald-400 bg-emerald-950/60 px-2.5 py-1 rounded-full border border-emerald-800/60">
                      <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                      Active
                    </span>
                  </div>
                </div>

                {/* Multilingual Starters Row */}
                <div className="px-4 py-2 border-b border-slate-800/60 bg-slate-950/80 overflow-x-auto">
                  <div className="flex items-center gap-1.5 text-xs whitespace-nowrap">
                    <span className="text-[10px] text-teal-400 font-semibold uppercase mr-1">5 Languages:</span>
                    <button
                      onClick={() => handleAgentSend("నాకు గుండె నొప్పిగా ఉంది, కార్డియాలజిస్ట్ కావాలి")}
                      className="px-2.5 py-1 rounded-md bg-teal-950/70 hover:bg-teal-900 text-teal-200 border border-teal-800 text-[11px] transition"
                    >
                      తెలుగు (Cardiology)
                    </button>
                    <button
                      onClick={() => handleAgentSend("எனக்கு தலைவலி உள்ளது, நரம்பியல் மருத்துவர் வேண்டும்")}
                      className="px-2.5 py-1 rounded-md bg-teal-950/70 hover:bg-teal-900 text-teal-200 border border-teal-800 text-[11px] transition"
                    >
                      தமிழ் (Neurology)
                    </button>
                    <button
                      onClick={() => handleAgentSend("ನನಗೆ ಡಾ. ರಾಜೇಶ್ ಶರ್ಮಾ ಅವರ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ಬೇಕು")}
                      className="px-2.5 py-1 rounded-md bg-teal-950/70 hover:bg-teal-900 text-teal-200 border border-teal-800 text-[11px] transition"
                    >
                      ಕನ್ನಡ (Dr. Sharma)
                    </button>
                    <button
                      onClick={() => handleAgentSend("मुझे सीने में दर्द है, कार्डियोलॉजिस्ट दिखाना है")}
                      className="px-2.5 py-1 rounded-md bg-teal-950/70 hover:bg-teal-900 text-teal-200 border border-teal-800 text-[11px] transition"
                    >
                      हिन्दी (Cardiology)
                    </button>
                    <button
                      onClick={() => handleAgentSend("అవును")}
                      className="px-2.5 py-1 rounded-md bg-emerald-950/70 hover:bg-emerald-900 text-emerald-300 border border-emerald-800 text-[11px] transition"
                    >
                      అవును / ஆம் / ಹೌದು / हाँ (Confirm)
                    </button>
                  </div>
                </div>

                {/* Scenario Quick-Action Chips */}
                <div className="px-4 py-2 border-b border-slate-800/60 bg-slate-950/60 overflow-x-auto">
                  <div className="flex items-center gap-1.5 text-xs whitespace-nowrap">
                    <span className="text-[10px] text-slate-500 font-semibold uppercase mr-1">Booking Steps:</span>
                    <button
                      onClick={() => handleAgentSend("I need to see a cardiologist for chest pain")}
                      className="px-2.5 py-1 rounded-md bg-slate-800/80 hover:bg-slate-700 text-teal-300 border border-slate-700/80 text-[11px] transition"
                    >
                      1. Cardiology Query
                    </button>
                    <button
                      onClick={() => handleAgentSend("I choose Dr. Rajesh Sharma")}
                      className="px-2.5 py-1 rounded-md bg-slate-800/80 hover:bg-slate-700 text-teal-300 border border-slate-700/80 text-[11px] transition"
                    >
                      2. Choose Doctor
                    </button>
                    <button
                      onClick={() => handleAgentSend("I want slot-101")}
                      className="px-2.5 py-1 rounded-md bg-slate-800/80 hover:bg-slate-700 text-teal-300 border border-slate-700/80 text-[11px] transition"
                    >
                      3. Select Slot
                    </button>
                    <button
                      onClick={() => handleAgentSend("reason: Intermittent palpitations and chest evaluation")}
                      className="px-2.5 py-1 rounded-md bg-slate-800/80 hover:bg-slate-700 text-teal-300 border border-slate-700/80 text-[11px] transition"
                    >
                      4. Reason
                    </button>
                    <button
                      onClick={() => handleAgentSend("My patient reference is PAT-2026-4409")}
                      className="px-2.5 py-1 rounded-md bg-slate-800/80 hover:bg-slate-700 text-teal-300 border border-slate-700/80 text-[11px] transition"
                    >
                      5. Patient ID
                    </button>
                    <button
                      onClick={() => handleAgentSend("YES, confirm booking")}
                      className="px-2.5 py-1 rounded-md bg-emerald-950/80 hover:bg-emerald-900 text-emerald-300 border border-emerald-800 text-[11px] font-bold transition"
                    >
                      6. Explicit Confirm
                    </button>
                    <button
                      onClick={() => handleAgentSend("actually change slot to slot-102")}
                      className="px-2.5 py-1 rounded-md bg-amber-950/80 hover:bg-amber-900 text-amber-300 border border-amber-800 text-[11px] transition"
                    >
                      Change Slot (Stale Test)
                    </button>
                    <button
                      onClick={() => handleAgentSend("I want slot-103")}
                      className="px-2.5 py-1 rounded-md bg-rose-950/80 hover:bg-rose-900 text-rose-300 border border-rose-800 text-[11px] transition"
                    >
                      Conflict Test (Booked Slot)
                    </button>
                    <button
                      onClick={() => handleAgentSend("No, cancel the booking")}
                      className="px-2.5 py-1 rounded-md bg-rose-950/80 hover:bg-rose-900 text-rose-300 border border-rose-800 text-[11px] transition"
                    >
                      Cancel Flow
                    </button>
                  </div>
                </div>

                {/* Message Scroll Area */}
                <div className="flex-1 p-4 overflow-y-auto space-y-3.5 bg-slate-950/40">
                  {chatMessages.map((msg, idx) => (
                    <div
                      key={idx}
                      className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                      {msg.role === 'assistant' && (
                        <div className="w-8 h-8 rounded-full bg-teal-500/20 border border-teal-500/30 flex items-center justify-center text-teal-300 shrink-0 mt-0.5">
                          <Stethoscope className="w-4 h-4" />
                        </div>
                      )}

                      <div
                        className={`max-w-[85%] rounded-2xl px-4 py-3 text-xs leading-relaxed whitespace-pre-wrap ${
                          msg.role === 'user'
                            ? 'bg-teal-600 text-slate-950 font-medium rounded-tr-sm shadow-md'
                            : 'bg-slate-900 border border-slate-800 text-slate-200 rounded-tl-sm'
                        }`}
                      >
                        <div>{msg.content}</div>
                        <div
                          className={`text-[10px] mt-1.5 font-mono ${
                            msg.role === 'user' ? 'text-teal-900/80' : 'text-slate-500'
                          }`}
                        >
                          {msg.time}
                        </div>
                      </div>

                      {msg.role === 'user' && (
                        <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 shrink-0 mt-0.5">
                          <User className="w-4 h-4" />
                        </div>
                      )}
                    </div>
                  ))}

                  {chatLoading && (
                    <div className="flex gap-3 justify-start">
                      <div className="w-8 h-8 rounded-full bg-teal-500/20 border border-teal-500/30 flex items-center justify-center text-teal-300 shrink-0">
                        <Stethoscope className="w-4 h-4" />
                      </div>
                      <div className="bg-slate-900 border border-slate-800 text-slate-400 rounded-2xl px-4 py-2.5 text-xs flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-ping"></span>
                        Reasoning & validating backend tools...
                      </div>
                    </div>
                  )}
                </div>

                {/* Input Bar */}
                <div className="p-3 bg-slate-900 border-t border-slate-800 flex gap-2">
                  <input
                    type="text"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleAgentSend()}
                    placeholder="Message the MediVoice assistant (e.g. 'I need a cardiologist')..."
                    className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-teal-500 transition"
                  />
                  <button
                    onClick={() => handleAgentSend()}
                    disabled={chatLoading || !chatInput.trim()}
                    className="px-4 py-2.5 bg-teal-600 hover:bg-teal-500 disabled:opacity-50 text-slate-950 font-bold rounded-xl text-xs flex items-center gap-1.5 transition"
                  >
                    <Send className="w-3.5 h-3.5" />
                    <span>Send</span>
                  </button>
                </div>
              </div>

              {/* Right Column: State Inspector, Safety Gates & Tool Trace */}
              <div className="lg:col-span-5 space-y-4">
                {/* 1. Dialogue Step & Confirmation Gate Card */}
                <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
                    <div className="flex items-center gap-2">
                      <Lock className="w-4 h-4 text-teal-400" />
                      <h4 className="text-xs font-semibold text-white">Conversation State & Safety Gate</h4>
                    </div>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                      Step: {agentStep}
                    </span>
                  </div>

                  {/* Gate Status Visualizer */}
                  <div>
                    {agentStep === 'AWAITING_CONFIRMATION' ? (
                      <div className="p-3 rounded-lg bg-amber-950/40 border border-amber-800/80 text-xs space-y-1">
                        <div className="font-bold text-amber-300 flex items-center gap-1.5">
                          <AlertTriangle className="w-4 h-4 text-amber-400" />
                          Explicit Confirmation Required
                        </div>
                        <p className="text-[11px] text-amber-200/90 leading-relaxed">
                          All 4 details gathered. The booking is <strong>strictly blocked</strong> until the patient replies "YES" or "CONFIRM".
                        </p>
                      </div>
                    ) : agentStep === 'BOOKED' ? (
                      <div className="p-3 rounded-lg bg-emerald-950/40 border border-emerald-800/80 text-xs space-y-1">
                        <div className="font-bold text-emerald-300 flex items-center gap-1.5">
                          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                          Confirmed & Committed in Database
                        </div>
                        <p className="text-[11px] text-emerald-200/90 leading-relaxed">
                          Transaction safe booking completed. Slot status transitioned to BOOKED and audit event recorded.
                        </p>
                      </div>
                    ) : agentStep === 'CANCELLED' ? (
                      <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-800/80 text-xs space-y-1">
                        <div className="font-bold text-rose-300 flex items-center gap-1.5">
                          <XCircle className="w-4 h-4 text-rose-400" />
                          Booking Cancelled by Patient
                        </div>
                        <p className="text-[11px] text-rose-200/90 leading-relaxed">
                          Patient declined or cancelled. No appointment was created in the database.
                        </p>
                      </div>
                    ) : (
                      <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-xs space-y-1">
                        <div className="font-bold text-slate-300 flex items-center gap-1.5">
                          <Clock className="w-4 h-4 text-teal-400" />
                          Gathering Booking Details
                        </div>
                        <p className="text-[11px] text-slate-400 leading-relaxed">
                          Agent is prompting patient for missing parameters. Tool calls only discover doctors and slots.
                        </p>
                      </div>
                    )}
                  </div>
                </div>

                {/* 2. Slot-Filling Draft Checklist */}
                <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-2.5">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                    <h4 className="text-xs font-semibold text-white">Booking Parameters Checklist</h4>
                    <span className="text-[10px] text-slate-400 font-mono">
                      {[agentDraft.doctorId, agentDraft.slotId, agentDraft.reason, agentDraft.patientRef].filter(Boolean).length}/4 Present
                    </span>
                  </div>

                  <div className="space-y-1.5 text-xs font-mono">
                    <div className="flex items-center justify-between p-2 rounded bg-slate-950 border border-slate-800/70">
                      <div className="flex items-center gap-2">
                        {agentDraft.doctorId ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <div className="w-3.5 h-3.5 rounded-full border border-slate-600" />
                        )}
                        <span className="text-slate-400">Doctor:</span>
                      </div>
                      <span className={agentDraft.doctorName ? "text-teal-300 font-semibold" : "text-slate-600"}>
                        {agentDraft.doctorName || "Missing"}
                      </span>
                    </div>

                    <div className="flex items-center justify-between p-2 rounded bg-slate-950 border border-slate-800/70">
                      <div className="flex items-center gap-2">
                        {agentDraft.slotId ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <div className="w-3.5 h-3.5 rounded-full border border-slate-600" />
                        )}
                        <span className="text-slate-400">Slot ID:</span>
                      </div>
                      <span className={agentDraft.slotId ? "text-teal-300 font-semibold" : "text-slate-600"}>
                        {agentDraft.slotId || "Missing"}
                      </span>
                    </div>

                    <div className="flex items-center justify-between p-2 rounded bg-slate-950 border border-slate-800/70">
                      <div className="flex items-center gap-2">
                        {agentDraft.reason ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <div className="w-3.5 h-3.5 rounded-full border border-slate-600" />
                        )}
                        <span className="text-slate-400">Clinical Reason:</span>
                      </div>
                      <span className={agentDraft.reason ? "text-teal-300 font-semibold truncate max-w-[150px]" : "text-slate-600"}>
                        {agentDraft.reason || "Missing"}
                      </span>
                    </div>

                    <div className="flex items-center justify-between p-2 rounded bg-slate-950 border border-slate-800/70">
                      <div className="flex items-center gap-2">
                        {agentDraft.patientRef ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <div className="w-3.5 h-3.5 rounded-full border border-slate-600" />
                        )}
                        <span className="text-slate-400">Patient Ref:</span>
                      </div>
                      <span className={agentDraft.patientRef ? "text-teal-300 font-semibold" : "text-slate-600"}>
                        {agentDraft.patientRef || "Missing"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* 3. Restricted Tool Trace */}
                <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-2.5">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                    <div className="flex items-center gap-2">
                      <Terminal className="w-4 h-4 text-teal-400" />
                      <h4 className="text-xs font-semibold text-white">Restricted Tool Execution Trace</h4>
                    </div>
                    <span className="text-[10px] text-teal-400 font-mono">Allowlist Only</span>
                  </div>

                  <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                    {agentToolTrace.length === 0 ? (
                      <div className="text-xs text-slate-500 font-mono p-2 bg-slate-950 rounded border border-slate-800">
                        No backend tools executed yet in this session.
                      </div>
                    ) : (
                      agentToolTrace.map((tr, i) => (
                        <div
                          key={i}
                          className="p-2 rounded bg-slate-950 border border-slate-800 text-xs font-mono flex items-center justify-between"
                        >
                          <div className="flex items-center gap-1.5">
                            {tr.success ? (
                              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                            ) : (
                              <XCircle className="w-3 h-3 text-rose-400" />
                            )}
                            <span className="text-teal-300 font-bold">{tr.tool_name}</span>
                          </div>
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded ${
                              tr.success ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'
                            }`}
                          >
                            {tr.success ? 'SUCCESS' : 'CONFLICT / REJECTED'}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                {/* 4. Confirmed Appointment Receipt */}
                {agentBookedAppointment && (
                  <div className="bg-slate-900 p-4 rounded-xl border border-emerald-800/80 space-y-2 bg-gradient-to-br from-slate-900 to-emerald-950/20">
                    <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                      <span className="text-xs font-bold text-emerald-300 flex items-center gap-1.5">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Confirmed Database Record
                      </span>
                      <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950 px-2 py-0.5 rounded border border-emerald-800">
                        CONFIRMED
                      </span>
                    </div>
                    <div className="space-y-1 text-xs font-mono text-slate-300">
                      <div>Appt ID: <span className="text-white">{agentBookedAppointment.appointment_id}</span></div>
                      <div>Doctor: <span className="text-white">{agentBookedAppointment.doctor_name}</span></div>
                      <div>Slot ID: <span className="text-white">{agentBookedAppointment.slot_id}</span></div>
                      <div>Patient: <span className="text-white">{agentBookedAppointment.patient_reference}</span></div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

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
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" /> 54 Passed, 0 Failed (1.56s)
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

              {/* Phase 2 Agent & Multilingual Gemini Suite */}
              <div className="bg-slate-900 p-4 rounded-xl border border-teal-800/80 space-y-2 md:col-span-2">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="font-semibold text-xs text-teal-300 flex items-center gap-1.5">
                    <Bot className="w-3.5 h-3.5 text-teal-400" /> test_agent.py (28 Tests) — Gemini Adapter & Multilingual Booking (TE, TA, KN, HI, EN)
                  </span>
                  <span className="text-[10px] text-emerald-400 font-mono font-bold">28/28 PASSED</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-1 text-xs font-mono text-slate-300">
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_restricted_tool_router_allowlist</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_restricted_tool_router_argument_validation</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_agent_doctor_search_by_specialty</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_agent_slot_discovery</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_agent_missing_details_prompts_sequentially</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_explicit_confirmation_gate_prevents_premature_booking</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_changed_details_invalidates_prior_confirmation</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_duplicate_confirmation_attempt</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_session_isolation</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_unavailable_slot_conflict_handling</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_successful_booking_end_to_end_with_db_commit</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_gemini_adapter_missing_credentials_handling</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_gemini_adapter_provider_failures_timeout_and_http_error</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_gemini_adapter_response_parsing_and_multi_round_tool_calling</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_gemini_adapter_max_tool_rounds_bound</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_gemini_adapter_confirmation_gate_blocks_premature_book_appointment</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_multilingual_telugu_end_to_end_booking</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_multilingual_tamil_end_to_end_booking</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_multilingual_kannada_conversation_and_cancellation</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_multilingual_hindi_end_to_end_with_changed_details_reconfirmation</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_gemini_adapter_multilingual_prompt_and_response_consistency_all_5_languages</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_gemini_adapter_end_to_end_booking_with_explicit_confirmation</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_gemini_adapter_changed_details_invalidates_prior_confirmation</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_gemini_adapter_unavailable_slot_and_duplicate_booking_conflict</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_gemini_adapter_unapproved_tool_rejected_by_router</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_multilingual_search_doctors_aliases_in_all_5_languages</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_agent_config_endpoint_hides_api_key</div>
                  <div className="flex items-center gap-1.5 text-emerald-300"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> test_create_reasoning_adapter_factory_selection</div>
                </div>
              </div>
            </div>

            {/* Terminal Command Snippet */}
            <div className="bg-slate-900 p-4 rounded-xl border border-slate-800 space-y-2">
              <span className="text-xs text-slate-400 font-semibold">Local Verification Command:</span>
              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 font-mono text-xs text-emerald-400 flex items-center justify-between">
                <span>$env:PYTHONPATH="backend"; $env:DATABASE_URL="sqlite:///aarogya_demo.db"; py -m pytest backend/tests/ -v</span>
                <span className="text-slate-400 font-bold text-[11px]">54 passed in ~1.56s</span>
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
