import React, { useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Globe,
  Maximize2,
  Mic,
  MicOff,
  RotateCcw,
  Send,
  ShieldCheck,
  Terminal,
  Volume2,
  VolumeX,
} from 'lucide-react';
import { usePlatform } from '../../app/PlatformContext';
import { ApiError, medivoiceApi } from '../../services/api';
import {
  BookingDraftState,
  SupportedLanguage,
  ToolCallTrace,
} from '../../types/api';

interface ChatTurn {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  language?: SupportedLanguage;
  step?: string;
  requiresConfirmation?: boolean;
  draft?: BookingDraftState;
  toolCalls?: ToolCallTrace[];
}

const LANGUAGE_OPTIONS: Array<{
  code: SupportedLanguage;
  label: string;
  nativeLabel: string;
  samplePrompt: string;
  bcp47: string;
}> = [
  {
    code: 'en',
    label: 'English',
    nativeLabel: 'English',
    samplePrompt: 'I want to see a cardiologist tomorrow morning.',
    bcp47: 'en-IN',
  },
  {
    code: 'te',
    label: 'Telugu',
    nativeLabel: 'తెలుగు',
    samplePrompt: 'నాకు జ్వరం ఉంది, జనరల్ మెడిసిన్ డాక్టర్ కావాలి',
    bcp47: 'te-IN',
  },
  {
    code: 'hi',
    label: 'Hindi',
    nativeLabel: 'हिन्दी',
    samplePrompt: 'मुझे हृदय विशेषज्ञ से कल सुबह अपॉइंटमेंट चाहिए',
    bcp47: 'hi-IN',
  },
  {
    code: 'ta',
    label: 'Tamil',
    nativeLabel: 'தமிழ்',
    samplePrompt: 'எனக்கு இதய மருத்துவரை பார்க்க வேண்டும்',
    bcp47: 'ta-IN',
  },
  {
    code: 'kn',
    label: 'Kannada',
    nativeLabel: 'ಕನ್ನಡ',
    samplePrompt: 'ನನಗೆ ಹೃದ್ರೋಗ ತಜ್ಞರ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬೇಕು',
    bcp47: 'kn-IN',
  },
];

const QUICK_WORKFLOW_PROMPTS = [
  {
    category: 'Doctor Discovery',
    prompt: 'Which cardiologists are available at Aarogya One Hospital?',
  },
  {
    category: 'Appointment Booking',
    prompt: 'I want to book a General Medicine appointment with Dr. Vikram Mehta.',
  },
  {
    category: 'Lab Status (6-Digit Code)',
    prompt: 'Check my lab report status for verification code 482910',
  },
  {
    category: 'Insurance Guidance',
    prompt: 'Does Aarogya Shield Gold Cashless Plus cover Cardiology and OPD?',
  },
];

interface MediVoiceChatExperienceProps {
  mode?: 'embedded' | 'fullscreen';
}

export const MediVoiceChatExperience: React.FC<MediVoiceChatExperienceProps> = ({
  mode = 'embedded',
}) => {
  const {
    activePatientRef,
    agentConfig,
    refreshOperationalData,
    navigate,
    initialChatPrompt,
    clearInitialChatPrompt,
  } = usePlatform();

  const [sessionId, setSessionId] = useState<string>(
    () => `sess-${Math.random().toString(36).slice(2, 10)}`
  );
  const [selectedLang, setSelectedLang] = useState<SupportedLanguage>('en');
  const [inputMessage, setInputMessage] = useState<string>('');
  const [isSending, setIsSending] = useState<boolean>(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [showToolTraces, setShowToolTraces] = useState<boolean>(false);

  const [isListening, setIsListening] = useState<boolean>(false);
  const [isSpeaking, setIsSpeaking] = useState<boolean>(false);
  const [autoSpeakReply, setAutoSpeakReply] = useState<boolean>(false);

  const [turns, setTurns] = useState<ChatTurn[]>([
    {
      id: 'welcome-turn',
      role: 'assistant',
      content:
        'Welcome to Aarogya One Hospital. I am MediVoice AI. I can help you find specialists, check open appointment slots, verify your 6-digit laboratory report status, or review hospital insurance plans in English, Telugu, Hindi, Tamil, or Kannada. How can I assist you today?',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      language: 'en',
      step: 'READY',
    },
  ]);

  const scrollContainerRef = useRef<HTMLDivElement | null>(null);

  const speechRecognitionSupported =
    typeof window !== 'undefined' &&
    Boolean(
      (window as unknown as Record<string, unknown>).SpeechRecognition ||
        (window as unknown as Record<string, unknown>).webkitSpeechRecognition
    );

  const speechSynthesisSupported =
    typeof window !== 'undefined' && 'speechSynthesis' in window;

  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  }, [turns, isSending]);

  const speakAssistantText = (text: string, langCode: SupportedLanguage) => {
    if (!speechSynthesisSupported || !autoSpeakReply) return;
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      const langMeta = LANGUAGE_OPTIONS.find((l) => l.code === langCode);
      utterance.lang = langMeta?.bcp47 || 'en-IN';
      utterance.onstart = () => setIsSpeaking(true);
      utterance.onend = () => setIsSpeaking(false);
      utterance.onerror = () => setIsSpeaking(false);
      window.speechSynthesis.speak(utterance);
    } catch {
      setIsSpeaking(false);
    }
  };

  const handleSendMessage = async (textOverride?: string) => {
    const messageToSend = (textOverride !== undefined ? textOverride : inputMessage).trim();
    if (!messageToSend || isSending) return;

    if (textOverride === undefined) {
      setInputMessage('');
    }
    setChatError(null);

    const userTurn: ChatTurn = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: messageToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setTurns((prev) => [...prev, userTurn]);
    setIsSending(true);

    try {
      const response = await medivoiceApi.sendAgentMessage({
        session_id: sessionId,
        message: messageToSend,
        patient_reference: activePatientRef,
      });

      setSessionId(response.session_id);
      if (response.language) {
        setSelectedLang(response.language);
      }

      const assistantTurn: ChatTurn = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.assistant_reply,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        language: response.language,
        step: response.conversation_step,
        requiresConfirmation: response.requires_confirmation,
        draft: response.draft,
        toolCalls: response.tool_calls,
      };

      setTurns((prev) => [...prev, assistantTurn]);
      speakAssistantText(response.assistant_reply, response.language);

      if (response.booked_appointment || (response.tool_calls && response.tool_calls.length > 0)) {
        await refreshOperationalData();
      }
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : 'Unable to reach the MediVoice AI conversation service. Please try again.';
      setChatError(msg);
    } finally {
      setIsSending(false);
    }
  };

  useEffect(() => {
    if (initialChatPrompt) {
      const promptToRun = initialChatPrompt;
      clearInitialChatPrompt();
      void handleSendMessage(promptToRun);
    }
  }, [initialChatPrompt, clearInitialChatPrompt]);

  const handleResetSession = async () => {
    try {
      await medivoiceApi.resetAgentSession(sessionId);
    } catch {
      // ignore if session wasn't persisted yet
    }
    const freshSession = `sess-${Math.random().toString(36).slice(2, 10)}`;
    setSessionId(freshSession);
    setChatError(null);
    setTurns([
      {
        id: `welcome-${Date.now()}`,
        role: 'assistant',
        content:
          'Conversation session reset. Tell me what symptoms or department you need, your 6-digit lab verification code, or any insurance question.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        language: selectedLang,
        step: 'READY',
      },
    ]);
  };

  const handleToggleMic = () => {
    if (!speechRecognitionSupported) return;
    if (isListening) {
      setIsListening(false);
      return;
    }

    try {
      const SpeechRecConstructor = ((window as unknown as Record<string, unknown>)
        .SpeechRecognition ||
        (window as unknown as Record<string, unknown>).webkitSpeechRecognition) as new () => {
        lang: string;
        interimResults: boolean;
        maxAlternatives: number;
        onstart: () => void;
        onend: () => void;
        onerror: () => void;
        onresult: (event: {
          results: ArrayLike<ArrayLike<{ transcript: string }>>;
        }) => void;
        start: () => void;
      };

      const recognition = new SpeechRecConstructor();
      const langMeta = LANGUAGE_OPTIONS.find((l) => l.code === selectedLang);
      recognition.lang = langMeta?.bcp47 || 'en-IN';
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => setIsListening(true);
      recognition.onend = () => setIsListening(false);
      recognition.onerror = () => setIsListening(false);
      recognition.onresult = (event) => {
        const transcript = event.results?.[0]?.[0]?.transcript;
        if (transcript) {
          setInputMessage(transcript);
        }
      };
      recognition.start();
    } catch {
      setIsListening(false);
    }
  };

  const latestAssistantTurn = [...turns].reverse().find((t) => t.role === 'assistant');
  const isVoiceActive = isListening || isSpeaking || isSending;

  return (
    <div
      className={`flex flex-col rounded-xl border border-[#334155] bg-[#111B2E] overflow-hidden ${
        mode === 'fullscreen' ? 'min-h-[calc(100vh-140px)]' : 'h-full'
      }`}
    >
      {/* Assistant Header */}
      <div className="border-b border-[#334155] bg-[#0B1020]/90 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            {mode === 'fullscreen' && (
              <button
                type="button"
                onClick={() => navigate('/')}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[#334155] bg-[#111B2E] px-3 py-1.5 text-xs font-medium text-[#E5EDF7] hover:border-[#2DD4BF] whitespace-nowrap shrink-0"
              >
                <ArrowLeft className="h-3.5 w-3.5 text-[#2DD4BF]" />
                Back to Hospital Website
              </button>
            )}

            {/* Voice Waveform Visualizer (animates only when listening, speaking, or processing) */}
            <div
              aria-hidden="true"
              className="flex h-10 w-10 items-center justify-center gap-0.5 rounded-lg border border-[#2DD4BF]/40 bg-[#2DD4BF]/10 px-1.5"
            >
              {[0, 1, 2, 3, 4].map((barIdx) => (
                <span
                  key={barIdx}
                  className={`w-1 rounded-full transition-transform duration-150 ${
                    isVoiceActive
                      ? 'h-5 bg-[#2DD4BF] scale-y-100 animate-pulse'
                      : 'h-2 bg-[#38BDF8]/70 scale-y-75'
                  }`}
                />
              ))}
            </div>

            <div>
              <div className="flex items-center gap-2 text-xs text-[#94A3B8]">
                <h2 className="font-display text-base font-bold text-[#E5EDF7]">
                  MediVoice AI Assistant
                </h2>
                <span aria-hidden="true">·</span>
                <span className="text-[#2DD4BF]">Aarogya One Hospital</span>
              </div>
              <p className="text-xs text-[#94A3B8]">
                Multilingual Care Concierge · Scheduling, 6-Digit Lab Status &amp; Insurance Help
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {speechSynthesisSupported && (
              <button
                type="button"
                onClick={() => {
                  setAutoSpeakReply((prev) => !prev);
                  if (autoSpeakReply) window.speechSynthesis.cancel();
                }}
                className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors whitespace-nowrap shrink-0 ${
                  autoSpeakReply
                    ? 'border-[#38BDF8]/50 bg-[#38BDF8]/15 text-[#38BDF8]'
                    : 'border-[#334155] bg-[#111B2E] text-[#94A3B8] hover:text-[#E5EDF7]'
                }`}
              >
                {autoSpeakReply ? (
                  <Volume2 className="h-3.5 w-3.5" />
                ) : (
                  <VolumeX className="h-3.5 w-3.5" />
                )}
                <span>{autoSpeakReply ? 'Voice Readout On' : 'Voice Readout'}</span>
              </button>
            )}

            {mode === 'embedded' && (
              <button
                type="button"
                onClick={() => navigate('/medivoice')}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[#334155] bg-[#111B2E] px-2.5 py-1.5 text-xs font-medium text-[#E5EDF7] hover:border-[#2DD4BF] whitespace-nowrap shrink-0"
              >
                <Maximize2 className="h-3.5 w-3.5 text-[#2DD4BF]" />
                <span>Full Screen</span>
              </button>
            )}

            <button
              type="button"
              onClick={() => void handleResetSession()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#334155] bg-[#111B2E] px-2.5 py-1.5 text-xs font-medium text-[#94A3B8] transition-colors hover:border-[#38BDF8] hover:text-[#E5EDF7] whitespace-nowrap shrink-0"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              <span>Reset</span>
            </button>
          </div>
        </div>

        {/* Multilingual Selector Bar */}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-[#334155]/60">
          <div className="flex items-center gap-1.5 text-xs text-[#94A3B8]">
            <Globe className="h-3.5 w-3.5 text-[#38BDF8]" />
            <span>Language:</span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            {LANGUAGE_OPTIONS.map((lang) => {
              const isSelected = selectedLang === lang.code;
              return (
                <button
                  key={lang.code}
                  type="button"
                  onClick={() => {
                    setSelectedLang(lang.code);
                    setInputMessage(lang.samplePrompt);
                  }}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors whitespace-nowrap shrink-0 ${
                    isSelected
                      ? 'bg-[#2DD4BF] text-[#0B1020] font-semibold'
                      : 'bg-[#0B1020] text-[#94A3B8] hover:text-[#E5EDF7] border border-[#334155]'
                  }`}
                >
                  {lang.nativeLabel} ({lang.code.toUpperCase()})
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Conversation Transcript Area */}
      <div
        ref={scrollContainerRef}
        className={`flex-1 space-y-4 overflow-y-auto p-5 ${
          mode === 'fullscreen' ? 'max-h-[540px]' : 'max-h-[380px] min-h-[320px]'
        }`}
      >
        {turns.map((turn) => (
          <div
            key={turn.id}
            className={`flex flex-col ${
              turn.role === 'user' ? 'items-end' : 'items-start'
            }`}
          >
            <div
              className={`max-w-[88%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
                turn.role === 'user'
                  ? 'bg-[#2DD4BF] text-[#0B1020] font-medium'
                  : 'border border-[#334155] bg-[#0B1020] text-[#E5EDF7]'
              }`}
            >
              <p className="whitespace-pre-line">{turn.content}</p>

              {/* Explicit Confirmation Banner when Assistant Awaits Patient Confirmation */}
              {turn.role === 'assistant' && turn.requiresConfirmation && (
                <div className="mt-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200">
                  <div className="flex items-center gap-2 font-semibold text-amber-300">
                    <ShieldCheck className="h-4 w-4 shrink-0" />
                    <span>Explicit Patient Confirmation Required Before Booking</span>
                  </div>
                  {turn.draft?.selected_doctor_name && (
                    <p className="mt-1 text-amber-100/90">
                      Doctor: {turn.draft.selected_doctor_name} · Slot:{' '}
                      {turn.draft.selected_slot_time || turn.draft.selected_slot_id}
                    </p>
                  )}
                  <div className="mt-2.5 flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={isSending}
                      onClick={() => void handleSendMessage('Yes, confirm booking')}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-[#2DD4BF] px-3 py-1.5 text-xs font-semibold text-[#0B1020] hover:bg-[#2DD4BF]/90 disabled:opacity-50 whitespace-nowrap"
                    >
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      Confirm Appointment Booking
                    </button>
                    <button
                      type="button"
                      disabled={isSending}
                      onClick={() => void handleSendMessage('Cancel, choose a different slot')}
                      className="rounded-lg border border-[#334155] bg-[#111B2E] px-3 py-1.5 text-xs font-medium text-[#E5EDF7] hover:border-rose-400 whitespace-nowrap"
                    >
                      Choose Another Slot
                    </button>
                  </div>
                </div>
              )}

              {/* Tool Execution Trace Summary */}
              {turn.role === 'assistant' && turn.toolCalls && turn.toolCalls.length > 0 && (
                <div className="mt-2.5 flex flex-wrap items-center gap-2 border-t border-[#334155]/70 pt-2 font-mono text-[11px] text-[#38BDF8]">
                  <span>Executed Backend Tools:</span>
                  {turn.toolCalls.map((tc, i) => (
                    <span key={`${tc.tool_name}-${i}`} className="text-[#2DD4BF]">
                      {tc.tool_name} {tc.success ? '✓' : '✗'}
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div className="mt-1 flex items-center gap-2 px-1 text-[11px] text-[#94A3B8]">
              <span>{turn.role === 'user' ? 'Patient' : 'MediVoice AI'}</span>
              <span aria-hidden="true">·</span>
              <span className="font-mono tabular-nums">{turn.timestamp}</span>
              {turn.language && (
                <>
                  <span aria-hidden="true">·</span>
                  <span className="font-mono uppercase text-[#2DD4BF]">{turn.language}</span>
                </>
              )}
            </div>
          </div>
        ))}

        {isSending && (
          <div className="flex items-center gap-2.5 text-xs text-[#94A3B8]">
            <div className="h-2 w-2 rounded-full bg-[#2DD4BF] animate-ping" />
            <span>MediVoice AI is executing controlled hospital workflow tools...</span>
          </div>
        )}

        {chatError && (
          <div className="flex items-start gap-2.5 rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-200">
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-400 mt-0.5" />
            <span>{chatError}</span>
          </div>
        )}
      </div>

      {/* Suggested Workflow Starters */}
      <div className="border-t border-[#334155]/70 bg-[#0B1020]/60 px-5 py-2.5">
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <span className="shrink-0 text-[11px] font-medium text-[#94A3B8]">
            Suggested Questions:
          </span>
          {QUICK_WORKFLOW_PROMPTS.map((item) => (
            <button
              key={item.category}
              type="button"
              disabled={isSending}
              onClick={() => void handleSendMessage(item.prompt)}
              className="shrink-0 rounded-md border border-[#334155] bg-[#111B2E] px-2.5 py-1 text-xs text-[#E5EDF7] transition-colors hover:border-[#2DD4BF] hover:text-[#2DD4BF] disabled:opacity-50 whitespace-nowrap"
            >
              {item.category}
            </button>
          ))}
        </div>
      </div>

      {/* Composer Bar */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void handleSendMessage();
        }}
        className="border-t border-[#334155] bg-[#0B1020] p-4"
      >
        <div className="flex items-center gap-2">
          {speechRecognitionSupported && (
            <button
              type="button"
              onClick={handleToggleMic}
              aria-label={isListening ? 'Stop voice input' : 'Start voice input'}
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border transition-colors ${
                isListening
                  ? 'border-rose-500 bg-rose-500/20 text-rose-300'
                  : 'border-[#334155] bg-[#111B2E] text-[#38BDF8] hover:border-[#38BDF8]'
              }`}
            >
              {isListening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
            </button>
          )}

          <input
            type="text"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            placeholder="Ask in English, తెలుగు, हिन्दी, தமிழ், or ಕನ್ನಡ..."
            aria-label="Message MediVoice AI"
            className="h-10 flex-1 rounded-lg border border-[#334155] bg-[#111B2E] px-3.5 text-sm text-[#E5EDF7] placeholder-[#94A3B8]/60 focus:border-[#2DD4BF] focus:outline-none"
          />

          <button
            type="submit"
            disabled={isSending || !inputMessage.trim()}
            className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-lg bg-[#2DD4BF] px-4 text-xs font-semibold text-[#0B1020] transition-colors hover:bg-[#2DD4BF]/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#38BDF8] disabled:opacity-50 whitespace-nowrap"
          >
            <Send className="h-3.5 w-3.5" />
            <span>Send</span>
          </button>
        </div>

        {/* Safety Boundary Note */}
        <div className="mt-2.5 flex items-center justify-between text-[11px] text-[#94A3B8]">
          <span>
            Routine hospital operations assistant · Explicit patient confirmation required before booking
          </span>
        </div>
      </form>
    </div>
  );
};
