import React, { useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  ArrowLeft,
  Bot,
  CheckCircle2,
  ChevronDown,
  Globe,
  Loader2,
  Maximize2,
  Mic,
  Minimize2,
  Radio,
  RotateCcw,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Volume2,
  VolumeX,
  XCircle,
  Calendar,
  Clock,
  User,
  Building2,
  Phone,
  MessageSquare,
  Heart,
} from 'lucide-react';
import { usePlatform } from '../../app/PlatformContext';
import { ApiError, medivoiceApi } from '../../services/api';
import { rememberPatientAppointmentReference } from '../../services/patientAppointmentAccess';
import {
  BookingDraftState,
  SupportedLanguage,
  ToolCallTrace,
  VoiceToolExecutionResult,
} from '../../types/api';
import { MediVoiceVoicePanel } from './MediVoiceVoicePanel';
import { shouldAutoSpeakChatTurn, TurnAudioCache } from './turnSpeech';

interface ChatTurn {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  language?: SupportedLanguage;
  step?: string;
  requiresConfirmation?: boolean;
  audioUrl?: string;
  draft?: BookingDraftState;
  toolCalls?: Array<ToolCallTrace | VoiceToolExecutionResult>;
  isError?: boolean;
  suggestedOptions?: Array<{ label: string; value: string }>;
  bookedAppointment?: Record<string, any>;
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

const SUGGESTED_QUESTIONS = [
  {
    label: 'Find a Doctor',
    prompt: 'Which cardiologists and specialists are available at Aarogya One Hospital?',
  },
  {
    label: 'Book an Appointment',
    prompt: 'I want to book an appointment with a General Medicine doctor.',
  },
  {
    label: 'Check Lab Report',
    prompt: 'Help me check my lab report status using my 6-digit verification code.',
  },
  {
    label: 'Insurance Help',
    prompt: 'Which insurance providers and cashless plans does Aarogya One Hospital accept?',
  },
  {
    label: 'Hospital Services',
    prompt: 'What clinical departments, emergency services, and OPD facilities are available?',
  },
];

interface MediVoiceChatExperienceProps {
  mode?: 'embedded' | 'fullscreen' | 'fullwidth';
}

function decodeHtmlEntities(str: string): string {
  if (!str) return '';
  return str
    .replace(/&#x([0-9a-fA-F]+);/g, (_, hex) => {
      try {
        const code = parseInt(hex, 16);
        return String.fromCodePoint(code);
      } catch {
        return _;
      }
    })
    .replace(/&#([0-9]+);/g, (_, dec) => {
      try {
        const code = parseInt(dec, 10);
        return String.fromCodePoint(code);
      } catch {
        return _;
      }
    })
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'");
}

function detectClientLanguage(text: string, currentLang: SupportedLanguage): SupportedLanguage {
  if (!text) return currentLang;
  let te = 0, ta = 0, kn = 0, hi = 0;
  for (let i = 0; i < text.length; i++) {
    const cp = text.charCodeAt(i);
    if (cp >= 0x0C00 && cp <= 0x0C7F) te++;
    else if (cp >= 0x0B80 && cp <= 0x0BFF) ta++;
    else if (cp >= 0x0C80 && cp <= 0x0CFF) kn++;
    else if (cp >= 0x0900 && cp <= 0x097F) hi++;
  }
  if (te > 0 && te >= ta && te >= kn && te >= hi) return 'te';
  if (ta > 0 && ta >= te && ta >= kn && ta >= hi) return 'ta';
  if (kn > 0 && kn >= te && kn >= ta && kn >= hi) return 'kn';
  if (hi > 0 && hi >= te && hi >= ta && hi >= kn) return 'hi';
  return currentLang;
}

function renderFormattedMessage(text: string) {
  if (!text) return null;
  const decodedText = decodeHtmlEntities(text);
  const paragraphs = decodedText.split(/\n\n+/);
  return (
    <div className="space-y-2">
      {paragraphs.map((p, pIdx) => {
        const lines = p.split('\n');
        return (
          <div key={pIdx} className="space-y-1">
            {lines.map((line, lIdx) => {
              const trimmed = line.trim();
              const isBullet =
                trimmed.startsWith('•') ||
                trimmed.startsWith('- ') ||
                trimmed.startsWith('* ');
              const cleanLine = isBullet
                ? trimmed.replace(/^[•\-\*]\s*/, '')
                : trimmed;

              const parts = cleanLine.split(/(\*\*[^*]+\*\*)/g);
              const renderedParts = parts.map((part, partIdx) => {
                if (part.startsWith('**') && part.endsWith('**')) {
                  return (
                    <strong
                      key={partIdx}
                      className="font-semibold text-[#17233B]"
                    >
                      {part.slice(2, -2)}
                    </strong>
                  );
                }
                return part;
              });

              if (isBullet) {
                return (
                  <div
                    key={lIdx}
                    className="flex items-start gap-2 pl-1 py-0.5"
                  >
                    <span className="text-[#7657FF] font-bold text-xs mt-0.5 shrink-0">
                      •
                    </span>
                    <span className="flex-1 text-[#17233B]">{renderedParts}</span>
                  </div>
                );
              }

              return (
                <p key={lIdx} className="min-h-[1.25rem] text-[#17233B]">
                  {renderedParts}
                </p>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

const maskPhoneNumber = (phone?: string): string => {
  if (!phone) return '+91 ******3210';
  const clean = phone.replace(/\s+/g, '');
  if (clean.length <= 4) return `******${clean}`;
  const last4 = clean.slice(-4);
  const prefix = clean.startsWith('+91') ? '+91 ' : (clean.startsWith('+') ? clean.slice(0, 3) + ' ' : '');
  return `${prefix}******${last4}`;
};

const LOCALE_BY_LANGUAGE: Record<SupportedLanguage, string> = {
  te: 'te-IN',
  hi: 'hi-IN',
  ta: 'ta-IN',
  kn: 'kn-IN',
  en: 'en-IN',
};

const formatAppointmentDateTime = (dtStr?: string, lang: SupportedLanguage = 'en'): string => {
  if (!dtStr) return 'Confirmed Slot';
  try {
    const dt = new Date(dtStr);
    if (isNaN(dt.getTime())) return dtStr;
    const locale = LOCALE_BY_LANGUAGE[lang] || 'en-IN';
    return dt.toLocaleString(locale, {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return dtStr;
  }
};

const LOCALIZED_COMPLETION_NOTICES: Record<SupportedLanguage, { sms: string; thankYou: string }> = {
  te: {
    sms: 'మీ అపాయింట్మెంట్ వివరాలు మీ రిజిస్టర్ చేసిన మొబైల్ నంబర్కు SMS ద్వారా పంపబడతాయి.',
    thankYou: 'ఆరోగ్య వన్ హాస్పిటల్ను ఎంచుకున్నందుకు ధన్యవాదాలు. మీకు త్వరగా కోలుకోవాలని కోరుకుంటున్నాము. జాగ్రత్తగా ఉండండి!',
  },
  en: {
    sms: 'Your appointment details will be sent to your registered mobile number via SMS.',
    thankYou: 'Thank you for choosing Aarogya One Hospital. We wish you a speedy recovery and good health!',
  },
  hi: {
    sms: 'आपके अपॉइंटमेंट का विवरण आपके पंजीकृत मोबाइल नंबर पर एसएमएस द्वारा भेज दिया जाएगा।',
    thankYou: 'आरोग्य वन अस्पताल चुनने के लिए धन्यवाद। हम आपके शीघ्र स्वस्थ होने की कामना करते हैं। अपना ध्यान रखें!',
  },
  ta: {
    sms: 'உங்கள் அப்பாயிண்ட்மென்ட் விவரங்கள் பதிவுசெய்யப்பட்ட மொபைல் எண்ணிற்கு எஸ்எம்எஸ் மூலம் அனுப்பப்படும்.',
    thankYou: 'ஆரோக்கியா ஒன் மருத்துவமனையைத் தேர்ந்தெடுத்ததற்கு நன்றி. நீங்கள் விரைவில் குணமடைய வாழ்த்துகிறோம்!',
  },
  kn: {
    sms: 'ನಿಮ್ಮ ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್ ವಿವರಗಳನ್ನು మీ ನೋಂದಾಯಿತ ಮೊಬೈಲ್ ಸಂಖ್ಯೆಗೆ ಎಸ್‌ಎಂಎಸ್ ಮೂಲಕ ಕಳುಹಿಸಲಾಗುತ್ತದೆ.',
    thankYou: 'ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆಯನ್ನು ಆಯ್ಕೆ ಮಾಡಿದ್ದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು. ನೀವು ಶೀಘ್ರವಾಗಿ ಚೇತರಿಸಿಕೊಳ್ಳಬೇಕೆಂದು ನಾವು ಬಯಸುತ್ತೇವೆ!',
  },
};

export const MediVoiceChatExperience: React.FC<MediVoiceChatExperienceProps> = ({
  mode = 'embedded',
}) => {
  const {
    activePatientRef,
    navigate,
    refreshOperationalData,
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

  // Gnani Prisma STT & Timbre TTS Voice Integration
  const [showVoicePanel, setShowVoicePanel] = useState<boolean>(false);
  const [playingTurnId, setPlayingTurnId] = useState<string | null>(null);
  const [synthesizingTurnId, setSynthesizingTurnId] = useState<string | null>(null);
  const turnAudioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const playingTurnIdRef = useRef<string | null>(null);
  const synthesizingTurnIdRef = useRef<string | null>(null);
  const [turnAudioCache] = useState(() => new TurnAudioCache());
  const lastUserMessageRef = useRef<string>('');

  const [turns, setTurns] = useState<ChatTurn[]>([
    {
      id: 'welcome-turn',
      role: 'assistant',
      content:
        'Welcome to Aarogya One Hospital. I am MediVoice AI, your multilingual care concierge. I can help you find specialists, check open appointment slots, verify your 6-digit laboratory report status, or review hospital insurance plans in English, Telugu, Hindi, Tamil, or Kannada. How can I assist you today?',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      language: 'en',
      step: 'READY',
    },
  ]);

  const scrollContainerRef = useRef<HTMLDivElement | null>(null);

  const scrollToBottom = () => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [turns, isSending, chatError]);

  // Clean up any playing audio on unmount
  useEffect(() => {
    return () => {
      if (turnAudioPlayerRef.current) {
        turnAudioPlayerRef.current.pause();
        turnAudioPlayerRef.current = null;
      }
      turnAudioCache.dispose((audioUrl) => URL.revokeObjectURL(audioUrl));
    };
  }, [turnAudioCache]);

  const handlePlayTurnSpeech = async (turn: ChatTurn) => {
    if (playingTurnIdRef.current === turn.id) {
      if (turnAudioPlayerRef.current) {
        turnAudioPlayerRef.current.pause();
      }
      turnAudioCache.finishPlayback(turn.id);
      playingTurnIdRef.current = null;
      setPlayingTurnId(null);
      return;
    }
    if (synthesizingTurnIdRef.current || turnAudioCache.isPlaying(turn.id)) return;

    try {
      synthesizingTurnIdRef.current = turn.id;
      setSynthesizingTurnId(turn.id);
      const audioUrl = turn.audioUrl || await turnAudioCache.getOrCreate(turn.id, async () => {
        const audioBlob = await medivoiceApi.synthesizeSpeech(
          turn.content,
          turn.language || selectedLang
        );
        return URL.createObjectURL(audioBlob);
      });
      turnAudioCache.remember(turn.id, audioUrl);
      setTurns((prev) => prev.map((item) => item.id === turn.id ? { ...item, audioUrl } : item));

      if (!turnAudioCache.beginPlayback(turn.id)) return;

      if (turnAudioPlayerRef.current) {
        turnAudioPlayerRef.current.pause();
      }
      if (playingTurnIdRef.current) turnAudioCache.finishPlayback(playingTurnIdRef.current);

      const audio = new Audio(audioUrl);
      turnAudioPlayerRef.current = audio;
      playingTurnIdRef.current = turn.id;
      setPlayingTurnId(turn.id);

      audio.onplay = () => {
        setPlayingTurnId(turn.id);
        setSynthesizingTurnId(null);
      };

      audio.onended = () => {
        turnAudioCache.finishPlayback(turn.id);
        if (playingTurnIdRef.current === turn.id) playingTurnIdRef.current = null;
        setPlayingTurnId((current) => current === turn.id ? null : current);
      };

      audio.onerror = () => {
        turnAudioCache.finishPlayback(turn.id);
        if (playingTurnIdRef.current === turn.id) playingTurnIdRef.current = null;
        setPlayingTurnId((current) => current === turn.id ? null : current);
        setSynthesizingTurnId((current) => current === turn.id ? null : current);
      };

      await audio.play();
    } catch (err) {
      console.warn('Speech synthesis failed:', err);
      turnAudioCache.finishPlayback(turn.id);
      if (playingTurnIdRef.current === turn.id) playingTurnIdRef.current = null;
      setSynthesizingTurnId((current) => current === turn.id ? null : current);
      setPlayingTurnId((current) => current === turn.id ? null : current);
    } finally {
      if (synthesizingTurnIdRef.current === turn.id) synthesizingTurnIdRef.current = null;
      setSynthesizingTurnId((current) => current === turn.id ? null : current);
    }
  };

  const handleVoiceTurnSuccess = async (result: {
    userTranscript: string;
    assistantReply: string;
    language: SupportedLanguage;
    draft?: BookingDraftState;
    toolCalls?: Array<ToolCallTrace | VoiceToolExecutionResult>;
    step?: string;
    requiresConfirmation?: boolean;
    audioBlob?: Blob;
    bookedAppointment?: Record<string, any>;
  }) => {
    const userTurn: ChatTurn = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: result.userTranscript,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      language: result.language,
    };

    const replyContent =
      result.assistantReply ||
      'Welcome to Aarogya One Hospital. How can I assist you with your health query today?';

    const assistantTurn: ChatTurn = {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: replyContent,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      language: result.language,
      step: result.step,
      requiresConfirmation: result.requiresConfirmation,
      audioUrl: result.audioBlob ? URL.createObjectURL(result.audioBlob) : undefined,
      draft: result.draft,
      toolCalls: result.toolCalls,
      bookedAppointment: result.bookedAppointment,
    };

    if (assistantTurn.audioUrl) turnAudioCache.remember(assistantTurn.id, assistantTurn.audioUrl);

    if (result.bookedAppointment?.appointment_id) {
      rememberPatientAppointmentReference(result.bookedAppointment.appointment_id);
      void refreshOperationalData();
    }

    setTurns((prev) => [...prev, userTurn, assistantTurn]);
    setChatError(null);

    if (result.language) {
      setSelectedLang(result.language);
    }

    if (result.toolCalls && result.toolCalls.length > 0) {
      await refreshOperationalData();
    }
  };

  const handleGreetingSpoken = (greetingText: string, lang: SupportedLanguage) => {
    setTurns((prev) => {
      // If user has already spoken/typed, do not inject a welcome greeting into an ongoing session
      if (prev.some((t) => t.role === 'user')) {
        return prev;
      }
      if (prev.length === 1 && prev[0].id === 'welcome-turn') {
        return [
          {
            id: 'welcome-turn',
            role: 'assistant',
            content: greetingText,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            language: lang,
            step: 'READY',
          },
        ];
      }
      const lastTurn = prev[prev.length - 1];
      if (lastTurn && lastTurn.content === greetingText) {
        return prev;
      }
      return [
        ...prev,
        {
          id: `greeting-${Date.now()}`,
          role: 'assistant',
          content: greetingText,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          language: lang,
          step: 'READY',
        },
      ];
    });
  };

  const handleSendMessage = async (textOverride?: string) => {
    const rawMessage = textOverride !== undefined ? textOverride : inputMessage;
    const messageToSend = rawMessage.trim();
    if (!messageToSend || isSending) return;

    if (textOverride === undefined) {
      setInputMessage('');
    }
    setChatError(null);
    lastUserMessageRef.current = messageToSend;

    const detectedInputLang = detectClientLanguage(messageToSend, selectedLang);
    const effectiveTurnLang = detectedInputLang !== 'en' ? detectedInputLang : selectedLang;

    const userTurn: ChatTurn = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: messageToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      language: effectiveTurnLang,
    };
    if (detectedInputLang !== 'en' && detectedInputLang !== selectedLang) {
      setSelectedLang(detectedInputLang);
    }

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

      // Defensively extract response content with fallback
      const replyContent =
        response.assistant_reply ||
        response.reply ||
        'Hello! Welcome to Aarogya One Hospital. How can I assist you today?';

      const isBookingDone =
        response.conversation_step === 'BOOKED' ||
        response.step === 'BOOKED' ||
        Boolean(response.booked_appointment);

      const assistantTurn: ChatTurn = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: replyContent,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        language: response.language || selectedLang,
        step: response.conversation_step || response.step,
        requiresConfirmation: Boolean(
          response.requires_confirmation ||
            response.confirmation_status === 'PENDING' ||
            response.conversation_step === 'AWAITING_CONFIRMATION'
        ),
        draft: response.draft,
        toolCalls: response.tool_calls || response.tool_trace,
        suggestedOptions: response.suggested_options,
        bookedAppointment: response.booked_appointment || undefined,
      };

      setTurns((prev) => [...prev, assistantTurn]);

      const bookedAppointmentId = response.booked_appointment?.appointment_id;
      if (typeof bookedAppointmentId === 'string') {
        rememberPatientAppointmentReference(bookedAppointmentId);
      }

      if (
        response.booked_appointment ||
        (response.tool_calls && response.tool_calls.length > 0)
      ) {
        await refreshOperationalData();
      }

      // Speak the final confirmation prompt as well as the completed booking response.
      if (shouldAutoSpeakChatTurn({
        isBookingDone,
        requiresConfirmation: assistantTurn.requiresConfirmation === true,
        voicePanelOpen: showVoicePanel,
      })) {
        void handlePlayTurnSpeech(assistantTurn);
      }
    } catch (err) {
      console.error('Chat error:', err);
      const msg =
        err instanceof ApiError
          ? err.message
          : 'Unable to connect to the MediVoice conversation service. Please verify your connection and tap Retry.';
      setChatError(msg);
    } finally {
      setIsSending(false);
    }
  };

  const handleRetryLastMessage = () => {
    if (lastUserMessageRef.current && !isSending) {
      setChatError(null);
      void handleSendMessage(lastUserMessageRef.current);
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
      // ignore
    }
    const freshSession = `sess-${Math.random().toString(36).slice(2, 10)}`;
    setSessionId(freshSession);
    setChatError(null);
    lastUserMessageRef.current = '';
    setTurns([
      {
        id: `welcome-${Date.now()}`,
        role: 'assistant',
        content:
          'Welcome to Aarogya One Hospital. I am MediVoice AI. Session has been reset. Tell me what symptoms or doctor specialty you need, your 6-digit laboratory verification code, or your insurance inquiry in English, Telugu, Hindi, Tamil, or Kannada.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        language: selectedLang,
        step: 'READY',
      },
    ]);
  };

  const isFullscreen = mode === 'fullscreen';
  const isFullWidth = mode === 'fullwidth';

  return (
    <div
      className={`assistant-panel flex flex-col rounded-[2.25rem] border border-violet-100/90 overflow-hidden shadow-xl shadow-violet-950/5 ${
        isFullscreen
          ? 'min-h-[calc(100vh-120px)] h-full'
          : isFullWidth
          ? 'min-h-[660px] h-[720px] lg:h-[760px] w-full'
          : 'h-[640px] md:h-[680px]'
      } bg-[#FAF9F6] text-[#17233B] relative`}
      role="region"
      aria-label="MediVoice AI Patient Care Assistant"
    >
      {/* =========================================================================
          Chat Header
          ========================================================================= */}
      <div className="shrink-0 border-b border-violet-100/80 bg-gradient-to-r from-[#FAF9FE] via-[#FFFFFF] to-[#F5F8FF] px-4 py-3.5 sm:px-6">
        <div className="max-w-5xl mx-auto flex flex-wrap items-center justify-between gap-3">
          {/* Logo & Identity */}
          <div className="flex items-center gap-3">
            {isFullscreen && (
              <button
                type="button"
                onClick={() => navigate('/')}
                className="inline-flex items-center gap-1.5 rounded-xl border border-violet-200/80 bg-white px-3 py-1.5 text-xs font-semibold text-[#17233B] hover:border-[#7657FF] hover:bg-violet-50/50 transition-all shadow-xs shrink-0"
              >
                <ArrowLeft className="h-3.5 w-3.5 text-[#7657FF]" />
                <span className="hidden sm:inline">Back to Website</span>
                <span className="sm:hidden">Back</span>
              </button>
            )}

            {/* Glowing Brand Avatar with Active Turquoise Dot */}
            <div className="relative shrink-0">
              <div className="assistant-orb flex h-11 w-11 items-center justify-center rounded-2xl shadow-md shadow-violet-500/20 text-white">
                <Sparkles className="h-5 w-5 animate-pulse text-white drop-shadow" />
              </div>
              <span
                className="absolute -bottom-0.5 -right-0.5 flex h-3 w-3 items-center justify-center rounded-full bg-white ring-2 ring-white"
                title="MediVoice AI Online"
              >
                <span className="h-2 w-2 rounded-full bg-[#25D9C3] animate-pulse" />
              </span>
            </div>

            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-display text-base font-bold text-[#17233B] tracking-tight">
                  MediVoice AI
                </h2>
                <span className="hidden sm:inline-block rounded-full bg-violet-100/80 px-2 py-0.5 text-[10px] font-bold text-[#7657FF]">
                  Care Concierge
                </span>
                <span className="text-[#61708A] text-xs">·</span>
                <span className="text-xs font-semibold text-[#7657FF]">
                  Aarogya One Hospital
                </span>
              </div>
              <p className="text-xs text-[#61708A] mt-0.5 hidden sm:block">
                Multilingual AI · Specialist Booking, 6-Digit Lab Reports & Cashless Insurance
              </p>
            </div>
          </div>

          {/* Action Buttons: Voice Panel Toggle, Fullscreen, Reset */}
          <div className="flex items-center gap-2 shrink-0">
            {/* Talk to MediVoice Voice Interaction Button */}
            <button
              type="button"
              onClick={() => setShowVoicePanel(true)}
              className="inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold transition-all shadow-xs bg-white border border-violet-200 text-[#7657FF] hover:border-[#7657FF] hover:bg-violet-50/60 cursor-pointer"
              aria-label="Open full-screen voice assistant"
              title="Speak with MediVoice using Gnani Prisma STT & Timbre TTS"
            >
              <Radio className="h-3.5 w-3.5 text-[#7657FF]" />
              <span>Talk to MediVoice</span>
              <span className="hidden md:inline-block rounded-full bg-violet-100 px-1.5 py-0.2 text-[9px] font-bold text-[#7657FF]">
                Voice AI
              </span>
            </button>

            {/* Full Screen Toggle */}
            {!isFullscreen ? (
              <button
                type="button"
                onClick={() => navigate('/medivoice')}
                className="inline-flex items-center gap-1.5 rounded-xl border border-violet-200/80 bg-white px-2.5 py-1.5 text-xs font-medium text-[#17233B] hover:border-[#7657FF] hover:text-[#7657FF] transition-all shadow-xs shrink-0 cursor-pointer"
                title="Expand to Dedicated Page View"
              >
                <Maximize2 className="h-3.5 w-3.5 text-[#4387FF]" />
                <span className="hidden sm:inline">Full Screen</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={() => navigate('/')}
                className="inline-flex items-center gap-1.5 rounded-xl border border-violet-200/80 bg-white px-2.5 py-1.5 text-xs font-medium text-[#17233B] hover:border-[#7657FF] hover:text-[#7657FF] transition-all shadow-xs shrink-0 cursor-pointer"
                title="Exit Full Screen View"
              >
                <Minimize2 className="h-3.5 w-3.5 text-[#4387FF]" />
                <span className="hidden sm:inline">Exit Full Screen</span>
              </button>
            )}

            {/* Reset Session Button */}
            <button
              type="button"
              onClick={() => void handleResetSession()}
              className="inline-flex items-center gap-1 rounded-xl border border-violet-200/80 bg-white px-2.5 py-1.5 text-xs font-medium text-[#61708A] hover:border-violet-400 hover:text-[#17233B] transition-all shadow-xs shrink-0 cursor-pointer"
              title="Start a fresh conversation"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Reset</span>
            </button>
          </div>
        </div>

        {/* Multilingual Selector Pills */}
        <div className="max-w-5xl mx-auto mt-2.5 flex flex-wrap items-center justify-between gap-2 pt-2.5 border-t border-violet-100/70">
          <div className="flex items-center gap-1.5 text-xs text-[#61708A]">
            <Globe className="h-3.5 w-3.5 text-[#4387FF]" />
            <span className="font-medium">Language:</span>
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
                  className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-all whitespace-nowrap shrink-0 cursor-pointer ${
                    isSelected
                      ? 'bg-[#7657FF] text-white font-semibold shadow-xs'
                      : 'bg-white text-[#61708A] hover:text-[#17233B] border border-violet-100 hover:border-violet-300'
                  }`}
                >
                  <span>{lang.nativeLabel}</span>{' '}
                  <span className="opacity-75">({lang.code.toUpperCase()})</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* =========================================================================
          Conversation Transcript Area
          ========================================================================= */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto bg-[radial-gradient(ellipse_at_top,_#F9F8FE,_#FAF9F6_60%)] p-4 sm:p-6"
      >
        <div className="max-w-4xl mx-auto space-y-4">
          {turns.map((turn, idx) => {
            const isUser = turn.role === 'user';

            return (
              <div
                key={turn.id}
                className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} transition-opacity duration-200`}
              >
                <div className={`flex items-start gap-2.5 max-w-[92%] sm:max-w-[85%] ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
                {/* Assistant Avatar */}
                {!isUser && (
                  <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-[#7657FF] to-[#4387FF] text-white shadow-xs">
                    <Bot className="h-4 w-4" />
                  </div>
                )}

                <div className="flex flex-col">
                  {/* Message Bubble */}
                  <div
                    className={`rounded-2xl px-4.5 py-3.5 text-sm leading-relaxed transition-all ${
                      isUser
                        ? 'bg-gradient-to-r from-[#7657FF] to-[#4387FF] text-white font-medium rounded-tr-sm shadow-md shadow-violet-500/15'
                        : 'bg-white border border-[#EAE5FF] text-[#17233B] rounded-tl-sm shadow-xs'
                    }`}
                  >
                    {isUser ? (
                      <p className="whitespace-pre-line text-white">{turn.content}</p>
                    ) : (
                      renderFormattedMessage(turn.content)
                    )}

                    {/* Explicit Confirmation Gate Banner */}
                    {!isUser && turn.requiresConfirmation && (
                      <div className="mt-3.5 rounded-xl border border-amber-300 bg-amber-50/90 p-3.5 text-xs text-[#17233B] shadow-xs">
                        <div className="flex items-center gap-2 font-bold text-amber-900">
                          <ShieldCheck className="h-4 w-4 shrink-0 text-amber-600" />
                          <span>Explicit Patient Confirmation Required</span>
                        </div>
                        {turn.draft?.selected_doctor_name && (
                          <div className="mt-1.5 text-xs text-slate-700 bg-white/70 rounded-lg p-2 border border-amber-200">
                            <strong>Doctor:</strong> {turn.draft.selected_doctor_name} ·{' '}
                            <strong>Slot:</strong>{' '}
                            {turn.draft.selected_slot_time || turn.draft.selected_slot_id}
                            {turn.draft.patient_reference && (
                              <>
                                {' '}· <strong>Patient ID:</strong>{' '}
                                <span className="font-mono">{turn.draft.patient_reference}</span>
                              </>
                            )}
                          </div>
                        )}
                        <p className="mt-1.5 text-[11px] text-amber-800">
                          MediVoice AI strictly requires explicit patient confirmation before booking slots in Aarogya One Hospital records.
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            disabled={isSending}
                            onClick={() => void handleSendMessage('Yes, confirm booking')}
                            className="inline-flex items-center gap-1.5 rounded-lg bg-[#25D9C3] hover:bg-[#1fbeaa] text-[#17233B] px-3.5 py-1.5 text-xs font-bold transition-all shadow-xs disabled:opacity-50 whitespace-nowrap cursor-pointer"
                          >
                            <CheckCircle2 className="h-3.5 w-3.5 text-[#17233B]" />
                            Confirm Appointment Booking
                          </button>
                          <button
                            type="button"
                            disabled={isSending}
                            onClick={() => void handleSendMessage('Cancel, choose a different slot')}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:border-rose-400 hover:text-rose-600 transition-colors disabled:opacity-50 whitespace-nowrap cursor-pointer"
                          >
                            <XCircle className="h-3.5 w-3.5" />
                            Choose Another Slot
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Confirmed Appointment Details Display Card */}
                    {!isUser && (turn.step === 'BOOKED' || turn.bookedAppointment) && (
                      <div className="mt-3.5 rounded-2xl border border-emerald-300 bg-gradient-to-br from-emerald-50/95 via-teal-50/80 to-emerald-50/95 p-4 text-xs text-[#17233B] shadow-sm">
                        <div className="flex items-center justify-between border-b border-emerald-200/80 pb-2.5 mb-3">
                          <div className="flex items-center gap-2 font-bold text-emerald-900 text-sm">
                            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500 text-white shadow-xs">
                              <CheckCircle2 className="h-4 w-4" />
                            </div>
                            <span>Confirmed Appointment Details</span>
                          </div>
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 border border-emerald-300 px-2.5 py-0.5 text-[11px] font-bold text-emerald-800">
                            Status: Confirmed
                          </span>
                        </div>

                        {/* Details Grid */}
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                          <div className="bg-white/80 rounded-xl p-2.5 border border-emerald-200/60">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 block">Patient Name</span>
                            <span className="font-semibold text-slate-900">
                              {turn.bookedAppointment?.patient_name || turn.draft?.patient_name || 'Valued Patient'}
                            </span>
                          </div>

                          <div className="bg-white/80 rounded-xl p-2.5 border border-emerald-200/60">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 block">Patient Reference ID</span>
                            <span className="font-mono font-semibold text-slate-900">
                              {turn.bookedAppointment?.patient_reference || turn.draft?.patient_reference || activePatientRef || 'PAT-DEMO'}
                            </span>
                          </div>

                          <div className="bg-white/80 rounded-xl p-2.5 border border-emerald-200/60">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 block">Hospital Name</span>
                            <span className="font-semibold text-slate-900">
                              {turn.bookedAppointment?.hospital_name || 'Aarogya One Hospital'}
                            </span>
                          </div>

                          <div className="bg-white/80 rounded-xl p-2.5 border border-emerald-200/60">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 block">Department</span>
                            <span className="font-semibold text-slate-900">
                              {turn.bookedAppointment?.department_name || turn.draft?.specialty || 'General Medicine'}
                            </span>
                          </div>

                          <div className="bg-white/80 rounded-xl p-2.5 border border-emerald-200/60">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 block">Consulting Doctor</span>
                            <span className="font-semibold text-emerald-950">
                              {turn.bookedAppointment?.doctor_name || turn.draft?.selected_doctor_name || 'Doctor'}
                            </span>
                          </div>

                          <div className="bg-white/80 rounded-xl p-2.5 border border-emerald-200/60">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 block">Appointment Date & Time</span>
                            <span className="font-semibold text-slate-900">
                              {formatAppointmentDateTime(turn.bookedAppointment?.appointment_start_time || turn.draft?.selected_slot_time, turn.language || selectedLang)}
                            </span>
                          </div>

                          <div className="bg-white/80 rounded-xl p-2.5 border border-emerald-200/60">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 block">Reason for Visit</span>
                            <span className="font-semibold text-slate-900">
                              {turn.bookedAppointment?.reason_category || turn.draft?.reason_category || 'General Consultation'}
                            </span>
                          </div>

                          <div className="bg-white/80 rounded-xl p-2.5 border border-emerald-200/60">
                            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 block">Booking Reference / ID</span>
                            <span className="font-mono font-bold text-violet-700">
                              {turn.bookedAppointment?.appointment_id || 'CONFIRMED'}
                            </span>
                          </div>
                        </div>

                        {/* Demo SMS Notification Banner */}
                        <div className="mt-3 rounded-xl bg-white/90 p-3 border border-emerald-200">
                          <div className="flex items-start gap-2.5">
                            <MessageSquare className="h-4 w-4 shrink-0 text-emerald-600 mt-0.5" />
                            <div className="text-xs">
                              <p className="font-medium text-slate-800">
                                {LOCALIZED_COMPLETION_NOTICES[turn.language || selectedLang]?.sms || LOCALIZED_COMPLETION_NOTICES.en.sms}
                              </p>
                              <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-600">
                                <span>To mobile: <strong className="font-mono text-slate-900">{maskPhoneNumber(turn.bookedAppointment?.phone_number)}</strong></span>
                                <span className="text-[10px] rounded-full bg-slate-100 text-slate-600 px-2 py-0.5 border border-slate-200">
                                  Simulated Demonstration Notice
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>

                        {/* Natural Thank You Ending */}
                        <div className="mt-2.5 flex items-center gap-2 rounded-xl bg-emerald-100/70 px-3.5 py-2.5 text-xs text-emerald-900 font-medium border border-emerald-200/60">
                          <Heart className="h-4 w-4 shrink-0 text-rose-500 fill-rose-500" />
                          <span>{LOCALIZED_COMPLETION_NOTICES[turn.language || selectedLang]?.thankYou || LOCALIZED_COMPLETION_NOTICES.en.thankYou}</span>
                        </div>
                      </div>
                    )}


                  </div>

                  {/* Metadata Row below Bubble */}
                  <div
                    className={`mt-1 flex items-center gap-2 px-1 text-[11px] text-[#61708A] ${
                      isUser ? 'justify-end' : 'justify-start'
                    }`}
                  >
                    <span>{isUser ? 'Patient' : 'MediVoice AI'}</span>
                    <span aria-hidden="true">·</span>
                    <span className="font-mono tabular-nums">{turn.timestamp}</span>
                    {turn.language && (
                      <>
                        <span aria-hidden="true">·</span>
                        <span className="font-mono uppercase font-semibold text-[#7657FF]">
                          {turn.language}
                        </span>
                      </>
                    )}

                    {/* Gnani Timbre Text-to-Speech Playback Action */}
                    {!isUser && (
                      <>
                        <span aria-hidden="true">·</span>
                        <button
                          type="button"
                          onClick={() => void handlePlayTurnSpeech(turn)}
                          className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#7657FF] hover:text-[#5C45D9] transition-colors"
                          aria-label="Listen with Gnani Timbre TTS"
                          title="Synthesize audio with Gnani Timbre"
                        >
                          {synthesizingTurnId === turn.id ? (
                            <>
                              <Loader2 className="w-3 h-3 animate-spin text-[#25D9C3]" />
                              <span>Generating...</span>
                            </>
                          ) : playingTurnId === turn.id ? (
                            <>
                              <VolumeX className="w-3 h-3 text-rose-500 animate-pulse" />
                              <span className="text-rose-600 font-bold">Stop Audio</span>
                            </>
                          ) : (
                            <>
                              <Volume2 className="w-3 h-3 text-[#7657FF]" />
                              <span>Listen (TTS)</span>
                            </>
                          )}
                        </button>
                      </>
                    )}
                  </div>

                  {/* Interactive Natural Suggestion Chips */}
                  {!isUser &&
                    turn.suggestedOptions &&
                    turn.suggestedOptions.length > 0 &&
                    idx === turns.length - 1 && (
                      <div className="mt-2.5 flex flex-wrap items-center gap-1.5 animate-fadeIn">
                        {turn.suggestedOptions.map((opt, optIdx) => (
                          <button
                            key={optIdx}
                            type="button"
                            onClick={() => void handleSendMessage(opt.value)}
                            disabled={isSending}
                            className="inline-flex items-center gap-1.5 rounded-full border border-violet-200/90 bg-white hover:bg-violet-50 hover:border-[#7657FF] px-3.5 py-1.5 text-xs font-semibold text-[#17233B] hover:text-[#7657FF] transition-all shadow-xs hover:shadow-sm active:scale-95 cursor-pointer disabled:opacity-50"
                          >
                            <Sparkles className="w-3 h-3 text-[#7657FF]" />
                            <span>{opt.label}</span>
                          </button>
                        ))}
                      </div>
                    )}
                </div>
              </div>
            </div>
          );
        })}

        {/* Temporary Assistant Thinking State */}
        {isSending && (
          <div className="flex items-start gap-2.5 animate-fadeIn">
            <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-[#7657FF] to-[#4387FF] text-white shadow-xs">
              <Bot className="h-4 w-4" />
            </div>
            <div className="flex flex-col">
              <div className="rounded-2xl rounded-tl-sm border border-[#EAE5FF] bg-white px-4 py-3 shadow-xs">
                <div className="flex items-center gap-3">
                  {/* Three Animated Bouncing Dots */}
                  <div className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-[#7657FF] animate-bounce [animation-delay:-0.3s]" />
                    <span className="h-2 w-2 rounded-full bg-[#4387FF] animate-bounce [animation-delay:-0.15s]" />
                    <span className="h-2 w-2 rounded-full bg-[#25D9C3] animate-bounce" />
                  </div>
                  <span className="text-xs font-medium text-[#61708A]">
                    MediVoice is thinking...
                  </span>
                </div>
              </div>
              <span className="mt-1 text-[11px] text-[#61708A] px-1">
                Executing controlled hospital workflows
              </span>
            </div>
          </div>
        )}

        {/* Friendly Error State with Actionable Retry */}
        {chatError && (
          <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50/90 p-4 text-xs text-[#17233B] shadow-xs">
            <AlertCircle className="h-5 w-5 shrink-0 text-[#FF7D8A] mt-0.5" />
            <div className="flex-1">
              <p className="font-semibold text-rose-900">Communication Notice</p>
              <p className="mt-0.5 text-rose-800">{chatError}</p>
              <div className="mt-2.5 flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleRetryLastMessage}
                  disabled={isSending}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white px-3 py-1.5 text-xs font-semibold transition-all shadow-xs disabled:opacity-50 cursor-pointer"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  <span>Retry Message</span>
                </button>
              </div>
            </div>
          </div>
        )}
        </div>
      </div>

      {/* =========================================================================
          Suggested Questions Strip
          ========================================================================= */}
      <div className="shrink-0 border-t border-violet-100/80 bg-gradient-to-r from-[#FAF9FE] to-[#F5F8FF] px-4 py-2 sm:px-6">
        <div className="max-w-4xl mx-auto flex items-center gap-2 overflow-x-auto pb-1 scrollbar-none">
          <span className="shrink-0 text-[11px] font-semibold text-[#61708A] uppercase tracking-wider">
            Suggested:
          </span>
          {SUGGESTED_QUESTIONS.map((item) => (
            <button
              key={item.label}
              type="button"
              disabled={isSending}
              onClick={() => void handleSendMessage(item.prompt)}
              className="shrink-0 rounded-full border border-violet-200/80 bg-white px-3 py-1 text-xs font-medium text-slate-700 transition-all hover:border-[#7657FF] hover:text-[#7657FF] hover:bg-violet-50/50 hover:shadow-xs disabled:opacity-50 whitespace-nowrap cursor-pointer"
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {/* =========================================================================
          Message Composer Bar
          ========================================================================= */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void handleSendMessage();
        }}
        className="shrink-0 border-t border-violet-100 bg-white p-3.5 sm:p-4"
      >
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center gap-2">
            {/* Microphone Action Button: Toggles Gnani Voice AI Assistant */}
            <button
              type="button"
              onClick={() => setShowVoicePanel(true)}
              aria-label={showVoicePanel ? 'Close voice panel' : 'Open voice assistant'}
              className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border transition-all cursor-pointer ${
                showVoicePanel
                  ? 'border-[#7657FF] bg-[#7657FF] text-white ring-2 ring-violet-300 shadow-md shadow-violet-500/25'
                  : 'border-violet-200 bg-violet-50/50 text-[#7657FF] hover:border-[#7657FF] hover:bg-violet-100/60'
              }`}
              title="Speak with Gnani Voice AI"
            >
              <Mic className="h-5 w-5" />
            </button>

            {/* Multilingual Text Input */}
            <input
              id="medivoice-message-input"
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void handleSendMessage();
                }
              }}
              placeholder="Ask in English, తెలుగు, हिन्दी, தமிழ், or ಕನ್ನಡ..."
              aria-label="Message MediVoice AI"
              disabled={isSending}
              className="h-11 flex-1 rounded-2xl border border-violet-100 bg-[#FAF9FC] px-4 text-sm text-[#17233B] placeholder-slate-400 focus:border-[#7657FF] focus:bg-white focus:outline-none focus:ring-2 focus:ring-[#7657FF]/20 transition-all"
            />

            {/* Send Button */}
            <button
              type="submit"
              disabled={isSending || !inputMessage.trim()}
              className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-[#7657FF] to-[#4387FF] px-4.5 text-xs font-semibold text-white shadow-md shadow-violet-500/20 transition-all hover:opacity-95 hover:shadow-lg disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer whitespace-nowrap"
            >
              {isSending ? (
                <Loader2 className="h-4 w-4 animate-spin text-white" />
              ) : (
                <Send className="h-3.5 w-3.5" />
              )}
              <span className="hidden sm:inline">Send</span>
            </button>
          </div>

          {/* Safety Boundary Note */}
          <div className="mt-2 flex items-center justify-between text-[11px] text-[#61708A] px-1">
            <span>
              Aarogya One Hospital Care Concierge · Explicit confirmation required before booking
            </span>
            <span className="hidden sm:inline font-mono text-[10px] text-violet-700">
              Session: {sessionId.slice(0, 12)}
            </span>
          </div>
        </div>
      </form>

      {/* =========================================================================
          Dedicated Full-Screen Voice Interface Overlay
          ========================================================================= */}
      {showVoicePanel && (
        <MediVoiceVoicePanel
          sessionId={sessionId}
          patientReference={activePatientRef}
          selectedLanguage={selectedLang}
          onLanguageChange={(lang) => setSelectedLang(lang)}
          onVoiceTurnSuccess={handleVoiceTurnSuccess}
          onGreetingSpoken={handleGreetingSpoken}
          onClose={() => setShowVoicePanel(false)}
          isEmbedded={false}
          hasExistingConversation={turns.some((t) => t.role === 'user')}
        />
      )}
    </div>
  );
};
