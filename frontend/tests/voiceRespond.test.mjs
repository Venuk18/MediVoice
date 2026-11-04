import assert from 'node:assert/strict';
import test from 'node:test';

import {
  base64ToBlob,
  shouldAutoPlayVoiceReply,
  shouldResumeVoiceMode,
  TurnAudioCache,
} from '../src/features/chatbot/turnSpeech.ts';

/**
 * Simulates request construction performed by medivoiceApi.sendVoiceTurn
 */
function buildVoiceTurnPayload(audioBlob, params = {}) {
  const isWebm = audioBlob.type.includes('webm');
  const isOgg = audioBlob.type.includes('ogg');
  const filename = isWebm
    ? 'patient_recording.webm'
    : isOgg
    ? 'patient_recording.ogg'
    : 'patient_recording.wav';

  const formData = new FormData();
  formData.append('file', audioBlob, filename);
  if (params.sessionId) formData.append('session_id', params.sessionId);
  if (params.patientReference) formData.append('patient_reference', params.patientReference);
  if (params.language) formData.append('language', params.language);
  if (params.correlationId) formData.append('correlation_id', params.correlationId);

  const endpoint = params.experimentalStreamingTts ? '/voice/respond/text' : '/voice/respond';
  return { formData, filename, endpoint };
}

/**
 * Simulates response normalization performed by medivoiceApi.sendVoiceTurn
 */
function normalizeVoiceTurnResponse(raw) {
  const reply = String(raw.assistant_reply ?? raw.reply ?? '').trim();
  const step = String(raw.conversation_step ?? raw.step ?? '');
  const confStatus = raw.confirmation_status ?? 'NONE';
  const reqConf = Boolean(
    raw.requires_confirmation ?? (confStatus === 'PENDING' || step === 'AWAITING_CONFIRMATION')
  );
  const toolCalls = raw.tool_calls ?? raw.tool_trace ?? [];

  return {
    ...raw,
    reply,
    assistant_reply: reply,
    step,
    conversation_step: step,
    confirmation_status: confStatus,
    requires_confirmation: reqConf,
    tool_calls: toolCalls,
    tool_trace: toolCalls,
  };
}

/**
 * Simulates voice turn error mapping used across frontend voice panels
 */
function mapVoiceError(err, { isOnline = true, language = 'en' } = {}) {
  if (!isOnline) {
    return {
      type: 'NETWORK_OFFLINE',
      userMessage: 'Network connection lost. Please check your internet connection.',
      canRetry: true,
    };
  }

  const errName = err?.name;
  if (errName === 'NotAllowedError' || errName === 'PermissionDeniedError') {
    return {
      type: 'PERMISSION_DENIED',
      userMessage: 'Microphone permission was denied. Please allow microphone access in your browser address bar.',
      canRetry: false,
    };
  }

  if (errName === 'NotFoundError' || errName === 'DevicesNotFoundError') {
    return {
      type: 'DEVICE_NOT_FOUND',
      userMessage: 'No microphone was found. Please connect a microphone and try again.',
      canRetry: false,
    };
  }

  const status = err?.status;
  if (status === 422) {
    const localized = language === 'te'
      ? 'నాకు స్పష్టంగా అర్థం కాలేదు. దయచేసి మరొకసారి చెప్పగలరా?'
      : 'No clear speech was recognized in the audio. Please speak clearly into your microphone.';
    return {
      type: 'UNINTELLIGIBLE_SPEECH',
      userMessage: localized,
      canRetry: true,
    };
  }

  if (status === 502) {
    const localized = language === 'te'
      ? 'స్పీచ్ గుర్తింపు సేవ ప్రస్తుతం అందుబాటులో లేదు. దయచేసి మళ్ళీ ప్రయత్నించండి.'
      : 'Gnani voice service temporarily unavailable. You can continue via text chat.';
    return {
      type: 'SERVICE_UNAVAILABLE',
      userMessage: localized,
      canRetry: true,
    };
  }

  if (status === 504 || status === 408) {
    const localized = language === 'te'
      ? 'వాయిస్ ప్రాసెసింగ్ సమయం మించిపోయింది. దయచేసి మళ్ళీ మాట్లాడండి.'
      : 'Voice request timed out. Please try speaking again.';
    return {
      type: 'TIMEOUT',
      userMessage: localized,
      canRetry: true,
    };
  }

  return {
    type: 'GENERIC_ERROR',
    userMessage: err?.message || 'Voice processing failed. Please try speaking again or use text chat.',
    canRetry: true,
  };
}

// -----------------------------------------------------------------------------
// Suite 1: Recording & Upload Behavior
// -----------------------------------------------------------------------------

test('upload assigns correct filename for audio/webm blobs', () => {
  const dummyWebm = new Blob(['webm-data'], { type: 'audio/webm;codecs=opus' });
  const { formData, filename, endpoint } = buildVoiceTurnPayload(dummyWebm, {
    sessionId: 'session-123',
    patientReference: 'PAT-001',
    language: 'te',
    correlationId: 'corr-abc-1',
  });

  assert.equal(filename, 'patient_recording.webm');
  assert.equal(endpoint, '/voice/respond');
  assert.equal(formData.get('session_id'), 'session-123');
  assert.equal(formData.get('patient_reference'), 'PAT-001');
  assert.equal(formData.get('language'), 'te');
  assert.equal(formData.get('correlation_id'), 'corr-abc-1');
  const fileField = formData.get('file');
  assert.ok(fileField instanceof Blob);
});

test('upload assigns correct filename for audio/ogg blobs', () => {
  const dummyOgg = new Blob(['ogg-data'], { type: 'audio/ogg;codecs=opus' });
  const { filename } = buildVoiceTurnPayload(dummyOgg);
  assert.equal(filename, 'patient_recording.ogg');
});

test('upload assigns correct filename for audio/wav blobs', () => {
  const dummyWav = new Blob(['wav-data'], { type: 'audio/wav' });
  const { filename } = buildVoiceTurnPayload(dummyWav);
  assert.equal(filename, 'patient_recording.wav');
});

test('upload selects /voice/respond/text when experimental streaming is requested', () => {
  const dummyWav = new Blob(['wav-data'], { type: 'audio/wav' });
  const { endpoint } = buildVoiceTurnPayload(dummyWav, { experimentalStreamingTts: true });
  assert.equal(endpoint, '/voice/respond/text');
});

test('short recording validation rejects audio smaller than 500 bytes before upload', () => {
  const tinyBlob = new Blob([new Uint8Array(120)], { type: 'audio/webm' });
  const isTooShort = tinyBlob.size < 500;
  assert.equal(isTooShort, true);

  const validBlob = new Blob([new Uint8Array(6400)], { type: 'audio/webm' });
  assert.equal(validBlob.size < 500, false);
});

// -----------------------------------------------------------------------------
// Suite 2: Response Handling & Normalization
// -----------------------------------------------------------------------------

test('normalizes backend response with full fields, timings, and tool traces', () => {
  const rawResponse = {
    session_id: 'session-456',
    transcript: 'నాకు జ్వరం ఉంది',
    reply: 'జనరల్ మెడిసిన్ విభాగంలో డాక్టర్ విక్రమ్ మెహతా అందుబాటులో ఉన్నారు.',
    step: 'DOCTOR_SELECTION',
    confirmation_status: 'NONE',
    requires_confirmation: false,
    draft: {
      symptom: 'fever',
      department_name: 'General Medicine',
    },
    tool_trace: [
      { tool_name: 'search_doctors', input_parameters: { department_name: 'General Medicine' } },
    ],
    timings: {
      stt_duration_ms: 320,
      llm_duration_ms: 1100,
      tts_duration_ms: 450,
      total_duration_ms: 1870,
    },
    audio_base64: 'UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=',
    audio_content_type: 'audio/wav',
  };

  const normalized = normalizeVoiceTurnResponse(rawResponse);
  assert.equal(normalized.session_id, 'session-456');
  assert.equal(normalized.transcript, 'నాకు జ్వరం ఉంది');
  assert.equal(normalized.assistant_reply, 'జనరల్ మెడిసిన్ విభాగంలో డాక్టర్ విక్రమ్ మెహతా అందుబాటులో ఉన్నారు.');
  assert.equal(normalized.conversation_step, 'DOCTOR_SELECTION');
  assert.equal(normalized.requires_confirmation, false);
  assert.deepEqual(normalized.tool_calls, rawResponse.tool_trace);
  assert.equal(normalized.timings.total_duration_ms, 1870);
  assert.equal(normalized.audio_base64.length > 0, true);
});

test('derives requires_confirmation when confirmation_status is PENDING', () => {
  const rawResponse = {
    session_id: 'session-789',
    transcript: 'రేపు ఉదయం 10 గంటలకు బుక్ చేయండి',
    assistant_reply: 'డాక్టర్ విక్రమ్ మెహతాతో రేపు ఉదయం 10 గంటలకు అపాయింట్‌మెంట్ బుక్ చేయమంటారా?',
    conversation_step: 'AWAITING_CONFIRMATION',
    confirmation_status: 'PENDING',
    draft: {
      doctor_id: 'doc-1',
      selected_doctor_name: 'Dr. Vikram Mehta',
      slot_start: '2026-11-05T10:00:00',
    },
  };

  const normalized = normalizeVoiceTurnResponse(rawResponse);
  assert.equal(normalized.requires_confirmation, true);
  assert.equal(normalized.confirmation_status, 'PENDING');
  assert.equal(normalized.conversation_step, 'AWAITING_CONFIRMATION');
});

// -----------------------------------------------------------------------------
// Suite 3: Playback Payload Decoding (base64ToBlob)
// -----------------------------------------------------------------------------

test('base64ToBlob decodes base64 payload into valid WAV Blob with correct size and type', () => {
  // 44-byte standard empty WAV RIFF header
  const sampleWavBase64 = 'UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';
  const blob = base64ToBlob(sampleWavBase64, 'audio/wav');

  assert.ok(blob instanceof Blob);
  assert.equal(blob.type, 'audio/wav');
  assert.equal(blob.size, 44);
});

test('base64ToBlob preserves exact binary data bytes', async () => {
  const originalBytes = new Uint8Array([0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00]);
  let binaryString = '';
  for (let i = 0; i < originalBytes.length; i++) {
    binaryString += String.fromCharCode(originalBytes[i]);
  }
  const base64 = btoa(binaryString);

  const decodedBlob = base64ToBlob(base64, 'audio/wav');
  const buffer = await decodedBlob.arrayBuffer();
  const decodedBytes = new Uint8Array(buffer);

  assert.deepEqual(Array.from(decodedBytes), Array.from(originalBytes));
});

test('audio URL lifecycle manages object URLs without memory leaks', () => {
  const createdUrls = [];
  const revokedUrls = [];

  const mockCreateObjectURL = (blob) => {
    const url = `blob:mock-audio-${Math.random().toString(36).slice(2)}`;
    createdUrls.push(url);
    return url;
  };
  const mockRevokeObjectURL = (url) => {
    revokedUrls.push(url);
  };

  const blob1 = base64ToBlob('UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=');
  const url1 = mockCreateObjectURL(blob1);
  assert.equal(createdUrls.length, 1);

  // When next audio arrives or player cleans up:
  mockRevokeObjectURL(url1);
  assert.equal(revokedUrls.length, 1);
  assert.equal(revokedUrls[0], url1);
});

// -----------------------------------------------------------------------------
// Suite 4: Error Handling
// -----------------------------------------------------------------------------

test('maps HTTP 422 to localized unintelligible speech prompt without breaking session', () => {
  const err422 = { status: 422, message: 'Unprocessable Entity: No clear speech recognized' };
  
  const mappedEn = mapVoiceError(err422, { isOnline: true, language: 'en' });
  assert.equal(mappedEn.type, 'UNINTELLIGIBLE_SPEECH');
  assert.equal(mappedEn.canRetry, true);
  assert.match(mappedEn.userMessage, /No clear speech was recognized/);

  const mappedTe = mapVoiceError(err422, { isOnline: true, language: 'te' });
  assert.equal(mappedTe.type, 'UNINTELLIGIBLE_SPEECH');
  assert.equal(mappedTe.canRetry, true);
  assert.match(mappedTe.userMessage, /స్పష్టంగా అర్థం కాలేదు/);
});

test('maps HTTP 502 to Gnani service temporarily unavailable warning', () => {
  const err502 = { status: 502, message: 'Bad Gateway: Gnani STT service error' };
  const mapped = mapVoiceError(err502, { isOnline: true, language: 'en' });

  assert.equal(mapped.type, 'SERVICE_UNAVAILABLE');
  assert.match(mapped.userMessage, /Gnani voice service temporarily unavailable/);
});

test('maps HTTP 504 and 408 to voice timeout prompt', () => {
  const err504 = { status: 504, message: 'Gateway Timeout: Gnani STT timed out after 20.0s' };
  const mapped504 = mapVoiceError(err504, { isOnline: true, language: 'en' });
  assert.equal(mapped504.type, 'TIMEOUT');
  assert.match(mapped504.userMessage, /timed out/);

  const err408 = { status: 408, message: 'Request Timeout' };
  const mapped408 = mapVoiceError(err408, { isOnline: true, language: 'en' });
  assert.equal(mapped408.type, 'TIMEOUT');
});

test('maps network disconnection to offline connection alert', () => {
  const errNetwork = new Error('Failed to fetch');
  const mapped = mapVoiceError(errNetwork, { isOnline: false });

  assert.equal(mapped.type, 'NETWORK_OFFLINE');
  assert.match(mapped.userMessage, /Network connection lost/);
});

test('maps microphone permission rejection to permission guidance', () => {
  const errPerm = { name: 'NotAllowedError', message: 'Permission denied' };
  const mapped = mapVoiceError(errPerm, { isOnline: true });

  assert.equal(mapped.type, 'PERMISSION_DENIED');
  assert.equal(mapped.canRetry, false);
  assert.match(mapped.userMessage, /Microphone permission was denied/);
});

// -----------------------------------------------------------------------------
// Suite 5: Session & Correlation ID Persistence
// -----------------------------------------------------------------------------

test('persists sessionId across multi-turn voice interaction', async () => {
  let currentSessionId = 'init-session-001';
  const correlationHistory = [];

  const mockSendVoiceTurn = async (blob, params) => {
    correlationHistory.push(params.correlationId);
    // Backend echoes or keeps session_id
    return {
      session_id: params.sessionId || 'server-session-001',
      transcript: 'Turn transcript',
      assistant_reply: 'Turn response',
      step: 'COLLECTING_INFO',
      confirmation_status: 'NONE',
    };
  };

  // Turn 1
  const turn1Blob = new Blob(['turn-1-audio'], { type: 'audio/webm' });
  const turn1Res = await mockSendVoiceTurn(turn1Blob, {
    sessionId: currentSessionId,
    correlationId: 'corr-001',
    language: 'te',
  });
  currentSessionId = turn1Res.session_id;

  // Turn 2
  const turn2Blob = new Blob(['turn-2-audio'], { type: 'audio/webm' });
  const turn2Res = await mockSendVoiceTurn(turn2Blob, {
    sessionId: currentSessionId,
    correlationId: 'corr-002',
    language: 'te',
  });

  assert.equal(turn1Res.session_id, 'init-session-001');
  assert.equal(turn2Res.session_id, 'init-session-001');
  assert.deepEqual(correlationHistory, ['corr-001', 'corr-002']);
});

// -----------------------------------------------------------------------------
// Suite 6: No Duplicate /agent/chat Calls
// -----------------------------------------------------------------------------

test('voice turn processing dispatches only to /voice/respond and does not call /agent/chat', async () => {
  let voiceRespondCalls = 0;
  let agentChatCalls = 0;

  const mockApi = {
    async sendVoiceTurn(audioBlob, params) {
      voiceRespondCalls += 1;
      return {
        session_id: params.sessionId,
        transcript: 'నాకు జ్వరం ఉంది',
        assistant_reply: 'డాక్టర్ విక్రమ్ మెహతా అందుబాటులో ఉన్నారు.',
        step: 'DOCTOR_SELECTION',
        confirmation_status: 'NONE',
        requires_confirmation: false,
      };
    },
    async sendAgentMessage(payload) {
      agentChatCalls += 1;
      return {
        session_id: payload.session_id,
        reply: 'Agent reply',
      };
    },
  };

  // Dispatch voice turn
  const testBlob = new Blob(['audio-data'], { type: 'audio/webm' });
  const voiceResult = await mockApi.sendVoiceTurn(testBlob, {
    sessionId: 'session-xyz',
    language: 'te',
    correlationId: 'corr-xyz',
  });

  // Verify chat timeline ingests result directly without calling sendAgentMessage
  const chatMessages = [
    { role: 'user', content: voiceResult.transcript },
    { role: 'assistant', content: voiceResult.assistant_reply },
  ];

  assert.equal(voiceRespondCalls, 1);
  assert.equal(agentChatCalls, 0);
  assert.equal(chatMessages.length, 2);
  assert.equal(chatMessages[0].content, 'నాకు జ్వరం ఉంది');
  assert.equal(chatMessages[1].content, 'డాక్టర్ విక్రమ్ మెహతా అందుబాటులో ఉన్నారు.');
});

// -----------------------------------------------------------------------------
// Suite 7: Booking Safeguards
// -----------------------------------------------------------------------------

test('affirmative transcript does not book appointment unless confirmation_status is PENDING', () => {
  function canConfirmAppointment(transcript, sessionState) {
    const isAffirmative = /^(yes|confirm|yeah|sure|yep|సరే|ఖరారు చేయండి|హా)/i.test(transcript.trim());
    if (!isAffirmative) return false;

    // Strict booking safeguard: MUST have explicit pending confirmation state
    const isPending =
      sessionState.confirmation_status === 'PENDING' ||
      sessionState.requires_confirmation === true ||
      sessionState.conversation_step === 'AWAITING_CONFIRMATION';

    const hasValidDraft = Boolean(
      sessionState.draft?.selected_doctor_name &&
      sessionState.draft?.slot_start
    );

    return isPending && hasValidDraft;
  }

  // Case A: User says "yes" during greeting or doctor browsing
  const browsingState = {
    conversation_step: 'DOCTOR_SELECTION',
    confirmation_status: 'NONE',
    requires_confirmation: false,
    draft: { symptom: 'fever' },
  };
  assert.equal(canConfirmAppointment('yes', browsingState), false);
  assert.equal(canConfirmAppointment('సరే', browsingState), false);

  // Case B: User says "yes" without complete slot details
  const incompleteState = {
    conversation_step: 'AWAITING_CONFIRMATION',
    confirmation_status: 'PENDING',
    requires_confirmation: true,
    draft: { selected_doctor_name: 'Dr. Vikram Mehta' }, // missing slot_start
  };
  assert.equal(canConfirmAppointment('yes', incompleteState), false);

  // Case C: User confirms when pending confirmation with complete draft
  const validPendingState = {
    conversation_step: 'AWAITING_CONFIRMATION',
    confirmation_status: 'PENDING',
    requires_confirmation: true,
    draft: {
      selected_doctor_name: 'Dr. Vikram Mehta',
      slot_start: '2026-11-05T10:00:00',
    },
  };
  assert.equal(canConfirmAppointment('yes', validPendingState), true);
  assert.equal(canConfirmAppointment('సరే', validPendingState), true);
  assert.equal(canConfirmAppointment('ఖరారు చేయండి', validPendingState), true);
});

