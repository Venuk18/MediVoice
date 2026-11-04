import {
  AgentConfigRead,
  AppointmentCreatePayload,
  AppointmentRead,
  AppointmentSlotRead,
  AuditEventRead,
  BookingDraftState,
  ChatRequestPayload,
  ChatResponsePayload,
  DoctorRead,
  HospitalDetailRead,
  InsuranceDeskContactRead,
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
  VoiceTurnResponse,
  WorkflowExceptionRead,
} from '../types/api';

/**
 * Resolves the API v1 base URL:
 * - If VITE_API_BASE_URL is unset or empty, defaults to '/api/v1' (routed via Vite development proxy).
 * - If VITE_API_BASE_URL is set (e.g. 'https://medivoice-backend.onrender.com'), appends '/api/v1'.
 * - If VITE_API_BASE_URL already includes '/api/v1', normalizes it without double-prefixing.
 */
export function resolveApiBaseUrl(rawEnvUrl?: string): string {
  const trimmed = (rawEnvUrl || '').trim().replace(/\/+$/, '');
  if (!trimmed) {
    return '/api/v1';
  }
  if (trimmed.endsWith('/api/v1')) {
    return trimmed;
  }
  return trimmed + '/api/v1';
}

const API_BASE = resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL);

export class ApiError extends Error {
  status: number;
  code: string;
  details?: Record<string, unknown>;

  constructor(status: number, message: string, code = 'API_ERROR', details?: Record<string, unknown>) {
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
      const code = typeof detailObj.code === 'string' ? detailObj.code : `HTTP_${response.status}`;
      throw new ApiError(response.status, msg, code, detailObj);
    }

    if (typeof detail === 'string') {
      throw new ApiError(response.status, detail, `HTTP_${response.status}`);
    }

    if (Array.isArray(detail) && detail.length > 0) {
      const firstErr = detail[0] as Record<string, unknown>;
      const msg = typeof firstErr.msg === 'string' ? firstErr.msg : 'Validation error in request payload.';
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

async function requestBlob(endpoint: string, payload: Record<string, unknown>, correlationId?: string): Promise<Blob> {
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
    throw new ApiError(response.status, `Audio synthesis failed with HTTP ${response.status}`, `HTTP_${response.status}`);
  }

  return await response.blob();
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

  // Hospital Facilities & Maintenance Work Orders (Protected by MAINTENANCE_STAFF / ADMIN)
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

    const raw = await requestMultipart<VoiceTurnResponse>('/voice/respond', formData);
    const reply = String(raw.assistant_reply ?? raw.reply).trim();
    const step = String(raw.conversation_step ?? raw.step);
    const confStatus = raw.confirmation_status;
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
  },
};
