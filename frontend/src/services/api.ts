import {
  AgentConfigRead,
  AppointmentCreatePayload,
  AppointmentRead,
  AppointmentSlotRead,
  AuditEventRead,
  BookingDraftState,
  ChatRequestPayload,
  ChatResponsePayload,
  DoctorManageCreatePayload,
  DoctorRead,
  DoctorSlotCreatePayload,
  HospitalDetailRead,
  InsuranceDeskContactRead,
  InsuranceProviderManageCreatePayload,
  InsuranceProviderRead,
  InsuranceSearchResponse,
  InsuranceSupportTicketCreatePayload,
  InsuranceSupportTicketRead,
  LabOrderCreatePayload,
  LabOrderRead,
  LabOrderStatusUpdatePayload,
  LabVerificationResponse,
  MaintenanceSummaryMetrics,
  MaintenanceWorkOrderCreatePayload,
  MaintenanceWorkOrderRead,
  MaintenanceWorkOrderStatusUpdatePayload,
  StaffLoginResponse,
  StaffProfile,
  SupportedLanguage,
  ToolCallTrace,
  VoiceConfigRead,
  VoiceTranscribeResponse,
  VoiceTurnResponse,
  WorkflowExceptionRead,
} from '../types/api';

const API_BASE = '/api/v1';

export class ApiError extends Error {
  status: number;
  code: string;
  details?: Record<string, unknown>;

  constructor(
    status: number,
    message: string,
    code = 'API_ERROR',
    details?: Record<string, unknown>
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

let activeAuthToken: string | null = null;

export function setApiAuthToken(token: string | null): void {
  activeAuthToken = token;
}

export function getApiAuthToken(): string | null {
  return activeAuthToken;
}

async function requestJson<T>(
  endpoint: string,
  options: RequestInit = {},
  customToken?: string | null
): Promise<T> {
  const tokenToUse = customToken !== undefined ? customToken : activeAuthToken;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-MediVoice-Client': 'web',
    ...((options.headers as Record<string, string>) || {}),
  };

  if (tokenToUse) {
    headers['Authorization'] = `Bearer ${tokenToUse}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorBody: Record<string, unknown> = {};
    try {
      errorBody = (await response.json()) as Record<string, unknown>;
    } catch {
      // Non-JSON error body
    }

    const detail = errorBody.detail;
    if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
      const detailObj = detail as Record<string, unknown>;
      const msg =
        typeof detailObj.message === 'string'
          ? detailObj.message
          : `Request failed with HTTP ${response.status}`;
      const code =
        typeof detailObj.code === 'string' ? detailObj.code : `HTTP_${response.status}`;
      throw new ApiError(response.status, msg, code, detailObj);
    }

    if (typeof detail === 'string') {
      throw new ApiError(response.status, detail, `HTTP_${response.status}`);
    }

    if (Array.isArray(detail) && detail.length > 0) {
      const firstErr = detail[0] as Record<string, unknown>;
      const msg =
        typeof firstErr.msg === 'string'
          ? firstErr.msg
          : 'Validation error in request payload.';
      throw new ApiError(response.status, msg, 'VALIDATION_ERROR');
    }

    throw new ApiError(
      response.status,
      `Backend request failed with HTTP ${response.status}`,
      `HTTP_${response.status}`
    );
  }

  return (await response.json()) as T;
}

async function requestMultipart<T>(endpoint: string, formData: FormData): Promise<T> {
  const headers: Record<string, string> = {
    'X-MediVoice-Client': 'web',
  };
  if (activeAuthToken) {
    headers['Authorization'] = `Bearer ${activeAuthToken}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (!response.ok) {
    let errorBody: Record<string, unknown> = {};
    try {
      errorBody = (await response.json()) as Record<string, unknown>;
    } catch {
      // Non-JSON error
    }

    const detail = errorBody.detail;
    if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
      const detailObj = detail as Record<string, unknown>;
      const msg =
        typeof detailObj.message === 'string'
          ? detailObj.message
          : `Voice service error (HTTP ${response.status})`;
      const code =
        typeof detailObj.code === 'string' ? detailObj.code : `HTTP_${response.status}`;
      throw new ApiError(response.status, msg, code, detailObj);
    }

    if (typeof detail === 'string') {
      throw new ApiError(response.status, detail, `HTTP_${response.status}`);
    }

    throw new ApiError(
      response.status,
      `Voice request failed with HTTP ${response.status}`,
      `HTTP_${response.status}`
    );
  }

  return (await response.json()) as T;
}

async function requestBlob(endpoint: string, payload: unknown, correlationId?: string): Promise<Blob> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-MediVoice-Client': 'web',
    ...(correlationId ? { 'X-MediVoice-Correlation-ID': correlationId } : {}),
  };
  if (activeAuthToken) {
    headers['Authorization'] = `Bearer ${activeAuthToken}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let errorMsg = `Speech synthesis failed with HTTP ${response.status}`;
    try {
      const errorBody = (await response.json()) as Record<string, unknown>;
      const detail = errorBody?.detail;
      if (typeof detail === 'string') errorMsg = detail;
      else if (detail && typeof detail === 'object' && 'message' in detail) {
        errorMsg = String((detail as Record<string, unknown>).message);
      }
    } catch {
      // ignore
    }
    throw new ApiError(response.status, errorMsg, `HTTP_${response.status}`);
  }

  return response.blob();
}

export const medivoiceApi = {
  // Staff Auth & RBAC
  loginStaff(username: string, password: string): Promise<StaffLoginResponse> {
    return requestJson<StaffLoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  },

  getCurrentStaff(token?: string | null): Promise<StaffProfile> {
    return requestJson<StaffProfile>('/auth/me', { method: 'GET' }, token);
  },

  // Hospital & Doctors
  getHospital(hospitalId = '11111111-1111-1111-1111-111111111111'): Promise<HospitalDetailRead> {
    return requestJson<HospitalDetailRead>(`/hospitals/${hospitalId}`);
  },

  getDoctors(params?: { specialty?: string; department_name?: string }): Promise<DoctorRead[]> {
    const query = new URLSearchParams();
    if (params?.specialty) query.set('specialty', params.specialty);
    if (params?.department_name) query.set('department_name', params.department_name);
    const qs = query.toString();
    return requestJson<DoctorRead[]>(`/doctors${qs ? `?${qs}` : ''}`);
  },

  createDoctor(payload: DoctorManageCreatePayload): Promise<DoctorRead> {
    return requestJson<DoctorRead>('/doctors', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  removeDoctor(doctorId: string): Promise<DoctorRead> {
    return requestJson<DoctorRead>(`/doctors/${encodeURIComponent(doctorId)}`, {
      method: 'DELETE',
    });
  },

  getDoctorSlots(
    doctorId: string,
    params?: { date?: string; time_range?: string }
  ): Promise<AppointmentSlotRead[]> {
    const query = new URLSearchParams();
    if (params?.date) query.set('date', params.date);
    if (params?.time_range) query.set('time_range', params.time_range);
    const qs = query.toString();
    return requestJson<AppointmentSlotRead[]>(
      `/doctors/${encodeURIComponent(doctorId)}/slots${qs ? `?${qs}` : ''}`
    );
  },

  createDoctorSlot(
    doctorId: string,
    payload: DoctorSlotCreatePayload
  ): Promise<AppointmentSlotRead> {
    return requestJson<AppointmentSlotRead>(
      `/doctors/${encodeURIComponent(doctorId)}/slots`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  },

  // Appointments
  getAppointments(params?: {
    doctor_id?: string;
    patient_reference?: string;
    status?: string;
  }): Promise<AppointmentRead[]> {
    const query = new URLSearchParams();
    if (params?.doctor_id) query.set('doctor_id', params.doctor_id);
    if (params?.patient_reference) query.set('patient_reference', params.patient_reference);
    if (params?.status) query.set('status', params.status);
    const qs = query.toString();
    return requestJson<AppointmentRead[]>(`/appointments${qs ? `?${qs}` : ''}`);
  },

  getAppointmentByReference(appointmentReference: string): Promise<AppointmentRead> {
    return requestJson<AppointmentRead>(
      `/appointments/${encodeURIComponent(appointmentReference.trim())}`
    );
  },

  bookAppointment(payload: AppointmentCreatePayload): Promise<AppointmentRead> {
    return requestJson<AppointmentRead>('/appointments', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  cancelAppointment(appointmentId: string, cancellationReason?: string): Promise<AppointmentRead> {
    return requestJson<AppointmentRead>(
      `/appointments/${encodeURIComponent(appointmentId)}/cancel`,
      {
        method: 'POST',
        body: JSON.stringify({
          cancellation_reason: cancellationReason || 'Cancelled via MediVoice Portal',
        }),
      }
    );
  },

  completeAppointment(appointmentId: string, notes?: string): Promise<AppointmentRead> {
    return requestJson<AppointmentRead>(
      `/appointments/${encodeURIComponent(appointmentId)}/complete`,
      {
        method: 'POST',
        body: JSON.stringify({ notes: notes || 'Consultation completed by clinician' }),
      }
    );
  },

  recordFollowUp(
    appointmentId: string,
    followUpDateIso: string,
    followUpNotes: string
  ): Promise<AppointmentRead> {
    return requestJson<AppointmentRead>(
      `/appointments/${encodeURIComponent(appointmentId)}/follow-up`,
      {
        method: 'POST',
        body: JSON.stringify({
          follow_up_date: followUpDateIso,
          follow_up_notes: followUpNotes,
        }),
      }
    );
  },

  // Laboratory Orders & 6-Digit Verification
  getLabOrders(params?: { status?: string; department_id?: string }): Promise<LabOrderRead[]> {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.department_id) query.set('department_id', params.department_id);
    const qs = query.toString();
    return requestJson<LabOrderRead[]>(`/lab-orders${qs ? `?${qs}` : ''}`);
  },

  createLabOrder(payload: LabOrderCreatePayload): Promise<LabOrderRead> {
    return requestJson<LabOrderRead>('/lab-orders', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  updateLabOrderStatus(
    orderId: string,
    payload: LabOrderStatusUpdatePayload
  ): Promise<LabOrderRead> {
    return requestJson<LabOrderRead>(`/lab-orders/${encodeURIComponent(orderId)}/status`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  verifyLabOrderCode(
    verificationCode: string,
    sessionId?: string
  ): Promise<LabVerificationResponse> {
    return requestJson<LabVerificationResponse>('/lab-orders/verify-status', {
      method: 'POST',
      body: JSON.stringify({
        verification_code: verificationCode,
        session_id: sessionId || null,
      }),
    });
  },

  // Hospital Insurance & Human Support Escalation Tickets
  getInsuranceProviders(): Promise<InsuranceProviderRead[]> {
    return requestJson<InsuranceProviderRead[]>('/insurance/providers');
  },

  createInsuranceProvider(
    payload: InsuranceProviderManageCreatePayload
  ): Promise<InsuranceProviderRead> {
    return requestJson<InsuranceProviderRead>('/insurance/providers', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  removeInsuranceProvider(
    providerId: string
  ): Promise<{ id: string; name: string; is_active: boolean }> {
    return requestJson<{ id: string; name: string; is_active: boolean }>(
      `/insurance/providers/${encodeURIComponent(providerId)}`,
      {
        method: 'DELETE',
      }
    );
  },

  searchInsurance(params?: {
    provider_name?: string;
    plan_type?: string;
    service?: string;
    cashless?: boolean;
    q?: string;
  }): Promise<InsuranceSearchResponse> {
    const query = new URLSearchParams();
    if (params?.provider_name) query.set('provider_name', params.provider_name);
    if (params?.plan_type) query.set('plan_type', params.plan_type);
    if (params?.service) query.set('service', params.service);
    if (params?.cashless !== undefined) query.set('cashless', String(params.cashless));
    if (params?.q) query.set('q', params.q);
    const qs = query.toString();
    return requestJson<InsuranceSearchResponse>(`/insurance/search${qs ? `?${qs}` : ''}`);
  },

  getInsuranceContact(): Promise<InsuranceDeskContactRead> {
    return requestJson<InsuranceDeskContactRead>('/insurance/contact');
  },

  createInsuranceSupportTicket(
    payload: InsuranceSupportTicketCreatePayload
  ): Promise<InsuranceSupportTicketRead> {
    return requestJson<InsuranceSupportTicketRead>('/insurance/support-tickets', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  getInsuranceSupportTickets(patientReference?: string): Promise<InsuranceSupportTicketRead[]> {
    const qs = patientReference
      ? `?patient_reference=${encodeURIComponent(patientReference)}`
      : '';
    return requestJson<InsuranceSupportTicketRead[]>(`/insurance/support-tickets${qs}`);
  },

  // Hospital Facilities & Maintenance Work Orders
  getMaintenanceSummary(): Promise<MaintenanceSummaryMetrics> {
    return requestJson<MaintenanceSummaryMetrics>('/maintenance/summary');
  },

  getMaintenanceWorkOrders(params?: {
    status?: string;
    priority?: string;
    category?: string;
    q?: string;
  }): Promise<MaintenanceWorkOrderRead[]> {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.priority) query.set('priority', params.priority);
    if (params?.category) query.set('category', params.category);
    if (params?.q) query.set('q', params.q);
    const qs = query.toString();
    return requestJson<MaintenanceWorkOrderRead[]>(
      `/maintenance/work-orders${qs ? `?${qs}` : ''}`
    );
  },

  createMaintenanceWorkOrder(
    payload: MaintenanceWorkOrderCreatePayload
  ): Promise<MaintenanceWorkOrderRead> {
    return requestJson<MaintenanceWorkOrderRead>('/maintenance/work-orders', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  updateMaintenanceWorkOrderStatus(
    workOrderId: string,
    payload: MaintenanceWorkOrderStatusUpdatePayload
  ): Promise<MaintenanceWorkOrderRead> {
    return requestJson<MaintenanceWorkOrderRead>(
      `/maintenance/work-orders/${encodeURIComponent(workOrderId)}/status`,
      {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }
    );
  },

  // Workflow Exceptions & Audit Trail
  getWorkflowExceptions(params?: {
    status?: string;
    priority?: string;
    department?: string;
  }): Promise<WorkflowExceptionRead[]> {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.priority) query.set('priority', params.priority);
    if (params?.department) query.set('department', params.department);
    const qs = query.toString();
    return requestJson<WorkflowExceptionRead[]>(
      `/workflow/exceptions${qs ? `?${qs}` : ''}`
    );
  },

  triggerOverdueLabDetection(): Promise<WorkflowExceptionRead[]> {
    return requestJson<WorkflowExceptionRead[]>('/workflow/exceptions/detect', {
      method: 'POST',
    });
  },

  assignWorkflowException(
    exceptionId: string,
    assignedTo: string
  ): Promise<WorkflowExceptionRead> {
    return requestJson<WorkflowExceptionRead>(
      `/workflow/exceptions/${encodeURIComponent(exceptionId)}/assign`,
      {
        method: 'POST',
        body: JSON.stringify({ assigned_to: assignedTo }),
      }
    );
  },

  resolveWorkflowException(
    exceptionId: string,
    resolutionNote: string
  ): Promise<WorkflowExceptionRead> {
    return requestJson<WorkflowExceptionRead>(
      `/workflow/exceptions/${encodeURIComponent(exceptionId)}/resolve`,
      {
        method: 'POST',
        body: JSON.stringify({ resolution_note: resolutionNote }),
      }
    );
  },

  getAuditEvents(params?: {
    entity_type?: string;
    entity_id?: string;
    limit?: number;
  }): Promise<AuditEventRead[]> {
    const query = new URLSearchParams();
    if (params?.entity_type) query.set('entity_type', params.entity_type);
    if (params?.entity_id) query.set('entity_id', params.entity_id);
    if (params?.limit) query.set('limit', String(params.limit));
    const qs = query.toString();
    return requestJson<AuditEventRead[]>(`/workflow/audit-events${qs ? `?${qs}` : ''}`);
  },

  // AI Text-First Agent
  async sendAgentMessage(payload: ChatRequestPayload): Promise<ChatResponsePayload> {
    const raw = await requestJson<Record<string, unknown>>('/agent/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    const reply = String(
      raw.assistant_reply ?? raw.reply ?? raw.response ?? raw.message ?? ''
    ).trim();
    const step = String(raw.conversation_step ?? raw.step ?? 'READY');
    const confStatus = String(
      raw.confirmation_status ?? (raw.requires_confirmation ? 'PENDING' : 'NONE')
    );
    const reqConf = Boolean(
      raw.requires_confirmation ??
        (confStatus === 'PENDING' || step === 'AWAITING_CONFIRMATION')
    );
    const toolCalls = (raw.tool_calls || raw.tool_trace || []) as ToolCallTrace[];

    return {
      session_id: String(raw.session_id || payload.session_id || ''),
      assistant_reply: reply,
      reply,
      conversation_step: step,
      step,
      confirmation_status: confStatus,
      requires_confirmation: reqConf,
      language: (raw.language as SupportedLanguage) || 'en',
      draft: (raw.draft || {}) as BookingDraftState,
      tool_calls: toolCalls,
      tool_trace: toolCalls,
      missing_details: (raw.missing_details as string[]) || [],
      booked_appointment: (raw.booked_appointment as Record<string, unknown> | null) || null,
    };
  },

  resetAgentSession(sessionId: string): Promise<{ status: string; session_id: string }> {
    return requestJson<{ status: string; session_id: string }>(
      `/agent/sessions/${encodeURIComponent(sessionId)}/reset`,
      {
        method: 'POST',
      }
    );
  },

  getAgentConfig(): Promise<AgentConfigRead> {
    return requestJson<AgentConfigRead>('/agent/config');
  },

  // Gnani Prisma STT & Timbre TTS Voice Integration
  getVoiceConfig(): Promise<VoiceConfigRead> {
    return requestJson<VoiceConfigRead>('/voice/config');
  },

  transcribeAudio(audioBlob: Blob, language?: string): Promise<VoiceTranscribeResponse> {
    const formData = new FormData();
    formData.append('file', audioBlob, 'patient_recording.wav');
    if (language) formData.append('language', language);
    return requestMultipart<VoiceTranscribeResponse>('/voice/transcribe', formData);
  },

  synthesizeSpeech(text: string, language?: string, voice?: string, correlationId?: string): Promise<Blob> {
    return requestBlob('/voice/synthesize', {
      text,
      language,
      voice,
    }, correlationId);
  },

  async sendVoiceTurn(
    audioBlob: Blob,
    params: {
      sessionId?: string | null;
      patientReference?: string | null;
      language?: string | null;
      correlationId?: string | null;
      experimentalStreamingTts?: boolean;
    } = {}
  ): Promise<VoiceTurnResponse> {
    const formData = new FormData();
    const isWebm = audioBlob.type.includes('webm');
    const isOgg = audioBlob.type.includes('ogg');
    const filename = isWebm ? 'patient_recording.webm' : isOgg ? 'patient_recording.ogg' : 'patient_recording.wav';
    formData.append('file', audioBlob, filename);
    if (params.sessionId) formData.append('session_id', params.sessionId);
    if (params.patientReference) formData.append('patient_reference', params.patientReference);
    if (params.language) formData.append('language', params.language);
    if (params.correlationId) formData.append('correlation_id', params.correlationId);
    const endpoint = params.experimentalStreamingTts ? '/voice/respond/text' : '/voice/respond';
    const raw = await requestMultipart<VoiceTurnResponse>(endpoint, formData);
    const reply = String(raw.assistant_reply ?? raw.reply).trim();
    const step = String(raw.conversation_step ?? raw.step);
    const confStatus = raw.confirmation_status;
    const reqConf = Boolean(
      raw.requires_confirmation ?? (confStatus === 'PENDING' || step === 'AWAITING_CONFIRMATION')
    );
    const toolCalls = raw.tool_calls ?? raw.tool_trace;

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
  },

  async streamSynthesizeSpeech(
    text: string,
    language: string | undefined,
    onFirstAudio: () => void,
    signal?: AbortSignal,
    onMetric?: (stage: string, elapsedMs: number) => void,
    correlationId?: string,
  ): Promise<void> {
    const requestStartedAt = performance.now();
    const metric = (stage: string) => onMetric?.(stage, performance.now() - requestStartedAt);
    const context = new AudioContext();
    try {
      await context.resume();
    } catch (error) {
      await context.close();
      throw error;
    }
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-MediVoice-Client': 'web',
    };
    if (activeAuthToken) headers.Authorization = `Bearer ${activeAuthToken}`;
    if (correlationId) headers['X-MediVoice-Correlation-ID'] = correlationId;
    let response: Response;
    try {
      response = await fetch(`${API_BASE}/voice/synthesize/stream`, {
        method: 'POST', headers, signal,
        body: JSON.stringify({ text, language, speed: 1.0 }),
      });
    } catch (error) {
      await context.close();
      throw error;
    }
    if (!response.ok || !response.body) {
      await context.close();
      throw new Error(`Streaming TTS failed (HTTP ${response.status})`);
    }
    let nextPlayTime = context.currentTime + 0.06;
    let expectedIndex = 1;
    let started = false;
    let completed = false;
    let carry = new Uint8Array(0);
    let lastEnded: Promise<void> | null = null;
    const sources: AudioBufferSourceNode[] = [];
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = '';
    let sampleRate = 16000;
    const b64ToBytes = (value: string) => {
      const binary = atob(value);
      const out = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i += 1) out[i] = binary.charCodeAt(i);
      return out;
    };
    const queuePcm = (bytes: Uint8Array) => {
      let pcm = bytes;
      if (carry.length) {
        pcm = new Uint8Array(carry.length + bytes.length);
        pcm.set(carry); pcm.set(bytes, carry.length); carry = new Uint8Array(0);
      }
      if (pcm.length % 2) {
        carry = pcm.slice(-1);
        pcm = pcm.slice(0, -1);
      }
      if (!pcm.length) return;
      const samples = new Float32Array(pcm.length / 2);
      const view = new DataView(pcm.buffer, pcm.byteOffset, pcm.byteLength);
      for (let i = 0; i < samples.length; i += 1) samples[i] = view.getInt16(i * 2, true) / 32768;
      const buffer = context.createBuffer(1, samples.length, sampleRate);
      buffer.copyToChannel(samples, 0);
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(context.destination);
      const startAt = Math.max(nextPlayTime, context.currentTime + 0.01);
      nextPlayTime = startAt + buffer.duration;
      if (!started) {
        started = true;
        window.setTimeout(onFirstAudio, Math.max(0, (startAt - context.currentTime) * 1000));
        window.setTimeout(() => { void context.resume(); }, 0);
      }
      metric('audio_chunk_received_ms');
      lastEnded = new Promise<void>((resolve) => {
        source.onended = () => resolve();
      });
      source.start(startAt);
      sources.push(source);
    };
    const handleEvent = (block: string) => {
      let event = 'message';
      const data: string[] = [];
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        if (line.startsWith('data:')) data.push(line.slice(5).trim());
      }
      if (!data.length) return;
      const payload = JSON.parse(data.join('\n')) as Record<string, unknown>;
      if (event === 'start') {
        if (typeof payload.sample_rate === 'number') sampleRate = payload.sample_rate;
      } else if (event === 'chunk') {
        if (payload.chunk_index !== expectedIndex || typeof payload.audio !== 'string') {
          throw new Error('Streaming TTS chunk order or payload is invalid');
        }
        if (expectedIndex === 1) metric('first_audio_chunk_received_ms');
        expectedIndex += 1;
        queuePcm(b64ToBytes(payload.audio));
      } else if (event === 'error') {
        throw Object.assign(new Error(String(payload.message || 'Streaming TTS failed')), { audibleStarted: started, recoverable: payload.recoverable === true });
      } else if (event === 'complete') {
        if (expectedIndex === 1) throw new Error('Streaming TTS returned no audio');
        if (carry.length) throw new Error('Streaming TTS ended with an incomplete PCM sample');
        completed = true;
        metric('final_audio_chunk_received_ms');
      }
    };

    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        pending += decoder.decode(value, { stream: true });
        let delimiter: number;
        while ((delimiter = pending.search(/\r?\n\r?\n/)) >= 0) {
          const block = pending.slice(0, delimiter);
          const matched = pending.slice(delimiter).match(/^\r?\n\r?\n/);
          pending = pending.slice(delimiter + (matched?.[0].length || 2));
          handleEvent(block);
        }
      }
      pending += decoder.decode();
      if (pending.trim()) handleEvent(pending);
      if (!completed) throw new Error('Streaming TTS ended before completion');
      if (lastEnded) await lastEnded;
      metric('playback_completed_ms');
    } catch (error) {
      try { await reader.cancel(); } catch { /* disconnected stream */ }
      for (const source of sources) { try { source.stop(); } catch { /* already ended */ } }
      throw Object.assign(error instanceof Error ? error : new Error('Streaming TTS failed'), { audibleStarted: started });
    } finally {
      await context.close();
    }
  },
};
