import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  AlertCircle,
  Check,
  ChevronDown,
  Globe,
  Loader2,
  MessageSquare,
  Mic,
  MicOff,
  PhoneOff,
  RotateCcw,
  ShieldAlert,
  Sparkles,
  Square,
  Volume2,
  WifiOff,
  X,
} from 'lucide-react';
import { medivoiceApi, ApiError } from '../../services/api';
import { shouldAutoPlayVoiceReply, shouldResumeVoiceMode } from './turnSpeech';
import { drawWaveformBars, drawIdleWaveform } from './waveformVisualizer';
import {
  BookingDraftState,
  SupportedLanguage,
  VoiceLanguagePreference,
  VoiceToolExecutionResult,
} from '../../types/api';

export type VoiceState =
  | 'idle'
  | 'starting_conversation'
  | 'speaking_greeting'
  | 'listening'
  | 'processing_speech'
  | 'assistant_speaking'
  | 'permission_denied'
  | 'service_unavailable'
  | 'ended';

interface MediVoiceVoicePanelProps {
  sessionId: string;
  patientReference?: string | null;
  selectedLanguage: VoiceLanguagePreference;
  onLanguageChange: (lang: VoiceLanguagePreference) => void;
  onVoiceTurnSuccess: (result: {
    userTranscript: string;
    assistantReply: string;
    language: SupportedLanguage;
    draft?: BookingDraftState;
    toolCalls?: VoiceToolExecutionResult[];
    step?: string;
    requiresConfirmation?: boolean;
    audioBlob?: Blob;
    bookedAppointment?: Record<string, any>;
  }) => void;
  onGreetingSpoken?: (greetingText: string, lang: SupportedLanguage) => void;
  onClose?: () => void;
  isEmbedded?: boolean;
  hasExistingConversation?: boolean;
}

const VOICE_LANGUAGES: Array<{
  code: VoiceLanguagePreference;
  locale: string;
  name: string;
  native: string;
}> = [
  { code: 'auto', locale: 'auto', name: 'Auto Detect', native: 'Adaptive' },
  { code: 'en', locale: 'en-IN', name: 'English (India)', native: 'English' },
  { code: 'te', locale: 'te-IN', name: 'Telugu', native: 'తెలుగు' },
  { code: 'hi', locale: 'hi-IN', name: 'Hindi', native: 'हिन्दी' },
  { code: 'ta', locale: 'ta-IN', name: 'Tamil', native: 'தமிழ்' },
  { code: 'kn', locale: 'kn-IN', name: 'Kannada', native: 'ಕನ್ನಡ' },
];

const GREETINGS_BY_LANGUAGE: Record<SupportedLanguage, string> = {
  en: 'Welcome to Aarogya One Hospital! How can I help you today?',
  te: 'ఆరోగ్య వన్ హాస్పిటల్‌కు స్వాగతం! ఈరోజు నేను మీకు ఎలా సహాయపడగలను?',
  hi: 'आरोग्य वन अस्पताल में आपका स्वागत है! आज मैं आपकी क्या मदद कर सकता हूँ?',
  ta: 'ஆரோக்யா ஒன் மருத்துவமனைக்கு வரவேற்கிறோம்! இன்று நான் உங்களுக்கு எவ்வாறு உதவ முடியும்?',
  kn: 'ಆರೋಗ್ಯ ಒನ್ ಆಸ್ಪತ್ರೆಗೆ ಸುಸ್ವಾಗತ! ಇಂದು ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?',
};

// Delayed waiting messages shown in assistantResponse area if backend response exceeds 3 seconds
const WAITING_MESSAGES_BY_LANGUAGE: Record<SupportedLanguage, string> = {
  en: 'Please wait',
  te: 'దయచేసి వేచి ఉండండి',
  hi: 'कृपया प्रतीक्षा करें',
  ta: 'தயவுசெய்து காத்திருக்கவும்',
  kn: 'ದಯವಿಟ್ಟು ಕಾಯಿರಿ',
};

// Client-side cache for synthesized hospital greetings by language (zero-latency replay and instant conversation start)
const GREETING_BLOB_CACHE = new Map<SupportedLanguage, Blob>();

export interface SessionMilestoneTimings {
  voiceActivation: number;
  micPermission?: number;
  ttsInitiation?: number;
  ttsResponse?: number;
  audioDownload?: number;
  playbackStart?: number;
  playbackEnd?: number;
  listeningActivated?: number;
}

export const LOCALIZED_VOICE_FEEDBACK: Record<
  SupportedLanguage,
  {
    silence: string;
    tooShort: string;
    unintelligible: string;
    sttUnavailable: string;
    timeout: string;
    genericError: string;
  }
> = {
  en: {
    silence: "I couldn't hear you. Please speak into your microphone.",
    tooShort: 'Speech was too brief. Please repeat your question.',
    unintelligible: "I couldn't clearly understand that. Could you please repeat?",
    sttUnavailable: 'Speech recognition service is currently unavailable. Please try again or type.',
    timeout: 'Voice request timed out. Please try speaking again.',
    genericError: 'Hospital voice service temporarily unavailable. You can retry or use text chat.',
  },
  te: {
    silence: 'నాకు మీ స్వరం వినిపించలేదు. దయచేసి మైక్రోఫోన్‌లో మాట్లాడండి.',
    tooShort: 'మాట చాలా తక్కువగా ఉంది. దయచేసి మీ అభ్యర్థనను మళ్ళీ చెప్పండి.',
    unintelligible: 'నాకు స్పష్టంగా అర్థం కాలేదు. దయచేసి మరొకసారి చెప్పగలరా?',
    sttUnavailable: 'స్పీచ్ గుర్తింపు సేవ ప్రస్తుతం అందుబాటులో లేదు. దయచేసి మళ్ళీ ప్రయత్నించండి.',
    timeout: 'వాయిస్ ప్రాసెసింగ్ సమయం మించిపోయింది. దయచేసి మళ్ళీ మాట్లాడండి.',
    genericError: 'వాయిస్ సేవ తాత్కాలికంగా అందుబాటులో లేదు. దయచేసి మళ్ళీ ప్రయత్నించండి.',
  },
  hi: {
    silence: 'मुझे आपकी आवाज़ सुनाई नहीं दी। कृपया माइक्रोफ़ोन में बोलें।',
    tooShort: 'ध्वनि बहुत संक्षिप्त थी। कृपया अपनी बात दोहराएं।',
    unintelligible: 'मैं ठीक से समझ नहीं पाया। क्या आप कृपया दोहरा सकते हैं?',
    sttUnavailable: 'ध्वनि पहचान सेवा अभी उपलब्ध नहीं है। कृपया पुनः प्रयास करें।',
    timeout: 'अनुरोध का समय समाप्त हो गया। कृपया पुनः बोलें।',
    genericError: 'वॉयस सेवा अस्थायी रूप से अनुपलब्ध है। कृपया पुनः प्रयास करें या चैट का उपयोग करें।',
  },
  ta: {
    silence: 'உங்கள் குரல் கேட்கவில்லை. தயவுசெய்து மைக்ரோஃபோனில் பேசவும்.',
    tooShort: 'குரல் மிகக் குறைவாக இருந்தது. தயவுசெய்து மீண்டும் கூறவும்.',
    unintelligible: 'எனக்கு தெளிவாக புரியவில்லை. தயவுசெய்து மீண்டும் கூற முடியுமா?',
    sttUnavailable: 'குரல் அறிதல் சேவை தற்போது கிடைக்கவில்லை. மீண்டும் முயற்சிக்கவும்.',
    timeout: 'கோரிக்கையின் நேரம் முடிந்தது. தயவுசெய்து மீண்டும் பேசவும்.',
    genericError: 'குரல் சேவை தற்காலிகமாக கிடைக்கவில்லை. மீண்டும் முயற்சிக்கவும் அல்லது தட்டச்சு செய்யவும்.',
  },
  kn: {
    silence: 'ನಿಮ್ಮ ಧ್ವನಿ ಕೇಳಿಸಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮೈಕ್ರೊಫೋನ್‌ನಲ್ಲಿ ಮಾತನಾಡಿ.',
    tooShort: 'ಧ್ವನಿ ತುಂಬಾ ಕಡಿಮೆಯಾಗಿದೆ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಹೇಳಿ.',
    unintelligible: 'ನನಗೆ ಸ್ಪಷ್ಟವಾಗಿ ಅರ್ಥವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಇನ್ನೊಮ್ಮೆ ಹೇಳಬಹುದೇ?',
    sttUnavailable: 'ಧ್ವನಿ ಗುರುತಿಸುವಿಕೆ ಸೇವೆ ಲಭ್ಯವಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.',
    timeout: 'ವಾಯ್ಸ್ ವಿನಂತಿ ಸಮಯ ಮೀರಿದೆ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಮಾತನಾಡಿ.',
    genericError: 'ವಾಯ್ಸ್ ಸೇವೆ ತಾತ್ಕಾಲಿಕವಾಗಿ ಲಭ್ಯವಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.',
  },
};

function base64ToBlob(base64: string, mimeType = 'audio/wav'): Blob {
  const binaryString = atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return new Blob([bytes], { type: mimeType });
}

function logVoiceDiagnostic(correlationId: string, stage: string, durationMs: number) {
  try {
    if (window.localStorage.getItem('medivoice.voiceDiagnostics') === 'true') {
      console.info('[MediVoice latency]', { correlationId, stage, durationMs: Math.round(durationMs * 100) / 100 });
    }
  } catch {
    // Diagnostics remain off when browser storage is unavailable.
  }
}

function logVoiceEvent(correlationId: string, event: string, details?: Record<string, any>) {
  try {
    console.info(`[MediVoice VoiceTurn] [${correlationId}] ${event}`, details || {});
  } catch {
    // Diagnostics remain silent on error.
  }
}

export const MediVoiceVoicePanel: React.FC<MediVoiceVoicePanelProps> = ({
  sessionId,
  patientReference,
  selectedLanguage,
  onLanguageChange,
  onVoiceTurnSuccess,
  onGreetingSpoken,
  onClose,
  isEmbedded = false,
  hasExistingConversation = false,
}) => {
  const [voiceState, setVoiceState] = useState<VoiceState>('starting_conversation');
  const [recordingDuration, setRecordingDuration] = useState<number>(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [recognizedTranscript, setRecognizedTranscript] = useState<string>('');
  const [assistantResponse, setAssistantResponse] = useState<string>('');
  const [detectedTurnLang, setDetectedTurnLang] = useState<SupportedLanguage | null>(null);
  const [isPlayingAudio, setIsPlayingAudio] = useState<boolean>(false);
  const [isLangMenuOpen, setIsLangMenuOpen] = useState<boolean>(false);
  const [isPatientSpeaking, setIsPatientSpeaking] = useState<boolean>(false);

  // Performance-optimized visualizer and ambient glow refs (bypassing React reconciliation)
  const waveformCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const glowRef = useRef<HTMLDivElement | null>(null);
  const isPatientSpeakingRef = useRef<boolean>(false);

  // Audio recording & playback refs
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const timerIntervalRef = useRef<number | null>(null);
  const audioElementRef = useRef<HTMLAudioElement | null>(null);
  const currentAudioUrlRef = useRef<string | null>(null);

  // Delayed waiting message refs
  const waitingTimerRef = useRef<number | null>(null);
  const waitingDotIntervalRef = useRef<number | null>(null);

  const clearWaitingTimer = useCallback(() => {
    if (waitingTimerRef.current !== null) {
      window.clearTimeout(waitingTimerRef.current);
      waitingTimerRef.current = null;
    }
    if (waitingDotIntervalRef.current !== null) {
      window.clearInterval(waitingDotIntervalRef.current);
      waitingDotIntervalRef.current = null;
    }
  }, []);

  // Session lifecycle & VAD refs
  const isSessionActiveRef = useRef<boolean>(true);
  const isSubmittingRef = useRef<boolean>(false);
  const hasSpokenRef = useRef<boolean>(false);
  const silenceStartRef = useRef<number | null>(null);
  const recordingStartTimeRef = useRef<number>(0);
  const speechEndTimeRef = useRef<number>(0);
  const turnCorrelationIdRef = useRef<string>('');
  const streamingAbortRef = useRef<AbortController | null>(null);
  const selectedLanguageRef = useRef<VoiceLanguagePreference>(selectedLanguage);

  useEffect(() => {
    selectedLanguageRef.current = selectedLanguage;
    setErrorMessage(null);
  }, [selectedLanguage]);

  // Precise 8-milestone timing tracker for voice activation, greeting latency, and listening activation
  const milestonesRef = useRef<SessionMilestoneTimings>({ voiceActivation: 0 });

  const logMilestone = (milestoneNumber: number, name: string, detail?: string) => {
    const elapsed = performance.now() - (milestonesRef.current.voiceActivation || performance.now());
    console.log(
      `[MediVoice Milestone ${milestoneNumber}] ${name}${detail ? ` - ${detail}` : ''} (+${elapsed.toFixed(1)}ms)`
    );
    if (typeof window !== 'undefined') {
      (window as unknown as { __medivoice_milestones: SessionMilestoneTimings }).__medivoice_milestones =
        milestonesRef.current;
    }
  };

  // Cleanup all audio resources (tracks, context, recorder, timer, element)
  const cleanupAudioResources = useCallback(() => {
    clearWaitingTimer();
    streamingAbortRef.current?.abort();
    streamingAbortRef.current = null;
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (waveformCanvasRef.current) {
      const ctx = waveformCanvasRef.current.getContext('2d');
      if (ctx) {
        ctx.clearRect(0, 0, waveformCanvasRef.current.width, waveformCanvasRef.current.height);
      }
    }
    if (glowRef.current) {
      glowRef.current.style.transform = 'scale(1)';
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // ignore
      }
      mediaRecorderRef.current = null;
    }
    if (sourceNodeRef.current) {
      try {
        sourceNodeRef.current.disconnect();
      } catch {
        // ignore
      }
      sourceNodeRef.current = null;
    }
    if (audioStreamRef.current) {
      audioStreamRef.current.getTracks().forEach((track) => track.stop());
      audioStreamRef.current = null;
    }
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      try {
        void audioContextRef.current.close();
      } catch {
        // ignore
      }
      audioContextRef.current = null;
    }
    if (audioElementRef.current) {
      audioElementRef.current.pause();
      audioElementRef.current.onended = null;
      audioElementRef.current.onerror = null;
      audioElementRef.current = null;
    }
    setIsPlayingAudio(false);
    isPatientSpeakingRef.current = false;
    setIsPatientSpeaking(false);
  }, [clearWaitingTimer]);

  // Play audio safely with callback when playback finishes
  const playAudio = useCallback(
    (url: string, onEndedCallback?: () => void, onStartedCallback?: () => void): Promise<void> => {
      return new Promise((resolve) => {
        try {
          if (audioElementRef.current) {
            audioElementRef.current.pause();
            audioElementRef.current.onended = null;
            audioElementRef.current.onerror = null;
            audioElementRef.current = null;
          }

          const audio = new Audio(url);
          audioElementRef.current = audio;

          audio.onplay = () => {
            setIsPlayingAudio(true);
            onStartedCallback?.();
          };

          const handlePlaybackFinished = () => {
            setIsPlayingAudio(false);
            if (audioElementRef.current === audio) {
              audioElementRef.current = null;
            }
            if (onEndedCallback && isSessionActiveRef.current) {
              onEndedCallback();
            }
            resolve();
          };

          audio.onended = handlePlaybackFinished;
          audio.onerror = () => {
            console.warn('Audio playback error encountered');
            handlePlaybackFinished();
          };

          audio.play().catch((playErr) => {
            console.warn('Audio play was deferred or blocked by browser:', playErr);
            handlePlaybackFinished();
          });
        } catch {
          setIsPlayingAudio(false);
          if (onEndedCallback && isSessionActiveRef.current) {
            onEndedCallback();
          }
          resolve();
        }
      });
    },
    []
  );

  // Stop recording and trigger submission
  const stopRecordingAndSubmit = useCallback(() => {
    if (isSubmittingRef.current) return;
    isSubmittingRef.current = true;
    speechEndTimeRef.current = performance.now();

    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }

    setIsPatientSpeaking(false);

    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // ignore
      }
    }
  }, []);

  // Handle captured audio blob through backend orchestration
  const handleAudioCaptured = useCallback(
    async (audioBlob: Blob) => {
      if (!isSessionActiveRef.current) return;

      const speechDuration = Date.now() - recordingStartTimeRef.current;
      const speechEndTime = speechEndTimeRef.current || performance.now();
      const spoken = hasSpokenRef.current;
      const activeLang = selectedLanguageRef.current;

      // Guard 1: Silence / No speech detected during turn (avoid useless backend 422 call)
      if (!spoken) {
        console.log('[MediVoice VAD] No speech detected during recording turn; safely skipping backend call.');
        setErrorMessage(LOCALIZED_VOICE_FEEDBACK[activeLang === 'auto' ? (detectedTurnLang || 'en') : activeLang].silence);
        setVoiceState('listening');
        isSubmittingRef.current = false;
        window.setTimeout(() => {
          if (isSessionActiveRef.current) {
            startListening();
          }
        }, 1200);
        return;
      }

      // Guard 2: Audio too brief (< 600ms or < 800 bytes)
      if (speechDuration < 600 || audioBlob.size < 800) {
        console.log(`[MediVoice VAD] Audio too brief (${speechDuration}ms, ${audioBlob.size}B); prompting patient.`);
        setErrorMessage(LOCALIZED_VOICE_FEEDBACK[activeLang === 'auto' ? (detectedTurnLang || 'en') : activeLang].tooShort);
        setVoiceState('listening');
        isSubmittingRef.current = false;
        window.setTimeout(() => {
          if (isSessionActiveRef.current) {
            startListening();
          }
        }, 1200);
        return;
      }

      setVoiceState('processing_speech');
      setErrorMessage(null);

      clearWaitingTimer();
      const baseWaitingMsg =
        WAITING_MESSAGES_BY_LANGUAGE[activeLang === 'auto' ? (detectedTurnLang || 'en') : activeLang] || WAITING_MESSAGES_BY_LANGUAGE.en;
      let dotCount = 1;
      waitingTimerRef.current = window.setTimeout(() => {
        if (!isSessionActiveRef.current) return;
        setAssistantResponse(`${baseWaitingMsg}.`);
        waitingDotIntervalRef.current = window.setInterval(() => {
          if (!isSessionActiveRef.current) return;
          dotCount = (dotCount % 3) + 1;
          const dots = '.'.repeat(dotCount);
          setAssistantResponse(`${baseWaitingMsg}${dots}`);
        }, 3000);
      }, 3000);

      try {
        // Unified voice turn: STT -> ConversationManager (Gemini reasoning) -> Hospital DB Tools -> Timbre TTS
        const correlationId = turnCorrelationIdRef.current || (typeof crypto !== 'undefined' && 'randomUUID' in crypto
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random().toString(36).slice(2)}`);
        turnCorrelationIdRef.current = correlationId;
        let experimentalStreamingTts = false;
        try {
          experimentalStreamingTts = window.localStorage.getItem('medivoice.experimentalStreamingTts') === 'true';
        } catch { /* experimental path remains disabled if storage is unavailable */ }
        const uploadStart = performance.now();
        logVoiceDiagnostic(correlationId, 'frontend_request_submission_ms', uploadStart - speechEndTime);
        const result = await medivoiceApi.sendVoiceTurn(audioBlob, {
          sessionId,
          patientReference,
          language: activeLang,
          correlationId,
          experimentalStreamingTts,
        });
        const responseReceived = performance.now();
        logVoiceDiagnostic(correlationId, 'speech_end_to_response_received_ms', responseReceived - speechEndTime);
        logVoiceDiagnostic(correlationId, 'voice_request_ms', responseReceived - uploadStart);

        clearWaitingTimer();
        if (!isSessionActiveRef.current) return;

        const transcript = (result.transcript || '').trim();
        const reply = (result.assistant_reply || result.reply || '').trim();

        if (!transcript) {
          setErrorMessage(LOCALIZED_VOICE_FEEDBACK[activeLang === 'auto' ? (detectedTurnLang || 'en') : activeLang].unintelligible);
          setVoiceState('listening');
          isSubmittingRef.current = false;
          window.setTimeout(() => {
            if (isSessionActiveRef.current) startListening();
          }, 1500);
          return;
        }

        setRecognizedTranscript(transcript);
        setAssistantResponse(reply);

        // Prepare synthesized assistant speech
        let audioUrlToPlay: string | null = null;
        let assistantAudioBlob: Blob | undefined;
        if (result.audio_base64) {
          logVoiceEvent(correlationId, 'audio_decoding_start', {
            contentType: result.audio_content_type,
            base64Length: result.audio_base64.length,
          });
          try {
            const audioBlobOut = base64ToBlob(
              result.audio_base64,
              result.audio_content_type || 'audio/wav'
            );
            assistantAudioBlob = audioBlobOut;
            if (currentAudioUrlRef.current) {
              URL.revokeObjectURL(currentAudioUrlRef.current);
            }
            audioUrlToPlay = URL.createObjectURL(audioBlobOut);
            currentAudioUrlRef.current = audioUrlToPlay;
            logVoiceEvent(correlationId, 'audio_decoding_success', {
              blobSize: audioBlobOut.size,
            });
          } catch (decodeErr) {
            logVoiceEvent(correlationId, 'audio_decoding_error', { error: String(decodeErr) });
          }
        } else {
          logVoiceEvent(correlationId, 'audio_omitted_or_missing', {
            tts_error: result.tts_error,
            tts_available: result.tts_available,
          });
        }

        const isBookingCompleted =
          result.conversation_step === 'BOOKED' ||
          result.step === 'BOOKED' ||
          Boolean(result.booked_appointment);
        const shouldPlayInlineAudio = shouldAutoPlayVoiceReply({
          voiceModeActive: isSessionActiveRef.current,
          audioAvailable: Boolean(audioUrlToPlay),
        });

        const turnDetectedLang = (result.detected_language as SupportedLanguage) || (result.language as SupportedLanguage) || 'en';
        setDetectedTurnLang(turnDetectedLang);
        if (activeLang !== 'auto' && result.language && (result.language as SupportedLanguage) !== activeLang) {
          selectedLanguageRef.current = result.language as SupportedLanguage;
        }

        // Notify parent chat interface to record user speech and assistant reply in chat timeline
        onVoiceTurnSuccess({
          userTranscript: transcript,
          assistantReply: reply,
          language: (result.language as SupportedLanguage) || turnDetectedLang,
          draft: result.draft,
          toolCalls: result.tool_calls || result.tool_trace,
          step: result.conversation_step || result.step,
          requiresConfirmation: result.requires_confirmation,
          audioBlob: assistantAudioBlob,
          bookedAppointment: result.booked_appointment || undefined,
        });

        // The experimental path streams only final assistant text and schedules each PCM chunk once.
        if (experimentalStreamingTts) {
          setVoiceState('assistant_speaking');
          const resumeListening = () => {
            setIsPlayingAudio(false);
            if (!shouldResumeVoiceMode(isBookingCompleted)) {
              setVoiceState('idle');
              return;
            }
            window.setTimeout(() => {
              if (isSessionActiveRef.current) {
                logVoiceDiagnostic(correlationId, 'microphone_resume_after_response_ms', performance.now() - responseReceived);
                startListening();
              }
            }, 200);
          };
          streamingAbortRef.current = new AbortController();
          try {
            await medivoiceApi.streamSynthesizeSpeech(
              reply,
              result.language || activeLang,
              () => {
                setIsPlayingAudio(true);
                logVoiceDiagnostic(correlationId, 'stream_first_audible_playback_ms', performance.now() - speechEndTime);
              },
              streamingAbortRef.current.signal,
              undefined,
              correlationId,
            );
            logVoiceDiagnostic(correlationId, 'stream_playback_complete_ms', performance.now() - responseReceived);
            resumeListening();
          } catch (streamError) {
            const audibleStarted = Boolean((streamError as { audibleStarted?: boolean })?.audibleStarted);
            if (!audibleStarted && isSessionActiveRef.current) {
              try {
                const fallbackBlob = await medivoiceApi.synthesizeSpeech(reply, result.language || activeLang, undefined, correlationId);
                if (currentAudioUrlRef.current) URL.revokeObjectURL(currentAudioUrlRef.current);
                const fallbackUrl = URL.createObjectURL(fallbackBlob);
                currentAudioUrlRef.current = fallbackUrl;
                await playAudio(fallbackUrl, resumeListening, () => {
                  logVoiceDiagnostic(correlationId, 'fallback_first_audible_playback_ms', performance.now() - speechEndTime);
                });
              } catch {
                resumeListening();
              }
            } else {
              console.warn('Experimental streaming playback stopped after partial audio; no full-response retry was made.');
              resumeListening();
            }
          } finally {
            streamingAbortRef.current = null;
          }
        // Step 4 & 5: Play assistant speech. If booking is completed, stay idle/completed and do NOT restart listening loop!
        } else if (audioUrlToPlay) {
          if (!shouldPlayInlineAudio) {
            setVoiceState('idle');
            return;
          }
          setVoiceState('assistant_speaking');
          logVoiceEvent(correlationId, 'playback_start', { lang: result.language || activeLang });
          await playAudio(audioUrlToPlay, () => {
            logVoiceEvent(correlationId, 'playback_complete', {
              durationSinceResponse: performance.now() - responseReceived,
            });
            logVoiceDiagnostic(correlationId, 'response_complete_playback_ms', performance.now() - responseReceived);
            if (!shouldResumeVoiceMode(isBookingCompleted)) {
              setVoiceState('idle');
              return;
            }
            // Continuous Conversation Loop with 200ms acoustic settling pause
            window.setTimeout(() => {
              if (isSessionActiveRef.current) {
                logVoiceEvent(correlationId, 'listening_restart_after_playback');
                logVoiceDiagnostic(correlationId, 'microphone_resume_after_response_ms', performance.now() - responseReceived);
                startListening();
              }
            }, 200);
          }, () => {
            logVoiceEvent(correlationId, 'first_audible_chunk', {
              latencyMs: performance.now() - speechEndTime,
            });
            logVoiceDiagnostic(correlationId, 'speech_end_to_first_audio_ms', performance.now() - speechEndTime);
          });
        } else {
          // The unified backend already attempted TTS. Retrying a known provider failure
          // here duplicated the same expensive request and added another full TTS wait.
          if (result.tts_error) {
            logVoiceEvent(correlationId, 'tts_error_handled', { error: result.tts_error });
            isSubmittingRef.current = false;
            if (!shouldResumeVoiceMode(isBookingCompleted)) {
              setVoiceState('idle');
              return;
            }
            // Graceful pause: give the patient 2500ms to read the on-screen text before restarting listening
            setVoiceState('idle');
            window.setTimeout(() => {
              if (isSessionActiveRef.current) {
                logVoiceEvent(correlationId, 'listening_restart_after_tts_error');
                startListening();
              }
            }, 2500);
            return;
          }

          // Compatibility fallback for older servers that omit inline audio without an error.
          try {
            const synthesizedBlob = await medivoiceApi.synthesizeSpeech(
              reply,
              result.language || activeLang
            );
            if (currentAudioUrlRef.current) {
              URL.revokeObjectURL(currentAudioUrlRef.current);
            }
            audioUrlToPlay = URL.createObjectURL(synthesizedBlob);
            currentAudioUrlRef.current = audioUrlToPlay;
            setVoiceState('assistant_speaking');
            await playAudio(audioUrlToPlay, () => {
              if (isBookingCompleted) {
                setVoiceState('idle');
                return;
              }
              window.setTimeout(() => {
                if (isSessionActiveRef.current) {
                  startListening();
                }
              }, 200);
            });
          } catch {
            setVoiceState(isBookingCompleted ? 'idle' : 'assistant_speaking');
            if (!isBookingCompleted) {
              window.setTimeout(() => {
                if (isSessionActiveRef.current) {
                  startListening();
                }
              }, 3000);
            }
          }
        }
      } catch (err: unknown) {
        clearWaitingTimer();
        if (!isSessionActiveRef.current) return;
        console.error('Voice turn processing error:', err);
        isSubmittingRef.current = false;

        if (typeof navigator !== 'undefined' && !navigator.onLine) {
          setVoiceState('service_unavailable');
          setErrorMessage('Network connection lost. Please check your internet connection.');
        } else if (err instanceof ApiError && err.status === 422) {
          // Empty or unintelligible speech - gracefully resume listening without repeating greeting
          setErrorMessage(LOCALIZED_VOICE_FEEDBACK[activeLang === 'auto' ? (detectedTurnLang || 'en') : activeLang].unintelligible);
          setVoiceState('listening');
          window.setTimeout(() => {
            if (isSessionActiveRef.current) startListening();
          }, 1500);
        } else if (err instanceof ApiError && err.status === 502) {
          setVoiceState('service_unavailable');
          setErrorMessage(LOCALIZED_VOICE_FEEDBACK[activeLang === 'auto' ? (detectedTurnLang || 'en') : activeLang].sttUnavailable);
        } else if (err instanceof ApiError && (err.status === 504 || err.status === 408)) {
          setErrorMessage(LOCALIZED_VOICE_FEEDBACK[activeLang === 'auto' ? (detectedTurnLang || 'en') : activeLang].timeout);
          setVoiceState('listening');
          window.setTimeout(() => {
            if (isSessionActiveRef.current) startListening();
          }, 1500);
        } else {
          setVoiceState('service_unavailable');
          setErrorMessage(
            err instanceof ApiError
              ? err.message
              : LOCALIZED_VOICE_FEEDBACK[activeLang === 'auto' ? (detectedTurnLang || 'en') : activeLang].genericError
          );
        }
      }
    },
    [sessionId, patientReference, onVoiceTurnSuccess, playAudio, clearWaitingTimer]
  );

  // Start Visualizer and Time-Domain RMS Voice Activity Detection (VAD)
  const startAudioVisualizerAndVad = useCallback(
    (stream: MediaStream) => {
      try {
        if (animFrameRef.current) {
          cancelAnimationFrame(animFrameRef.current);
          animFrameRef.current = null;
        }

        const AudioCtx =
          window.AudioContext ||
          (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
        if (!audioContextRef.current || audioContextRef.current.state === 'closed') {
          audioContextRef.current = new AudioCtx();
        }
        const audioCtx = audioContextRef.current;
        if (audioCtx.state === 'suspended') {
          void audioCtx.resume();
        }

        if (sourceNodeRef.current) {
          try {
            sourceNodeRef.current.disconnect();
          } catch {
            // ignore
          }
        }

        const source = audioCtx.createMediaStreamSource(stream);
        sourceNodeRef.current = source;

        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        analyser.smoothingTimeConstant = 0.4;
        source.connect(analyser);
        analyserRef.current = analyser;

        const timeData = new Uint8Array(analyser.fftSize);
        const freqData = new Uint8Array(analyser.frequencyBinCount);

        let calibrationFrames = 0;
        let ambientSum = 0;
        let dynamicSpeechThreshold = 0.038;
        let consecutiveSpeechCount = 0;

        const updateMeter = () => {
          if (!analyserRef.current || !isSessionActiveRef.current || isSubmittingRef.current) return;

          // 1. Compute true acoustic RMS energy from time domain
          analyserRef.current.getByteTimeDomainData(timeData);
          let sumSquares = 0;
          for (let i = 0; i < timeData.length; i++) {
            const normalized = (timeData[i] - 128) / 128; // -1.0 to +1.0
            sumSquares += normalized * normalized;
          }
          const rms = Math.sqrt(sumSquares / timeData.length);

          // 2. Direct Canvas Waveform rendering (0 React state updates at 60 FPS)
          analyserRef.current.getByteFrequencyData(freqData);
          if (waveformCanvasRef.current) {
            drawWaveformBars(waveformCanvasRef.current, freqData, rms, isPatientSpeakingRef.current);
          }

          // Directly modulate ambient glow scale via CSS transform (GPU accelerated, no layout reflow)
          if (glowRef.current) {
            const scale = 1 + Math.min(rms * 4.0, 1.0) * 0.45;
            glowRef.current.style.transform = `scale(${scale.toFixed(3)})`;
          }

          // 3. Dynamic ambient noise calibration (first 24 frames, ~400ms at 60fps)
          if (calibrationFrames < 24) {
            ambientSum += rms;
            calibrationFrames++;
            const currentAmbient = ambientSum / calibrationFrames;
            dynamicSpeechThreshold = Math.min(0.080, Math.max(0.032, currentAmbient * 2.5));
            // CRITICAL: Speech onset detection is bypassed during ambient calibration
            animFrameRef.current = requestAnimationFrame(updateMeter);
            return;
          }

          // 4. Voice Activity Detection (VAD) logic - requires 5 consecutive frames (~85ms) above threshold
          if (rms > dynamicSpeechThreshold) {
            consecutiveSpeechCount++;
            if (consecutiveSpeechCount >= 5) {
              // Confirmed speech detected!
              hasSpokenRef.current = true;
              silenceStartRef.current = null;
              if (!isPatientSpeakingRef.current) {
                isPatientSpeakingRef.current = true;
                setIsPatientSpeaking(true);
              }
            }
          } else {
            consecutiveSpeechCount = 0;
            if (hasSpokenRef.current) {
              if (isPatientSpeakingRef.current) {
                isPatientSpeakingRef.current = false;
                setIsPatientSpeaking(false);
              }
              // Patient spoke, now silent
              if (!silenceStartRef.current) {
                silenceStartRef.current = performance.now();
              } else if (performance.now() - silenceStartRef.current >= 1800) {
                // Exactly 1.8 seconds of continuous silence after speech -> Auto-submit!
                stopRecordingAndSubmit();
                return;
              }
            }
          }

          animFrameRef.current = requestAnimationFrame(updateMeter);
        };

        animFrameRef.current = requestAnimationFrame(updateMeter);
      } catch (err) {
        console.warn('VAD AudioContext initialization warning:', err);
      }
    },
    [stopRecordingAndSubmit]
  );

  // Activate microphone recording in listening state
  const startListening = useCallback(() => {
    if (!isSessionActiveRef.current) return;

    if (audioElementRef.current) {
      audioElementRef.current.pause();
    }
    setIsPlayingAudio(false);

    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }

    isSubmittingRef.current = false;
    turnCorrelationIdRef.current = typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    hasSpokenRef.current = false;
    silenceStartRef.current = null;
    isPatientSpeakingRef.current = false;
    setIsPatientSpeaking(false);
    setRecordingDuration(0);
    setVoiceState('listening');
    setErrorMessage(null);
    if (waveformCanvasRef.current) {
      drawIdleWaveform(waveformCanvasRef.current);
    }

    const stream = audioStreamRef.current;
    if (!stream) {
      void initVoiceSession();
      return;
    }

    // Start Audio Visualizer and Time-Domain RMS Voice Activity Detection (VAD)
    startAudioVisualizerAndVad(stream);

    // Determine supported mime type for MediaRecorder
    let mimeType = 'audio/webm';
    if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
      mimeType = 'audio/webm;codecs=opus';
    } else if (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) {
      mimeType = 'audio/ogg;codecs=opus';
    } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
      mimeType = 'audio/mp4';
    }

    try {
      const mediaRecorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        logVoiceDiagnostic(turnCorrelationIdRef.current, 'audio_finalization_ms', performance.now() - speechEndTimeRef.current);
        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
        if (isSessionActiveRef.current) {
          void handleAudioCaptured(audioBlob);
        }
      };

      mediaRecorder.start(200);
      recordingStartTimeRef.current = Date.now();

      timerIntervalRef.current = window.setInterval(() => {
        const elapsed = Math.floor((Date.now() - recordingStartTimeRef.current) / 1000);
        setRecordingDuration(elapsed);

        // Safety timeout: auto-submit at 15s max speech
        if (elapsed >= 15) {
          stopRecordingAndSubmit();
        }
      }, 500);
    } catch (err) {
      console.error('Failed to start MediaRecorder:', err);
      setVoiceState('service_unavailable');
      setErrorMessage('Failed to initialize microphone recorder.');
    }
  }, [
    startAudioVisualizerAndVad,
    stopRecordingAndSubmit,
    handleAudioCaptured,
  ]);

  // Initialize voice conversation session with concurrent mic permission & greeting fetch
  const initVoiceSession = useCallback(async () => {
    cleanupAudioResources();
    setVoiceState('starting_conversation');
    setErrorMessage(null);
    setRecognizedTranscript('');
    setAssistantResponse('');
    isSessionActiveRef.current = true;
    isSubmittingRef.current = false;

    // Milestone 1: Voice activation
    const tActivation = performance.now();
    milestonesRef.current = { voiceActivation: tActivation };
    logMilestone(1, 'Voice activation initiated');

    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error(
          'Your browser does not support audio recording. Please use Google Chrome, Microsoft Edge, or Firefox.'
        );
      }

      const effectiveGreetingLang: SupportedLanguage = selectedLanguage === 'auto' ? 'en' : selectedLanguage;
      const greetingText =
        GREETINGS_BY_LANGUAGE[effectiveGreetingLang] || GREETINGS_BY_LANGUAGE.en;
      if (!hasExistingConversation) {
        setAssistantResponse(greetingText);
      }

      // Concurrent Operation 1: Synthesize / retrieve cached greeting audio (only on fresh conversation)
      const tTtsReq = performance.now();
      milestonesRef.current.ttsInitiation = tTtsReq;
      logMilestone(3, 'TTS request initiation');

      const greetingFetchPromise = hasExistingConversation
        ? Promise.resolve(null)
        : (async () => {
            let blob = GREETING_BLOB_CACHE.get(effectiveGreetingLang);
            if (!blob) {
              blob = await medivoiceApi.synthesizeSpeech(
                greetingText,
                effectiveGreetingLang
              );
              GREETING_BLOB_CACHE.set(effectiveGreetingLang, blob);
            }
            const tTtsResp = performance.now();
            milestonesRef.current.ttsResponse = tTtsResp;
            milestonesRef.current.audioDownload = tTtsResp;
            logMilestone(4, 'TTS provider response', `duration: ${(tTtsResp - tTtsReq).toFixed(1)}ms`);
            logMilestone(5, 'Audio download completion', `${blob.size} bytes`);
            return blob;
          })().catch((err) => {
            console.warn('Greeting audio synthesis warning:', err);
            return null;
          });

      // Concurrent Operation 2: Request browser microphone permission
      const micStreamPromise = navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      }).then((stream) => {
        const tMic = performance.now();
        milestonesRef.current.micPermission = tMic;
        logMilestone(2, 'Microphone permission granted', `latency: ${(tMic - tActivation).toFixed(1)}ms`);
        return stream;
      });

      // Concurrent await for mic permission and greeting audio fetch
      const [greetingBlob, stream] = await Promise.all([
        greetingFetchPromise,
        micStreamPromise,
      ]);

      if (!isSessionActiveRef.current) {
        if (stream) stream.getTracks().forEach((t) => t.stop());
        return;
      }

      audioStreamRef.current = stream;

      if (hasExistingConversation) {
        // Conversation already in progress: do not repeat welcome greeting.
        milestonesRef.current.listeningActivated = performance.now();
        logMilestone(8, 'Listening activation (existing conversation)');
        startListening();
      } else if (greetingBlob) {
        // Synthesize and play greeting using Gnani Timbre TTS
        setVoiceState('speaking_greeting');
        if (onGreetingSpoken) {
          onGreetingSpoken(greetingText, effectiveGreetingLang);
        }

        if (currentAudioUrlRef.current) {
          URL.revokeObjectURL(currentAudioUrlRef.current);
        }
        const audioUrl = URL.createObjectURL(greetingBlob);
        currentAudioUrlRef.current = audioUrl;

        const tPlayStart = performance.now();
        milestonesRef.current.playbackStart = tPlayStart;
        logMilestone(6, 'Audio playback start', `at +${(tPlayStart - tActivation).toFixed(1)}ms from activation`);

        await playAudio(audioUrl, () => {
          const tPlayEnd = performance.now();
          milestonesRef.current.playbackEnd = tPlayEnd;
          logMilestone(7, 'Greeting playback completion', `duration: ${(tPlayEnd - tPlayStart).toFixed(1)}ms`);

          // Acoustic settling delay: 200ms pause to let hardware echo cancellation settle
          window.setTimeout(() => {
            if (isSessionActiveRef.current) {
              milestonesRef.current.listeningActivated = performance.now();
              logMilestone(8, 'Listening activation', `total time: ${(performance.now() - tActivation).toFixed(1)}ms`);
              startListening();
            }
          }, 200);
        });
      } else {
        // Fallback if greeting audio unavailable: start listening directly
        window.setTimeout(() => {
          if (isSessionActiveRef.current) {
            milestonesRef.current.listeningActivated = performance.now();
            logMilestone(8, 'Listening activation (greeting fallback)');
            startListening();
          }
        }, 800);
      }
    } catch (err: unknown) {
      if (!isSessionActiveRef.current) return;
      cleanupAudioResources();
      const errName = (err as { name?: string })?.name;
      if (errName === 'NotAllowedError' || errName === 'PermissionDeniedError') {
        setVoiceState('permission_denied');
        setErrorMessage(
          'Microphone access was denied. Please allow microphone permission in your browser address bar.'
        );
      } else if (errName === 'NotFoundError' || errName === 'DevicesNotFoundError') {
        setVoiceState('permission_denied');
        setErrorMessage(
          'No microphone was found. Please connect a microphone and tap retry.'
        );
      } else {
        setVoiceState('service_unavailable');
        setErrorMessage(
          (err as Error)?.message ||
            'Failed to initialize voice service. Please check your microphone and retry.'
        );
      }
    }
  }, [
    cleanupAudioResources,
    hasExistingConversation,
    onGreetingSpoken,
    playAudio,
    selectedLanguage,
    startListening,
  ]);

  // Auto-start voice conversation on mount (First mic click opens panel & starts greeting)
  useEffect(() => {
    isSessionActiveRef.current = true;
    void initVoiceSession();

    return () => {
      isSessionActiveRef.current = false;
      cleanupAudioResources();
      if (currentAudioUrlRef.current) {
        URL.revokeObjectURL(currentAudioUrlRef.current);
      }
    };
  }, []);

  // Draw idle resting equalizer whenever entering listening state
  useEffect(() => {
    if (voiceState === 'listening' && waveformCanvasRef.current) {
      drawIdleWaveform(waveformCanvasRef.current);
    }
  }, [voiceState]);

  // Explicitly end conversation
  const handleEndConversation = () => {
    isSessionActiveRef.current = false;
    cleanupAudioResources();
    setVoiceState('ended');
  };

  // Handle closing voice mode cleanly and returning to text chat
  const handleCloseVoice = useCallback(() => {
    isSessionActiveRef.current = false;
    cleanupAudioResources();
    if (onClose) {
      onClose();
    }
  }, [cleanupAudioResources, onClose]);

  // Keyboard shortcut: Escape exits full-screen voice mode
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleCloseVoice();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleCloseVoice]);

  // Replay current assistant audio
  const handleReplay = () => {
    if (currentAudioUrlRef.current) {
      void playAudio(currentAudioUrlRef.current, () => {
        window.setTimeout(() => {
          if (isSessionActiveRef.current) {
            startListening();
          }
        }, 200);
      });
    }
  };

  // Skip assistant speaking and jump straight to listening
  const handleSkipToListening = () => {
    if (audioElementRef.current) {
      audioElementRef.current.pause();
    }
    setIsPlayingAudio(false);
    milestonesRef.current.listeningActivated = performance.now();
    logMilestone(8, 'Listening activation (skipped playback)');
    startListening();
  };

  const currentLangMeta =
    VOICE_LANGUAGES.find((l) => l.code === selectedLanguage) || VOICE_LANGUAGES[0];

  const formatTimer = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
  };

  return (
    <div
      className={
        isEmbedded
          ? "relative w-full overflow-hidden transition-all duration-500 rounded-3xl p-5 sm:p-6 bg-gradient-to-b from-[#181335] via-[#121428] to-[#0A0D1E] text-white shadow-2xl border border-violet-500/25"
          : "fixed inset-0 z-50 overflow-y-auto bg-gradient-to-b from-[#0B081E] via-[#120F2E] to-[#070915] text-white flex flex-col justify-between p-4 sm:p-6 lg:p-8 backdrop-blur-2xl"
      }
      role="region"
      aria-label="MediVoice AI Full-Screen Voice Receptionist Interface"
    >
      {/* Background Ambient Radial Glows in Royal Violet (#7657FF), Electric Blue (#4387FF) & Turquoise (#25D9C3) */}
      <div className="absolute -top-32 -left-32 w-96 h-96 rounded-full bg-[#7657FF]/25 blur-3xl pointer-events-none" />
      <div className="absolute -bottom-32 -right-32 w-96 h-96 rounded-full bg-[#4387FF]/20 blur-3xl pointer-events-none" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[32rem] h-[32rem] rounded-full bg-[#25D9C3]/10 blur-3xl pointer-events-none" />

      {/* Top Header Bar: Branding, Language Switcher, Return to Text Chat, End Call, and Close Button */}
      <div className="relative z-20 flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-white/10 max-w-6xl mx-auto w-full">
        {/* Aarogya One Hospital Branding */}
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-tr from-[#7657FF] to-[#4387FF] text-white shadow-lg shadow-violet-500/30">
            <Sparkles className="h-5 w-5 text-white animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-display text-sm sm:text-base font-bold text-white tracking-tight">
                MediVoice AI
              </h2>
              <span className="rounded-full bg-emerald-500/20 border border-emerald-400/30 px-2 py-0.5 text-[10px] font-bold text-[#25D9C3] flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-[#25D9C3] animate-pulse" />
                Voice Concierge
              </span>
            </div>
            <p className="text-[11px] text-white/60 hidden sm:block">
              Aarogya One Hospital · Multilingual Voice Receptionist
            </p>
          </div>
        </div>

        {/* Center: Language Switcher Dropdown */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setIsLangMenuOpen(!isLangMenuOpen)}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/10 hover:bg-white/15 backdrop-blur-md border border-white/20 text-xs font-medium transition-all shadow-sm focus:outline-none focus:ring-2 focus:ring-[#7657FF] cursor-pointer"
            aria-expanded={isLangMenuOpen}
            aria-label="Select voice conversation language"
          >
            {selectedLanguage === 'auto' ? (
              <>
                <Sparkles className="w-3.5 h-3.5 text-[#25D9C3] animate-pulse" />
                <span className="font-semibold text-emerald-200">Auto</span>
                <span className="text-white/70 text-[11px] bg-white/10 px-1.5 py-0.5 rounded-md">
                  {detectedTurnLang ? (VOICE_LANGUAGES.find(l => l.code === detectedTurnLang)?.name || detectedTurnLang) : 'Adaptive'}
                </span>
              </>
            ) : (
              <>
                <Globe className="w-3.5 h-3.5 text-[#25D9C3]" />
                <span className="font-semibold text-violet-200">{currentLangMeta.name}</span>
                <span className="text-white/60">({currentLangMeta.native})</span>
              </>
            )}
            <ChevronDown className="w-3.5 h-3.5 text-white/60" />
          </button>

          {isLangMenuOpen && (
            <div className="absolute top-full right-0 sm:left-0 mt-2 w-60 rounded-2xl bg-[#1C1838] border border-violet-400/30 shadow-2xl backdrop-blur-xl p-1.5 z-50">
              <div className="text-[10px] font-bold tracking-wider text-violet-300/80 px-2.5 py-1 uppercase">
                Gnani Multilingual Voice
              </div>
              {VOICE_LANGUAGES.map((lang) => (
                <button
                  key={lang.code}
                  type="button"
                  onClick={() => {
                    onLanguageChange(lang.code);
                    setIsLangMenuOpen(false);
                  }}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs md:text-sm transition-colors text-left cursor-pointer ${
                    selectedLanguage === lang.code
                      ? 'bg-violet-600/30 text-white font-medium border border-violet-400/40'
                      : 'text-white/80 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  <div className="flex flex-col">
                    <span className="font-medium flex items-center gap-1.5">
                      {lang.code === 'auto' && <Sparkles className="w-3.5 h-3.5 text-[#25D9C3]" />}
                      {lang.name}
                    </span>
                    <span className="text-xs text-white/50">{lang.native}</span>
                  </div>
                  {selectedLanguage === lang.code && <Check className="w-4 h-4 text-[#25D9C3]" />}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right Exit & Call Controls */}
        <div className="flex items-center gap-2 sm:gap-3">
          {/* Return to Text Chat Button */}
          <button
            type="button"
            onClick={handleCloseVoice}
            className="inline-flex items-center gap-1.5 rounded-full border border-violet-400/40 bg-violet-600/20 hover:bg-violet-600/30 text-white px-3 sm:px-4 py-1.5 text-xs font-semibold backdrop-blur-md transition-all shadow-sm hover:scale-102 cursor-pointer"
            title="Return to text chat (preserves all conversation history)"
          >
            <MessageSquare className="w-3.5 h-3.5 text-[#25D9C3]" />
            <span className="hidden sm:inline">Return to Text Chat</span>
            <span className="sm:hidden">Chat</span>
          </button>

          {/* End Call Button */}
          {voiceState !== 'ended' && (
            <button
              type="button"
              onClick={handleEndConversation}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-rose-500/20 hover:bg-rose-500/30 border border-rose-400/30 text-rose-200 text-xs font-semibold transition-all cursor-pointer"
              title="End current voice session"
            >
              <PhoneOff className="w-3 h-3 text-rose-300" />
              <span>End Call</span>
            </button>
          )}

          {/* Close X Button */}
          <button
            type="button"
            onClick={handleCloseVoice}
            className="p-2 rounded-full bg-white/10 hover:bg-white/20 text-white/70 hover:text-white transition-colors focus:outline-none focus:ring-2 focus:ring-[#7657FF] cursor-pointer"
            aria-label="Close voice panel"
            title="Close (Esc)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Interactive Stage */}
      <div className="relative z-10 flex flex-col items-center justify-center text-center my-auto py-6 sm:py-8 max-w-2xl mx-auto w-full">
        {/* Animated Radial Glowing AI Orb */}
        <div className="relative mb-6 flex items-center justify-center">
          {/* Outer Ambient Glow Reacting to Audio Level via GPU Transform */}
          <div
            ref={glowRef}
            className="absolute rounded-full transition-transform duration-150 ease-out pointer-events-none"
            style={{
              width: '200px',
              height: '200px',
              transform: 'scale(1)',
              background:
                voiceState === 'listening'
                  ? isPatientSpeaking
                    ? 'radial-gradient(circle, rgba(37,217,195,0.6) 0%, rgba(118,87,255,0.45) 50%, transparent 75%)'
                    : 'radial-gradient(circle, rgba(37,217,195,0.3) 0%, rgba(118,87,255,0.2) 50%, transparent 75%)'
                  : voiceState === 'assistant_speaking' || voiceState === 'speaking_greeting'
                  ? 'radial-gradient(circle, rgba(67,135,255,0.45) 0%, rgba(37,217,195,0.3) 50%, transparent 75%)'
                  : voiceState === 'permission_denied' || voiceState === 'service_unavailable'
                  ? 'radial-gradient(circle, rgba(255,125,138,0.4) 0%, transparent 70%)'
                  : 'radial-gradient(circle, rgba(118,87,255,0.3) 0%, rgba(67,135,255,0.2) 50%, transparent 75%)',
            }}
          />

          {/* Rotating Shimmer Halo for Active Processing / Initializing */}
          {(voiceState === 'starting_conversation' || voiceState === 'processing_speech') && (
            <div
              className="absolute w-52 h-52 sm:w-60 sm:h-60 rounded-full border border-violet-400/30 border-t-[#25D9C3] border-r-[#4387FF] animate-spin pointer-events-none"
              style={{ animationDuration: '3s' }}
            />
          )}

          {/* Core Voice Orb */}
          <div
            className={`relative w-44 h-44 sm:w-52 sm:h-52 rounded-full flex flex-col items-center justify-center shadow-2xl transition-all duration-300 ${
              voiceState === 'starting_conversation'
                ? 'bg-gradient-to-tr from-[#7657FF] via-[#5C45D9] to-[#4387FF] ring-4 ring-violet-400/30 shadow-violet-500/30'
                : voiceState === 'speaking_greeting'
                ? 'bg-gradient-to-tr from-[#4387FF] via-[#7657FF] to-[#25D9C3] ring-4 ring-[#4387FF]/50 shadow-[#4387FF]/40'
                : voiceState === 'listening'
                ? isPatientSpeaking
                  ? 'bg-gradient-to-tr from-[#25D9C3] via-[#4387FF] to-[#7657FF] ring-4 ring-[#25D9C3] shadow-[#25D9C3]/60 scale-105'
                  : 'bg-gradient-to-tr from-[#7657FF] via-[#4387FF] to-[#25D9C3] ring-4 ring-[#25D9C3]/50 shadow-[#25D9C3]/30'
                : voiceState === 'processing_speech'
                ? 'bg-gradient-to-tr from-[#7657FF] via-[#4387FF] to-[#25D9C3] ring-4 ring-violet-400/40 shadow-violet-500/40'
                : voiceState === 'assistant_speaking'
                ? 'bg-gradient-to-tr from-[#25D9C3] via-[#4387FF] to-[#7657FF] ring-4 ring-[#25D9C3]/50 shadow-[#25D9C3]/40'
                : voiceState === 'permission_denied'
                ? 'bg-gradient-to-tr from-rose-700 via-rose-600 to-amber-600 ring-4 ring-rose-400/40 shadow-rose-500/40'
                : voiceState === 'service_unavailable'
                ? 'bg-gradient-to-tr from-rose-700 via-rose-600 to-amber-600 ring-4 ring-rose-400/40 shadow-rose-500/40'
                : 'bg-gradient-to-tr from-slate-700 via-slate-800 to-slate-900 ring-2 ring-white/20 shadow-black/40'
            }`}
          >
            {/* Inner Glow Highlights */}
            <div className="absolute inset-2 rounded-full bg-gradient-to-b from-white/20 to-transparent pointer-events-none" />

            {/* State 1: Starting conversation */}
            {voiceState === 'starting_conversation' && (
              <div className="flex flex-col items-center gap-2">
                <Loader2 className="w-11 h-11 sm:w-14 sm:h-14 text-white animate-spin" />
                <span className="text-xs sm:text-sm font-semibold text-white/90">
                  Starting call...
                </span>
              </div>
            )}

            {/* State 2: Speaking greeting */}
            {voiceState === 'speaking_greeting' && (
              <div className="flex flex-col items-center gap-2">
                <Volume2 className="w-11 h-11 sm:w-14 sm:h-14 text-white animate-pulse" />
                <span className="text-xs sm:text-sm font-bold text-[#25D9C3] tracking-wide">
                  Speaking Greeting
                </span>
              </div>
            )}

            {/* State 3: Listening (Direct Canvas Waveform - 0 React reconciliation cycles) */}
            {voiceState === 'listening' && (
              <div className="flex flex-col items-center gap-2">
                <div className="flex items-center justify-center h-9 sm:h-11">
                  <canvas
                    ref={waveformCanvasRef}
                    width={120}
                    height={44}
                    className="w-24 h-9 sm:h-11"
                    aria-label={isPatientSpeaking ? 'Patient speaking detected' : 'Microphone listening'}
                    role="img"
                  />
                </div>
                <span className="text-xs font-mono font-bold text-white bg-black/40 px-3 py-0.5 rounded-full border border-white/10">
                  {formatTimer(recordingDuration)}
                </span>
              </div>
            )}

            {/* State 4: Processing speech */}
            {voiceState === 'processing_speech' && (
              <div className="flex flex-col items-center gap-2">
                <Loader2 className="w-11 h-11 sm:w-14 sm:h-14 text-[#25D9C3] animate-spin" />
                <span className="text-xs sm:text-sm font-bold text-teal-100 tracking-wide">
                  Processing Speech
                </span>
              </div>
            )}

            {/* State 5: Assistant speaking */}
            {voiceState === 'assistant_speaking' && (
              <div className="flex flex-col items-center gap-2">
                <Volume2 className="w-11 h-11 sm:w-14 sm:h-14 text-white animate-pulse" />
                <span className="text-xs sm:text-sm font-bold text-[#25D9C3] tracking-wide">
                  Assistant Speaking
                </span>
              </div>
            )}

            {/* State 6: Microphone permission denied */}
            {voiceState === 'permission_denied' && (
              <div className="flex flex-col items-center gap-2">
                <ShieldAlert className="w-11 h-11 sm:w-14 sm:h-14 text-rose-200" />
                <span className="text-xs sm:text-sm font-bold text-white">
                  Mic Blocked
                </span>
              </div>
            )}

            {/* State 7: Voice service unavailable */}
            {voiceState === 'service_unavailable' && (
              <div className="flex flex-col items-center gap-2">
                <WifiOff className="w-11 h-11 sm:w-14 sm:h-14 text-rose-200" />
                <span className="text-xs sm:text-sm font-bold text-white">
                  Unavailable
                </span>
              </div>
            )}

            {/* State 8: Conversation ended */}
            {voiceState === 'ended' && (
              <div className="flex flex-col items-center gap-2">
                <MicOff className="w-11 h-11 sm:w-14 sm:h-14 text-white/60" />
                <span className="text-xs sm:text-sm font-bold text-white/70">
                  Call Ended
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Clear Informative State Text */}
        <div className="min-h-[4rem] flex flex-col items-center justify-center max-w-lg px-2">
          {/* State 1 */}
          {voiceState === 'starting_conversation' && (
            <>
              <h3 className="text-lg sm:text-xl font-bold tracking-tight text-white mb-1">
                Connecting to Aarogya One Hospital
              </h3>
              <p className="text-xs sm:text-sm text-violet-200/80">
                Initializing voice session and microphone...
              </p>
            </>
          )}

          {/* State 2 */}
          {voiceState === 'speaking_greeting' && (
            <>
              <h3 className="text-lg sm:text-xl font-bold text-[#25D9C3] mb-1 flex items-center gap-2">
                <Volume2 className="w-5 h-5 text-[#25D9C3] animate-pulse" />
                Welcome to Aarogya One Hospital
              </h3>
              <p className="text-xs sm:text-sm text-white/90 italic line-clamp-2 max-w-md">
                "{assistantResponse || GREETINGS_BY_LANGUAGE[selectedLanguage === 'auto' ? 'en' : selectedLanguage]}"
              </p>
            </>
          )}

          {/* State 3 */}
          {voiceState === 'listening' && (
            <>
              <h3 className="text-lg sm:text-xl font-bold text-[#25D9C3] mb-1 flex items-center gap-2">
                <span
                  className={`w-3 h-3 rounded-full ${
                    isPatientSpeaking ? 'bg-[#25D9C3] scale-125' : 'bg-[#25D9C3]'
                  } animate-ping inline-block`}
                />
                {isPatientSpeaking ? 'Listening to your speech...' : 'Listening...'}
              </h3>
              {errorMessage && !isPatientSpeaking ? (
                <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/20 border border-amber-400/30 text-amber-200 text-xs sm:text-sm font-medium animate-pulse mt-0.5">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0 text-amber-300" />
                  <span>{errorMessage}</span>
                </div>
              ) : (
                <p className="text-xs sm:text-sm text-white/80">
                  {isPatientSpeaking
                    ? 'Speech detected — will auto-submit when you pause for 1.8 seconds.'
                    : `Speak naturally in ${currentLangMeta.name}. Recording auto-submits on silence.`}
                </p>
              )}
            </>
          )}

          {/* State 4 */}
          {voiceState === 'processing_speech' && (
            <>
              <h3 className="text-lg sm:text-xl font-bold text-[#25D9C3] mb-1">
                Processing speech
              </h3>
              <p className="text-xs sm:text-sm text-white/70">
                Gnani Prisma STT transcribing & Gemini 3.5 Flash-Lite coordinating hospital care...
              </p>
            </>
          )}

          {/* State 5 */}
          {voiceState === 'assistant_speaking' && (
            <>
              <h3 className="text-lg sm:text-xl font-bold text-[#25D9C3] mb-1 flex items-center gap-2">
                <Volume2 className="w-5 h-5 text-[#25D9C3] animate-pulse" />
                Assistant speaking
              </h3>
              <p className="text-xs sm:text-sm text-white/80">
                Gnani Timbre Text-to-Speech active · Listening resumes automatically when finished.
              </p>
            </>
          )}

          {/* State 6 */}
          {voiceState === 'permission_denied' && (
            <div className="bg-rose-500/20 border border-rose-400/40 rounded-2xl p-4 max-w-md">
              <h3 className="text-sm font-bold text-rose-200 mb-1 flex items-center justify-center gap-1.5">
                <ShieldAlert className="w-4 h-4 text-rose-300" />
                Microphone permission denied
              </h3>
              <p className="text-xs text-rose-100">
                {errorMessage ||
                  'Please click the microphone icon in your browser address bar and select "Allow" to speak with MediVoice.'}
              </p>
            </div>
          )}

          {/* State 7 */}
          {voiceState === 'service_unavailable' && (
            <div className="bg-rose-500/20 border border-rose-400/40 rounded-2xl p-4 max-w-md">
              <h3 className="text-sm font-bold text-rose-200 mb-1 flex items-center justify-center gap-1.5">
                <WifiOff className="w-4 h-4 text-rose-300" />
                Voice service unavailable
              </h3>
              <p className="text-xs text-rose-100">
                {errorMessage || 'Hospital voice service temporarily unavailable. You can retry or switch to text chat.'}
              </p>
            </div>
          )}

          {/* State 8 */}
          {voiceState === 'ended' && (
            <>
              <h3 className="text-lg sm:text-xl font-bold text-white mb-1">
                Conversation ended
              </h3>
              <p className="text-xs sm:text-sm text-white/70">
                Voice call ended. You can start a new voice session or return to text chat below.
              </p>
            </>
          )}
        </div>

        {/* Live Recognized Patient Transcript Card */}
        {recognizedTranscript &&
          (voiceState === 'processing_speech' ||
            voiceState === 'assistant_speaking' ||
            voiceState === 'listening') && (
            <div className="w-full max-w-lg mt-4 p-4 rounded-2xl bg-white/10 border border-white/15 text-left text-xs backdrop-blur-md shadow-lg">
              <div className="flex items-center gap-1.5 text-[10px] font-bold text-violet-300 uppercase tracking-wider mb-1.5">
                <Mic className="w-3.5 h-3.5 text-[#25D9C3]" />
                <span>You said</span>
              </div>
              <p className="text-white text-sm italic font-medium leading-relaxed">
                "{recognizedTranscript}"
              </p>
            </div>
          )}

        {/* Assistant Spoken Response Card with Controls */}
        {assistantResponse &&
          (voiceState === 'assistant_speaking' || voiceState === 'listening' || voiceState === 'processing_speech') && (
            <div className="w-full max-w-lg mt-3 p-4 rounded-2xl bg-gradient-to-r from-violet-950/70 via-indigo-950/60 to-teal-950/50 border border-[#25D9C3]/40 text-left backdrop-blur-md shadow-xl">
              <div className="flex items-center justify-between gap-2 mb-2">
                <div className="flex items-center gap-1.5 text-[10px] font-bold text-[#25D9C3] uppercase tracking-wider">
                  <Sparkles className="w-3.5 h-3.5 text-[#25D9C3]" />
                  <span>MediVoice AI Response</span>
                  {isPlayingAudio && (
                    <span className="ml-1 inline-flex items-center gap-1 rounded-full bg-[#25D9C3]/20 px-2 py-0.5 text-[9px] text-[#25D9C3]">
                      <Volume2 className="w-3 h-3 animate-pulse" /> Playing Audio
                    </span>
                  )}
                </div>

                {/* Audio Controls */}
                <div className="flex items-center gap-1.5">
                  {voiceState !== 'processing_speech' && currentAudioUrlRef.current && (
                    <button
                      type="button"
                      onClick={handleReplay}
                      className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors cursor-pointer"
                      title="Replay assistant audio"
                      aria-label="Replay audio"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                    </button>
                  )}
                  {voiceState === 'assistant_speaking' && (
                    <button
                      type="button"
                      onClick={handleSkipToListening}
                      className="p-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors cursor-pointer"
                      title="Skip speaking and talk now"
                      aria-label="Skip to speaking"
                    >
                      <Square className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>

              <p className="text-xs sm:text-sm text-white/95 leading-relaxed">
                {assistantResponse}
              </p>
            </div>
          )}
      </div>

      {/* Bottom Action Controls Bar */}
      <div className="relative z-20 flex flex-col items-center justify-center gap-3 pt-4 border-t border-white/10 max-w-4xl mx-auto w-full">
        <div className="flex flex-wrap items-center justify-center gap-3">
          {voiceState === 'speaking_greeting' && (
            <button
              type="button"
              onClick={handleSkipToListening}
              className="flex items-center gap-2 px-6 py-3 rounded-full bg-gradient-to-r from-[#7657FF] to-[#4387FF] hover:opacity-95 text-white font-semibold text-xs sm:text-sm transition-all shadow-lg hover:scale-105 cursor-pointer"
            >
              <Mic className="w-4 h-4" />
              <span>Skip Greeting & Speak Now</span>
            </button>
          )}

          {voiceState === 'listening' && (
            <>
              <button
                type="button"
                onClick={stopRecordingAndSubmit}
                className="flex items-center gap-2 px-6 py-3 rounded-full bg-gradient-to-r from-[#25D9C3] to-[#4387FF] hover:opacity-95 text-slate-950 font-bold text-xs sm:text-sm transition-all shadow-lg shadow-teal-500/25 hover:scale-105 cursor-pointer"
              >
                <Square className="w-3.5 h-3.5 fill-slate-950" />
                <span>Done Speaking (Manual Submit)</span>
              </button>
              <button
                type="button"
                onClick={handleEndConversation}
                className="px-5 py-3 rounded-full bg-white/10 hover:bg-white/20 text-white/80 hover:text-white text-xs sm:text-sm transition-colors cursor-pointer"
              >
                End Call
              </button>
            </>
          )}

          {voiceState === 'assistant_speaking' && (
            <button
              type="button"
              onClick={handleSkipToListening}
              className="flex items-center gap-2 px-6 py-3 rounded-full bg-gradient-to-r from-[#7657FF] to-[#25D9C3] hover:opacity-95 text-white font-semibold text-xs sm:text-sm transition-all shadow-lg hover:scale-105 cursor-pointer"
            >
              <Mic className="w-4 h-4" />
              <span>Interrupt & Speak Now</span>
            </button>
          )}

          {(voiceState === 'permission_denied' || voiceState === 'service_unavailable') && (
            <button
              type="button"
              onClick={() => void initVoiceSession()}
              className="flex items-center gap-2 px-6 py-3 rounded-full bg-gradient-to-r from-[#7657FF] to-[#4387FF] hover:opacity-95 text-white font-semibold text-xs sm:text-sm transition-all shadow-lg hover:scale-105 cursor-pointer"
            >
              <RotateCcw className="w-4 h-4" />
              <span>Grant Microphone & Retry</span>
            </button>
          )}

          {voiceState === 'ended' && (
            <button
              type="button"
              onClick={() => void initVoiceSession()}
              className="flex items-center gap-2 px-6 py-3 rounded-full bg-gradient-to-r from-[#7657FF] via-[#5C45D9] to-[#25D9C3] hover:opacity-95 text-white font-semibold text-xs sm:text-sm transition-all shadow-lg shadow-violet-600/30 hover:scale-105 cursor-pointer"
            >
              <Mic className="w-4 h-4" />
              <span>Start Voice Conversation</span>
            </button>
          )}

          {/* Secondary Exit Control: Return to Text Chat */}
          <button
            type="button"
            onClick={handleCloseVoice}
            className="flex items-center gap-2 px-5 py-3 rounded-full bg-white/10 hover:bg-white/20 text-white text-xs sm:text-sm transition-colors border border-white/15 cursor-pointer"
          >
            <MessageSquare className="w-4 h-4 text-[#25D9C3]" />
            <span>Return to Text Chat</span>
          </button>
        </div>

        {/* Informative Hint */}
        <p className="text-[11px] text-white/50 text-center">
          Tip: Press <kbd className="px-1.5 py-0.5 rounded bg-white/10 text-white/80 font-mono text-[10px]">Esc</kbd> anytime to return to text chat · Conversation history is saved
        </p>
      </div>
    </div>
  );
};
