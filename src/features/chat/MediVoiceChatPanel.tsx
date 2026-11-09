import React, { useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  Code2,
  Globe,
  Loader2,
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

function base64ToBlob(base64: string, mimeType = 'audio/wav'): Blob {
  const binaryString = atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return new Blob([bytes], { type: mimeType });
}

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
  const [voiceLanguage, setVoiceLanguage] = useState<SupportedLanguage>('te');
  const [conversationStep, setConversationStep] = useState<string>('GREETING');
  const [confirmationStatus, setConfirmationStatus] = useState<string>('NONE');
  const [requiresConfirmation, setRequiresConfirmation] = useState<boolean>(false);
  const [draft, setDraft] = useState<BookingDraftState>({
    patient_reference: activePatientRef,
  });
  const [toolTraces, setToolTraces] = useState<ToolCallTrace[]>([]);
  const [bookedResult, setBookedResult] = useState<Record<string, unknown> | null>(null);
  const [showInspector, setShowInspector] = useState<boolean>(false);

  // Gnani AI Voice Pipeline State & Refs
  const [speechSupported, setSpeechSupported] = useState<boolean>(false);
  const [isListening, setIsListening] = useState<boolean>(false);
  const [isProcessingVoice, setIsProcessingVoice] = useState<boolean>(false);
  const [ttsEnabled, setTtsEnabled] = useState<boolean>(true);
  const [voiceError, setVoiceError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const currentAudioUrlRef = useRef<string | null>(null);
  const correlationIdRef = useRef<string>('');
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const hasMedia = Boolean(
      typeof navigator !== 'undefined' &&
      navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === 'function' &&
      typeof MediaRecorder !== 'undefined'
    );
    setSpeechSupported(hasMedia);
  }, []);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages, isSending, isProcessingVoice]);

  // Clean up recording and playback resources on unmount
  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        try {
          mediaRecorderRef.current.stop();
        } catch {
          // ignore
        }
        mediaRecorderRef.current = null;
      }
      if (audioStreamRef.current) {
        audioStreamRef.current.getTracks().forEach((track) => track.stop());
        audioStreamRef.current = null;
      }
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause();
        audioPlayerRef.current = null;
      }
      if (currentAudioUrlRef.current) {
        URL.revokeObjectURL(currentAudioUrlRef.current);
        currentAudioUrlRef.current = null;
      }
    };
  }, []);

  const playAudioBlob = (blob: Blob) => {
    try {
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause();
        audioPlayerRef.current = null;
      }
      if (currentAudioUrlRef.current) {
        URL.revokeObjectURL(currentAudioUrlRef.current);
        currentAudioUrlRef.current = null;
      }
      const url = URL.createObjectURL(blob);
      currentAudioUrlRef.current = url;
      const audio = new Audio(url);
      audioPlayerRef.current = audio;
      audio.onended = () => {
        if (currentAudioUrlRef.current === url) {
          URL.revokeObjectURL(url);
          currentAudioUrlRef.current = null;
        }
        if (audioPlayerRef.current === audio) {
          audioPlayerRef.current = null;
        }
      };
      audio.onerror = () => {
        if (currentAudioUrlRef.current === url) {
          URL.revokeObjectURL(url);
          currentAudioUrlRef.current = null;
        }
        if (audioPlayerRef.current === audio) {
          audioPlayerRef.current = null;
        }
      };
      void audio.play().catch((err) => {
        console.warn('Audio playback error or deferred by browser:', err);
      });
    } catch (err) {
      console.warn('Failed to play audio:', err);
    }
  };

  const speakAssistantReply = async (text: string, lang: SupportedLanguage) => {
    if (!ttsEnabled) return;
    try {
      const blob = await medivoiceApi.synthesizeSpeech(text, lang);
      playAudioBlob(blob);
    } catch (err) {
      console.warn('Gnani Timbre speech synthesis failed:', err);
    }
  };

  const toggleVoiceInput = async () => {
    if (!speechSupported) return;
    if (isListening) {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        try {
          mediaRecorderRef.current.stop();
        } catch {
          // ignore
        }
      }
      return;
    }

    setVoiceError(null);
    setVoiceLanguage('te');
    setActiveLanguage('en');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      audioStreamRef.current = stream;

      let mimeType = 'audio/webm';
      if (typeof MediaRecorder.isTypeSupported === 'function') {
        if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
          mimeType = 'audio/webm;codecs=opus';
        } else if (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) {
          mimeType = 'audio/ogg;codecs=opus';
        } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
          mimeType = 'audio/mp4';
        }
      }

      const mediaRecorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        setIsListening(false);
        if (audioStreamRef.current) {
          audioStreamRef.current.getTracks().forEach((track) => track.stop());
          audioStreamRef.current = null;
        }

        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        audioChunksRef.current = [];

        if (audioBlob.size < 500) {
          setVoiceError('Speech recording was too short. Please speak clearly into your microphone.');
          return;
        }

        setIsProcessingVoice(true);
        const nowLabel = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const correlationId =
          typeof crypto !== 'undefined' && 'randomUUID' in crypto
            ? crypto.randomUUID()
            : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
        correlationIdRef.current = correlationId;

        try {
          const response = await medivoiceApi.sendVoiceTurn(audioBlob, {
            sessionId,
            patientReference: activePatientRef,
            language: voiceLanguage || 'te',
            correlationId,
          });

          const userTranscript = (response.transcript || '').trim();
          const assistantReply = (response.assistant_reply || response.reply || '').trim();

          if (userTranscript) {
            const userMsg: ChatMessageItem = {
              id: `user-${Date.now()}`,
              role: 'user',
              content: userTranscript,
              timestamp: nowLabel,
            };
            setMessages((prev) => [...prev, userMsg]);
          }

          setSessionId(response.session_id);
          if (response.language) {
            setActiveLanguage(response.language as SupportedLanguage);
            setVoiceLanguage(response.language as SupportedLanguage);
          }
          setConversationStep(response.conversation_step || response.step);
          setConfirmationStatus(response.confirmation_status);
          setRequiresConfirmation(Boolean(response.requires_confirmation));
          setDraft(response.draft);

          if (response.tool_calls && response.tool_calls.length > 0) {
            setToolTraces((prev) => [...(response.tool_calls as ToolCallTrace[]), ...prev].slice(0, 20));
          }

          if (response.booked_appointment) {
            setBookedResult(response.booked_appointment);
            await refreshOperationalData();
          }

          const assistantMsg: ChatMessageItem = {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content: assistantReply,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            step: response.conversation_step || response.step,
            requiresConfirmation: Boolean(response.requires_confirmation),
          };
          setMessages((prev) => [...prev, assistantMsg]);

          if (response.audio_base64 && ttsEnabled) {
            const audioOut = base64ToBlob(
              response.audio_base64,
              response.audio_content_type || 'audio/wav'
            );
            playAudioBlob(audioOut);
          }
        } catch (err: unknown) {
          console.error('Voice turn processing error:', err);
          let safeMessage = 'Voice processing failed. Please try speaking again or use text chat.';
          if (err instanceof ApiError) {
            if (err.status === 422) {
              safeMessage = 'No clear speech was recognized in the audio. Please speak clearly into your microphone.';
            } else if (err.status === 502) {
              safeMessage = 'Gnani voice service temporarily unavailable. You can continue via text chat.';
            } else if (err.status === 504 || err.status === 408) {
              safeMessage = 'Voice request timed out. Please try speaking again.';
            } else {
              safeMessage = err.message || safeMessage;
            }
          }
          setVoiceError(safeMessage);
          setMessages((prev) => [
            ...prev,
            {
              id: `err-${Date.now()}`,
              role: 'assistant',
              content: safeMessage,
              timestamp: nowLabel,
              isError: true,
            },
          ]);
        } finally {
          setIsProcessingVoice(false);
        }
      };

      mediaRecorder.start(200);
      setIsListening(true);
    } catch (err: unknown) {
      console.error('Microphone initialization error:', err);
      setIsListening(false);
      const errName = (err as { name?: string })?.name;
      if (errName === 'NotAllowedError' || errName === 'PermissionDeniedError') {
        setVoiceError('Microphone permission was denied. Please allow microphone access in your browser address bar.');
      } else if (errName === 'NotFoundError' || errName === 'DevicesNotFoundError') {
        setVoiceError('No microphone was found. Please connect a microphone and try again.');
      } else {
        setVoiceError('Failed to access microphone. Please check your browser audio settings.');
      }
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
      void speakAssistantReply(response.assistant_reply, response.language);
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
    setVoiceError(null);
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
                Gnani Prisma STT • Gnani Timbre TTS • Explicit booking confirmation • 5 Indian languages
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
                    height: isSending || isListening || isProcessingVoice ? `${height}px` : '8px',
                  }}
                  className={`w-1 rounded-full transition-all duration-300 ${
                    isListening
                      ? 'bg-rose-400 animate-pulse'
                      : isProcessingVoice
                      ? 'bg-[#2DD4BF] animate-pulse'
                      : isSending
                      ? 'bg-[#38BDF8] animate-pulse'
                      : 'bg-[#334155]'
                  }`}
                />
              ))}
              <span className="ml-1.5 font-mono text-[10px] text-[#94A3B8]">
                {isListening ? 'RECORDING' : isProcessingVoice ? 'GNANI AI' : isSending ? 'ROUTING' : 'READY'}
              </span>
            </div>

            <button
              type="button"
              onClick={() => setTtsEnabled((prev) => !prev)}
              title={ttsEnabled ? 'Mute voice readout' : 'Enable voice readout (Gnani Timbre TTS)'}
              className={`rounded-lg border p-2 text-xs transition-colors ${
                ttsEnabled
                  ? 'border-[#2DD4BF] bg-[#2DD4BF]/15 text-[#2DD4BF]'
                  : 'border-[#334155] bg-[#111B2E] text-[#94A3B8] hover:text-[#E5EDF7]'
              }`}
            >
              {ttsEnabled ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
            </button>

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
              onClick={handleResetSession}
              title="Reset conversation session"
              className="rounded-lg border border-[#334155] bg-[#111B2E] p-2 text-xs text-[#94A3B8] hover:border-rose-500/50 hover:text-rose-400 transition-colors"
            >
              <RotateCcw className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Operational Context Sub-bar */}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[#334155]/60 pt-3 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-[#94A3B8]">Patient Ref:</span>
            <input
              type="text"
              aria-label="Synthetic Patient Reference"
              value={activePatientRef}
              onChange={(e) => setActivePatientRef(e.target.value)}
              placeholder="e.g. PAT-2024-9182"
              className="w-36 rounded-md border border-[#334155] bg-[#111B2E] px-2 py-0.5 font-mono text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
            />
          </div>

          <div className="flex items-center gap-3 text-[11px]">
            <div className="flex items-center gap-1">
              <span className="text-[#94A3B8]">Step:</span>
              <span className="font-mono font-semibold text-[#38BDF8]">{conversationStep}</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-[#94A3B8]">Confirmation:</span>
              <span
                className={`font-mono font-semibold ${
                  confirmationStatus === 'CONFIRMED'
                    ? 'text-emerald-400'
                    : confirmationStatus === 'PENDING'
                    ? 'text-amber-400'
                    : 'text-[#94A3B8]'
                }`}
              >
                {confirmationStatus}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Voice Warning Banner */}
      {voiceError && (
        <div className="bg-rose-500/10 border-b border-rose-500/30 px-5 py-2.5 text-xs text-rose-300 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
            <span>{voiceError}</span>
          </div>
          <button
            type="button"
            onClick={() => setVoiceError(null)}
            className="text-rose-400 hover:text-rose-200 text-xs font-semibold"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* State Inspector Drawer */}
      {showInspector && (
        <div className="border-b border-[#334155] bg-[#0B1020] p-4 text-xs font-mono text-[#94A3B8] space-y-3">
          <div className="flex items-center justify-between text-[#E5EDF7]">
            <span className="font-bold uppercase tracking-wider text-[11px] text-[#2DD4BF]">
              Reasoning State & Extracted Draft
            </span>
            <span>Session: {sessionId}</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="rounded-lg border border-[#334155] bg-[#111B2E] p-3 space-y-1">
              <span className="text-[#38BDF8] font-semibold block mb-1">Extracted Booking Draft:</span>
              <pre className="text-[11px] overflow-x-auto text-[#E5EDF7]">
                {JSON.stringify(draft, null, 2)}
              </pre>
            </div>

            <div className="rounded-lg border border-[#334155] bg-[#111B2E] p-3 space-y-1">
              <span className="text-[#38BDF8] font-semibold block mb-1">
                Recent Allowlisted Tool Executions:
              </span>
              <div className="max-h-32 overflow-y-auto space-y-1 text-[11px]">
                {toolTraces.length === 0 ? (
                  <span className="text-[#64748B]">No tool executions in this turn yet.</span>
                ) : (
                  toolTraces.map((trace, i) => (
                    <div key={i} className="flex items-center justify-between border-b border-[#334155]/40 py-0.5">
                      <span className="text-emerald-400">{trace.tool_name}</span>
                      <span className="text-[#64748B]">
                        {trace.success ? '✓ SUCCESS' : `✗ ${trace.error || 'FAILED'}`}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Chat Messages Timeline */}
      <div className="h-96 overflow-y-auto p-5 space-y-4">
        {messages.map((msg) => {
          const isUser = msg.role === 'user';
          return (
            <div
              key={msg.id}
              className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} space-y-1`}
            >
              <div className="flex items-center gap-2 text-[11px] text-[#94A3B8]">
                <span>{isUser ? `Patient (${activePatientRef})` : 'MediVoice AI'}</span>
                <span>•</span>
                <span>{msg.timestamp}</span>
              </div>

              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                  isUser
                    ? 'bg-[#2DD4BF] text-[#0B1020] font-medium rounded-br-none shadow-md'
                    : msg.isError
                    ? 'border border-rose-500/40 bg-rose-500/10 text-rose-200 rounded-bl-none'
                    : 'border border-[#334155] bg-[#1E293B] text-[#E5EDF7] rounded-bl-none shadow-md'
                }`}
              >
                <div className="whitespace-pre-wrap">{msg.content}</div>

                {msg.requiresConfirmation && (
                  <div className="mt-2.5 flex items-center gap-1.5 rounded-lg border border-amber-400/40 bg-amber-400/10 px-2.5 py-1 text-xs text-amber-200">
                    <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-amber-400" />
                    <span>Explicit booking confirmation required before reserving slot.</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {isSending && (
          <div className="flex items-center gap-2 text-xs text-[#38BDF8] animate-pulse">
            <Bot className="h-4 w-4 animate-spin" />
            <span>MediVoice AI is querying hospital backend tools...</span>
          </div>
        )}

        {isProcessingVoice && (
          <div className="flex items-center gap-2 text-xs text-[#2DD4BF] animate-pulse">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>Processing voice recording via Gnani Prisma STT & AI Reasoning...</span>
          </div>
        )}

        <div ref={transcriptEndRef} />
      </div>

      {/* Language Quick Selector & Multilingual Samples */}
      <div className="border-t border-[#334155] bg-[#0B1020]/60 px-5 py-2.5 flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-1.5 text-[#94A3B8]">
          <Globe className="h-3.5 w-3.5 text-[#38BDF8]" />
          <span>Active Language:</span>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {(Object.keys(LANGUAGE_META) as SupportedLanguage[]).map((langKey) => (
            <button
              key={langKey}
              type="button"
              onClick={() => setActiveLanguage(langKey)}
              className={`rounded-md px-2 py-0.5 text-xs font-medium transition-colors ${
                activeLanguage === langKey
                  ? 'border border-[#2DD4BF]/60 bg-[#2DD4BF]/20 text-[#2DD4BF]'
                  : 'border border-[#334155] bg-[#111B2E] text-[#94A3B8] hover:text-[#E5EDF7]'
              }`}
            >
              {LANGUAGE_META[langKey].label}
            </button>
          ))}
        </div>
      </div>

      {/* Quick Prompts Bar */}
      <div className="border-t border-[#334155]/60 bg-[#0B1020]/40 px-5 py-2 flex items-center gap-2 overflow-x-auto text-xs">
        <span className="shrink-0 font-mono text-[10px] uppercase text-[#64748B]">Quick Try:</span>
        {QUICK_SCENARIO_PROMPTS.map((item, idx) => (
          <button
            key={idx}
            type="button"
            disabled={isSending || isListening || isProcessingVoice}
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
            disabled={isProcessingVoice || isSending}
            onClick={toggleVoiceInput}
            title={
              isListening
                ? 'Stop recording and process voice via Gnani AI'
                : isProcessingVoice
                ? 'Processing voice turn...'
                : `Speak with Gnani AI in ${LANGUAGE_META[activeLanguage]?.label || activeLanguage}`
            }
            aria-label={isListening ? 'Stop recording' : 'Speak with Gnani AI'}
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border transition-all ${
              isListening
                ? 'border-rose-500 bg-rose-500/20 text-rose-300 ring-2 ring-rose-400 animate-pulse'
                : isProcessingVoice
                ? 'border-[#2DD4BF] bg-[#2DD4BF]/20 text-[#2DD4BF] cursor-wait'
                : 'border-[#334155] bg-[#111B2E] text-[#38BDF8] hover:border-[#38BDF8]'
            } disabled:opacity-50`}
          >
            {isProcessingVoice ? (
              <Loader2 className="h-4 w-4 animate-spin text-[#2DD4BF]" />
            ) : isListening ? (
              <MicOff className="h-4 w-4" />
            ) : (
              <Mic className="h-4 w-4" />
            )}
          </button>
        )}

        <input
          type="text"
          value={input}
          disabled={isSending || isListening || isProcessingVoice}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            isListening
              ? 'Listening... Click the red microphone button to finish speaking'
              : isProcessingVoice
              ? 'Processing speech via Gnani AI...'
              : 'Ask in English, తెలుగు, தமிழ், ಕನ್ನಡ, or हिन्दी (or click the microphone)...'
          }
          className="flex-1 rounded-xl border border-[#334155] bg-[#111B2E] px-4 py-2.5 text-sm text-[#E5EDF7] placeholder-[#94A3B8]/60 focus:border-[#2DD4BF] focus:outline-none disabled:opacity-75"
        />

        <button
          type="submit"
          disabled={isSending || isListening || isProcessingVoice || !input.trim()}
          className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-xl bg-[#2DD4BF] px-4 text-xs font-semibold text-[#0B1020] transition-colors hover:bg-[#2DD4BF]/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#38BDF8] disabled:opacity-50"
        >
          <Send className="h-4 w-4" />
          <span>Send</span>
        </button>
      </form>
    </div>
  );
};
