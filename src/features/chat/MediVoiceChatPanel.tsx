import React, { useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  Code2,
  Globe,
  Mic,
  MicOff,
  RotateCcw,
  Send,
  ShieldCheck,
  Volume2,
  VolumeX,
} from 'lucide-react';
import { usePlatform } from '../../context/PlatformContext';
import { ApiError, medivoiceApi } from '../../services/api';
import {
  BookingDraftState,
  SupportedLanguage,
  ToolCallTrace,
} from '../../types/api';

interface ChatMessageItem {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  step?: string;
  requiresConfirmation?: boolean;
  isError?: boolean;
}

const LANGUAGE_META: Record<
  SupportedLanguage,
  { label: string; speechLang: string; samplePrompt: string }
> = {
  en: {
    label: 'English',
    speechLang: 'en-IN',
    samplePrompt: 'I need a Cardiology consultation with Dr. Rajesh Sharma',
  },
  te: {
    label: 'తెలుగు (Telugu)',
    speechLang: 'te-IN',
    samplePrompt: 'నాకు జ్వరం ఉంది, జనరల్ మెడిసిన్ డాక్టర్ కావాలి',
  },
  ta: {
    label: 'தமிழ் (Tamil)',
    speechLang: 'ta-IN',
    samplePrompt: 'எனக்கு காய்ச்சல் உள்ளது, பொது மருத்துவரை பார்க்க வேண்டும்',
  },
  kn: {
    label: 'ಕನ್ನಡ (Kannada)',
    speechLang: 'kn-IN',
    samplePrompt: 'ನನಗೆ ಜ್ವರವಿದೆ, ಜನರಲ್ ಮೆಡಿಸಿನ್ ವೈದ್ಯರನ್ನು ಕಾಣಬೇಕು',
  },
  hi: {
    label: 'हिन्दी (Hindi)',
    speechLang: 'hi-IN',
    samplePrompt: 'मुझे बुखार है, जनरल मेडिसिन डॉक्टर से मिलना है',
  },
};

const QUICK_SCENARIO_PROMPTS: Array<{
  label: string;
  prompt: string;
  lang: SupportedLanguage;
}> = [
  {
    label: 'Cardiology Consultation',
    prompt: 'I need a Cardiology consultation with Dr. Rajesh Sharma',
    lang: 'en',
  },
  {
    label: 'Lab Status',
    prompt: 'Help me check my lab status using the code on my receipt',
    lang: 'en',
  },
  {
    label: 'Cashless Insurance Plans',
    prompt: 'Which cashless health insurance plans are accepted at Aarogya One Hospital?',
    lang: 'en',
  },
  {
    label: 'తెలుగు: డాక్టర్ ఎంపిక',
    prompt: 'నాకు జ్వరం ఉంది, ఏ డాక్టర్ ని కలవాలో తెలియదు',
    lang: 'te',
  },
  {
    label: 'हिन्दी: लैब रिपोर्ट',
    prompt: 'मेरी लैब रिपोर्ट का स्टेटस मेरे रसीद कोड से चेक करें',
    lang: 'hi',
  },
];

export const MediVoiceChatPanel: React.FC = () => {
  const { activePatientRef, setActivePatientRef, agentConfig, refreshOperationalData } =
    usePlatform();

  const [sessionId, setSessionId] = useState<string>(() => `mv-session-${Date.now()}`);
  const [messages, setMessages] = useState<ChatMessageItem[]>([
    {
      id: 'welcome-msg',
      role: 'assistant',
      content:
        'Welcome to Aarogya One Hospital. I am MediVoice AI (supporting English, తెలుగు, தமிழ், ಕನ್ನಡ, and हिन्दी). How can I assist you with specialist doctor discovery, appointment booking, 6-digit lab report verification, or hospital insurance guidance today?',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      step: 'GREETING',
    },
  ]);
  const [input, setInput] = useState<string>('');
  const [isSending, setIsSending] = useState<boolean>(false);
  const [activeLanguage, setActiveLanguage] = useState<SupportedLanguage>('en');
  const [conversationStep, setConversationStep] = useState<string>('GREETING');
  const [confirmationStatus, setConfirmationStatus] = useState<string>('NONE');
  const [requiresConfirmation, setRequiresConfirmation] = useState<boolean>(false);
  const [draft, setDraft] = useState<BookingDraftState>({
    patient_reference: activePatientRef,
  });
  const [toolTraces, setToolTraces] = useState<ToolCallTrace[]>([]);
  const [bookedResult, setBookedResult] = useState<Record<string, unknown> | null>(null);
  const [showInspector, setShowInspector] = useState<boolean>(false);

  // Conditional Web Speech API Voice Input & Output
  const [speechSupported, setSpeechSupported] = useState<boolean>(false);
  const [ttsSupported, setTtsSupported] = useState<boolean>(false);
  const [isListening, setIsListening] = useState<boolean>(false);
  const [ttsEnabled, setTtsEnabled] = useState<boolean>(false);
  const recognitionRef = useRef<{ stop: () => void } | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const win = window as unknown as Record<string, unknown>;
    const hasRecognition = Boolean(win.SpeechRecognition || win.webkitSpeechRecognition);
    setSpeechSupported(hasRecognition);
    setTtsSupported(typeof window !== 'undefined' && 'speechSynthesis' in window);
  }, []);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages, isSending]);

  const speakAssistantReply = (text: string, lang: SupportedLanguage) => {
    if (!ttsEnabled || !ttsSupported || typeof window === 'undefined') return;
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = LANGUAGE_META[lang]?.speechLang || 'en-IN';
      utterance.rate = 1.0;
      window.speechSynthesis.speak(utterance);
    } catch {
      // Ignore synthesis errors
    }
  };

  const toggleVoiceInput = () => {
    if (!speechSupported) return;
    if (isListening && recognitionRef.current) {
      recognitionRef.current.stop();
      setIsListening(false);
      return;
    }

    const win = window as unknown as Record<
      string,
      new () => {
        lang: string;
        interimResults: boolean;
        maxAlternatives: number;
        onresult: (event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void;
        onerror: () => void;
        onend: () => void;
        start: () => void;
        stop: () => void;
      }
    >;
    const SpeechRec = win.SpeechRecognition || win.webkitSpeechRecognition;
    if (!SpeechRec) return;

    try {
      const recognition = new SpeechRec();
      recognition.lang = LANGUAGE_META[activeLanguage]?.speechLang || 'en-IN';
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      recognition.onresult = (event) => {
        const transcript = event.results?.[0]?.[0]?.transcript;
        if (transcript) {
          setInput((prev) => (prev ? `${prev} ${transcript}` : transcript));
        }
      };
      recognition.onerror = () => setIsListening(false);
      recognition.onend = () => setIsListening(false);

      recognitionRef.current = recognition;
      setIsListening(true);
      recognition.start();
    } catch {
      setIsListening(false);
    }
  };

  const handleSendMessage = async (overrideMessage?: string) => {
    const textToSend = (overrideMessage !== undefined ? overrideMessage : input).trim();
    if (!textToSend || isSending) return;

    const nowLabel = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userMsg: ChatMessageItem = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: textToSend,
      timestamp: nowLabel,
    };

    setMessages((prev) => [...prev, userMsg]);
    if (overrideMessage === undefined) {
      setInput('');
    }
    setIsSending(true);

    try {
      const response = await medivoiceApi.sendAgentMessage({
        session_id: sessionId,
        message: textToSend,
        patient_reference: activePatientRef,
      });

      setSessionId(response.session_id);
      setActiveLanguage(response.language);
      setConversationStep(response.conversation_step);
      setConfirmationStatus(response.confirmation_status);
      setRequiresConfirmation(response.requires_confirmation);
      setDraft(response.draft);

      if (response.tool_calls && response.tool_calls.length > 0) {
        setToolTraces((prev) => [...response.tool_calls, ...prev].slice(0, 20));
      }

      if (response.booked_appointment) {
        setBookedResult(response.booked_appointment);
        await refreshOperationalData();
      }

      const assistantMsg: ChatMessageItem = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.assistant_reply,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        step: response.conversation_step,
        requiresConfirmation: response.requires_confirmation,
      };
      setMessages((prev) => [...prev, assistantMsg]);
      speakAssistantReply(response.assistant_reply, response.language);
    } catch (err) {
      const errMessage =
        err instanceof ApiError
          ? err.message
          : 'Unable to reach MediVoice AI right now. Please try again shortly.';
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: errMessage,
          timestamp: nowLabel,
          isError: true,
        },
      ]);
    } finally {
      setIsSending(false);
    }
  };

  const handleResetSession = async () => {
    try {
      await medivoiceApi.resetAgentSession(sessionId);
    } catch {
      // Ignore if session wasn't initialized on server yet
    }
    const nextSession = `mv-session-${Date.now()}`;
    setSessionId(nextSession);
    setConversationStep('GREETING');
    setConfirmationStatus('NONE');
    setRequiresConfirmation(false);
    setDraft({ patient_reference: activePatientRef });
    setToolTraces([]);
    setBookedResult(null);
    setMessages([
      {
        id: `reset-${Date.now()}`,
        role: 'assistant',
        content:
          'Session reset complete. How can I assist you with doctor appointments, 6-digit lab status verification, or insurance coverage information today?',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        step: 'GREETING',
      },
    ]);
  };

  return (
    <div className="rounded-2xl border border-[#334155] bg-[#111B2E] shadow-2xl overflow-hidden">
      {/* Assistant Header with Animated Waveform */}
      <div className="border-b border-[#334155] bg-[#0B1020]/90 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-[#2DD4BF]/50 bg-[#2DD4BF]/10 text-[#2DD4BF]">
              <Bot className="h-5 w-5" />
              <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-[#2DD4BF] ring-2 ring-[#0B1020]" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-display text-base font-bold text-[#E5EDF7]">
                  MediVoice AI Assistant
                </h2>
                <span className="rounded border border-[#2DD4BF]/30 bg-[#2DD4BF]/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-[#2DD4BF]">
                  {LANGUAGE_META[activeLanguage]?.label || activeLanguage.toUpperCase()}
                </span>
              </div>
              <p className="text-xs text-[#94A3B8]">
                Allowlisted tool router • Explicit booking confirmation • 5 Indian languages
              </p>
            </div>
          </div>

          {/* Animated Acoustic Waveform Carrier */}
          <div className="flex items-center gap-2">
            <div
              aria-hidden="true"
              className="hidden sm:flex items-center gap-1 rounded-lg border border-[#334155] bg-[#111B2E] px-3 py-1.5"
            >
              {[14, 22, 12, 26, 18, 24, 10, 20].map((height, idx) => (
                <span
                  key={idx}
                  style={{
                    height: isSending || isListening ? `${height}px` : '8px',
                  }}
                  className={`w-1 rounded-full transition-all duration-300 ${
                    isListening
                      ? 'bg-[#2DD4BF] animate-pulse'
                      : isSending
                      ? 'bg-[#38BDF8] animate-pulse'
                      : 'bg-[#334155]'
                  }`}
                />
              ))}
              <span className="ml-1.5 font-mono text-[10px] text-[#94A3B8]">
                {isListening ? 'LISTENING' : isSending ? 'ROUTING' : 'READY'}
              </span>
            </div>

            {ttsSupported && (
              <button
                type="button"
                onClick={() => setTtsEnabled((prev) => !prev)}
                title={ttsEnabled ? 'Mute voice readout' : 'Enable voice readout'}
                className={`rounded-lg border p-2 text-xs transition-colors ${
                  ttsEnabled
                    ? 'border-[#2DD4BF] bg-[#2DD4BF]/15 text-[#2DD4BF]'
                    : 'border-[#334155] bg-[#111B2E] text-[#94A3B8] hover:text-[#E5EDF7]'
                }`}
              >
                {ttsEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
              </button>
            )}

            <button
              type="button"
              onClick={() => setShowInspector((prev) => !prev)}
              className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 font-mono text-xs transition-colors ${
                showInspector
                  ? 'border-[#38BDF8] bg-[#38BDF8]/15 text-[#38BDF8]'
                  : 'border-[#334155] bg-[#111B2E] text-[#94A3B8] hover:text-[#E5EDF7]'
              }`}
            >
              <Code2 className="h-3.5 w-3.5" />
              <span>State ({toolTraces.length})</span>
            </button>

            <button
              type="button"
              onClick={() => void handleResetSession()}
              title="Reset conversation session"
              className="flex items-center gap-1 rounded-lg border border-[#334155] bg-[#111B2E] px-2.5 py-1.5 text-xs text-[#94A3B8] transition-colors hover:border-rose-500/40 hover:text-rose-300"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              <span className="hidden md:inline">Reset</span>
            </button>
          </div>
        </div>

        {/* Patient Context & Quick Language Switcher Bar */}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[#334155]/60 pt-3 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-[#94A3B8]">Patient ID:</span>
            <input
              type="text"
              aria-label="Synthetic Patient Reference"
              value={activePatientRef}
              onChange={(e) => setActivePatientRef(e.target.value)}
              className="w-36 rounded border border-[#334155] bg-[#111B2E] px-2 py-1 font-mono text-xs text-[#2DD4BF] focus:border-[#2DD4BF] focus:outline-none"
            />
            <span className="hidden sm:inline font-mono text-[11px] text-[#94A3B8]">
              Step: <strong className="text-[#E5EDF7]">{conversationStep}</strong>
            </span>
          </div>

          <div className="flex items-center gap-1">
            <Globe className="h-3.5 w-3.5 text-[#38BDF8] mr-1" />
            {(['en', 'te', 'ta', 'kn', 'hi'] as SupportedLanguage[]).map((langCode) => (
              <button
                key={langCode}
                type="button"
                onClick={() => void handleSendMessage(LANGUAGE_META[langCode].samplePrompt)}
                className={`rounded px-2 py-0.5 font-mono text-[11px] transition-colors ${
                  activeLanguage === langCode
                    ? 'bg-[#2DD4BF]/20 text-[#2DD4BF] border border-[#2DD4BF]/40'
                    : 'text-[#94A3B8] hover:bg-[#111B2E] hover:text-[#E5EDF7]'
                }`}
              >
                {langCode.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Collapsible Session Draft & Tool Router Trace Drawer */}
      {showInspector && (
        <div className="border-b border-[#334155] bg-[#0B1020]/95 px-5 py-3.5 text-xs space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-mono font-semibold text-[#38BDF8]">
              SESSION DRAFT & ALLOWLISTED TOOL ROUTER
            </span>
            {agentConfig && (
              <span className="font-mono text-[11px] text-[#94A3B8]">
                Adapter: {agentConfig.adapter_class}
              </span>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5 font-mono text-[11px]">
            <div className="rounded border border-[#334155] bg-[#111B2E] p-2">
              <span className="block text-[10px] text-[#94A3B8]">SPECIALTY</span>
              <span className="text-[#E5EDF7]">{draft.specialty_or_department || '—'}</span>
            </div>
            <div className="rounded border border-[#334155] bg-[#111B2E] p-2">
              <span className="block text-[10px] text-[#94A3B8]">DOCTOR</span>
              <span className="text-[#E5EDF7]">{draft.selected_doctor_name || '—'}</span>
            </div>
            <div className="rounded border border-[#334155] bg-[#111B2E] p-2">
              <span className="block text-[10px] text-[#94A3B8]">SLOT</span>
              <span className="text-[#E5EDF7]">{draft.selected_slot_id || '—'}</span>
            </div>
            <div className="rounded border border-[#334155] bg-[#111B2E] p-2">
              <span className="block text-[10px] text-[#94A3B8]">REASON</span>
              <span className="text-[#E5EDF7] truncate block">{draft.reason_category || '—'}</span>
            </div>
            <div className="rounded border border-[#334155] bg-[#111B2E] p-2">
              <span className="block text-[10px] text-[#94A3B8]">CONFIRMATION</span>
              <span className="text-[#2DD4BF]">{confirmationStatus}</span>
            </div>
          </div>

          {toolTraces.length > 0 && (
            <div className="max-h-32 overflow-y-auto space-y-1.5 border-t border-[#334155]/60 pt-2">
              {toolTraces.map((trace, i) => (
                <div
                  key={`${trace.tool_name}-${i}`}
                  className="flex items-center justify-between rounded border border-[#334155]/80 bg-[#111B2E] px-2.5 py-1.5 font-mono text-[11px]"
                >
                  <span className="text-[#38BDF8]">{trace.tool_name}</span>
                  <span className={trace.success ? 'text-emerald-400' : 'text-rose-400'}>
                    {trace.success ? 'SUCCESS' : trace.error || 'FAILED'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Conversation Transcript */}
      <div className="h-[380px] overflow-y-auto px-5 py-4 space-y-3.5 bg-[#0B1020]/50">
        {messages.map((msg) => {
          const isUser = msg.role === 'user';
          return (
            <div
              key={msg.id}
              className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
            >
              <div
                className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  isUser
                    ? 'bg-[#2DD4BF] text-[#0B1020] font-medium'
                    : msg.isError
                    ? 'border border-rose-500/50 bg-rose-500/10 text-rose-200'
                    : 'border border-[#334155] bg-[#111B2E] text-[#E5EDF7]'
                }`}
              >
                <p className="whitespace-pre-wrap">{msg.content}</p>
              </div>
              <div className="mt-1 flex items-center gap-2 px-1 font-mono text-[10px] text-[#94A3B8] tabular-nums">
                <span>{isUser ? `Patient (${activePatientRef})` : 'MediVoice AI'}</span>
                <span>•</span>
                <span>{msg.timestamp}</span>
              </div>
            </div>
          );
        })}

        {isSending && (
          <div className="flex items-center gap-2.5 text-xs text-[#94A3B8] font-mono">
            <span className="h-2 w-2 rounded-full bg-[#2DD4BF] animate-ping" />
            <span>MediVoice AI is querying hospital backend tools...</span>
          </div>
        )}
        <div ref={transcriptEndRef} />
      </div>

      {/* Explicit Confirmation Banner when Agent Awaits Patient Confirmation */}
      {requiresConfirmation && (
        <div className="border-t border-[#2DD4BF]/40 bg-[#2DD4BF]/10 px-5 py-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-[#E5EDF7]">
            <ShieldCheck className="h-4 w-4 text-[#2DD4BF] shrink-0" />
            <span>
              <strong>Explicit Patient Confirmation Required:</strong> Confirm to commit slot{' '}
              <span className="font-mono text-[#2DD4BF]">{draft.selected_slot_id}</span> with{' '}
              <strong>{draft.selected_doctor_name}</strong>.
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={isSending}
              onClick={() => void handleSendMessage('Yes, confirm booking')}
              className="rounded-lg bg-[#2DD4BF] px-3 py-1.5 text-xs font-semibold text-[#0B1020] hover:bg-[#2DD4BF]/90 disabled:opacity-50"
            >
              Confirm Booking
            </button>
            <button
              type="button"
              disabled={isSending}
              onClick={() => void handleSendMessage('No, cancel')}
              className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-1.5 text-xs font-medium text-rose-300 hover:bg-rose-500/20 disabled:opacity-50"
            >
              Cancel Draft
            </button>
          </div>
        </div>
      )}

      {/* Committed Booking Receipt Banner */}
      {bookedResult && (
        <div className="border-t border-emerald-500/40 bg-emerald-500/10 px-5 py-2.5 flex items-center justify-between text-xs text-emerald-200">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
            <span>
              Appointment committed to database:{' '}
              <strong className="font-mono">
                {String(bookedResult.appointment_id || '').slice(0, 12)}...
              </strong>{' '}
              ({String(bookedResult.doctor_name || '')} • {String(bookedResult.slot_id || '')})
            </span>
          </div>
          <span className="font-mono text-[10px] uppercase text-emerald-300">CONFIRMED</span>
        </div>
      )}

      {/* Scenario Starter Prompts */}
      <div className="border-t border-[#334155]/70 bg-[#0B1020]/80 px-5 py-2.5 flex items-center gap-2 overflow-x-auto">
        <span className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-[#94A3B8]">
          Try:
        </span>
        {QUICK_SCENARIO_PROMPTS.map((item) => (
          <button
            key={item.label}
            type="button"
            disabled={isSending}
            onClick={() => void handleSendMessage(item.prompt)}
            className="shrink-0 rounded-lg border border-[#334155] bg-[#111B2E] px-2.5 py-1 text-xs text-[#E5EDF7] transition-colors hover:border-[#38BDF8] hover:text-[#38BDF8] disabled:opacity-50"
          >
            {item.label}
          </button>
        ))}
      </div>

      {/* Input Composer */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void handleSendMessage();
        }}
        className="border-t border-[#334155] bg-[#0B1020] p-3.5 flex items-center gap-2.5"
      >
        {speechSupported && (
          <button
            type="button"
            onClick={toggleVoiceInput}
            title={isListening ? 'Stop voice capture' : 'Speak in selected language'}
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border transition-all ${
              isListening
                ? 'border-rose-500 bg-rose-500/20 text-rose-300 animate-pulse'
                : 'border-[#334155] bg-[#111B2E] text-[#38BDF8] hover:border-[#38BDF8]'
            }`}
          >
            {isListening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
          </button>
        )}

        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask in English, తెలుగు, தமிழ், ಕನ್ನಡ, or हिन्दी (e.g., book cardiology slot, check lab status using my receipt code)..."
          className="flex-1 rounded-xl border border-[#334155] bg-[#111B2E] px-4 py-2.5 text-sm text-[#E5EDF7] placeholder-[#94A3B8]/60 focus:border-[#2DD4BF] focus:outline-none"
        />

        <button
          type="submit"
          disabled={isSending || !input.trim()}
          className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-xl bg-[#2DD4BF] px-4 text-xs font-semibold text-[#0B1020] transition-colors hover:bg-[#2DD4BF]/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#38BDF8] disabled:opacity-50"
        >
          <Send className="h-4 w-4" />
          <span>Send</span>
        </button>
      </form>
    </div>
  );
};
