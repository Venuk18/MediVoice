export type SupportedLanguage = 'en' | 'te' | 'ta' | 'kn' | 'hi';

export type StaffRoleType = 'DOCTOR' | 'LAB_OPERATOR' | 'MAINTENANCE_STAFF' | 'ADMIN';

export type WorkspaceTab = 'patient' | 'doctor' | 'lab' | 'maintenance';

export type AppRoutePath =
  | '/'
  | '/doctors'
  | '/appointments'
  | '/lab-status'
  | '/insurance'
  | '/support'
  | '/medivoice'
  | '/staff/login'
  | '/login'
  | '/doctor'
  | '/doctor/appointments'
  | '/doctor/calendar'
  | '/doctor/availability'
  | '/doctor/profile'
  | '/lab'
  | '/lab/orders'
  | '/maintenance'
  | '/maintenance/work-orders'
  | '/maintenance/new-request'
  | '/maintenance/doctors'
  | '/maintenance/insurance'
  | '/maintenance/tickets';

export interface StaffProfile {
  staff_id: string;
  username: string;
  display_name: string;
  role: StaffRoleType;
  department: string;
  doctor_id?: string | null;
  badge_label: string;
}

export interface StaffLoginResponse {
  access_token: string;
  token_type: string;
  expires_at: number;
  staff: StaffProfile;
}

export interface DepartmentRead {
  id: string;
  hospital_id: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  created_at: string;
}

export interface HospitalDetailRead {
  id: string;
  name: string;
  description?: string | null;
  address?: string | null;
  is_active: boolean;
  created_at: string;
  departments: DepartmentRead[];
}

export interface DoctorRead {
  id: string;
  hospital_id: string;
  department_id: string;
  display_name: string;
  specialty: string;
  is_active: boolean;
  created_at: string;
  department_name?: string | null;
  hospital_name?: string | null;
}

export interface DoctorManageCreatePayload {
  hospital_id?: string;
  department_id?: string | null;
  department_name?: string | null;
  display_name: string;
  specialty: string;
}

export interface DoctorSlotCreatePayload {
  start_time: string;
  end_time: string;
}

export interface AppointmentSlotRead {
  id: string;
  doctor_id: string;
  start_time: string;
  end_time: string;
  status: 'AVAILABLE' | 'BOOKED' | 'BLOCKED' | string;
  created_at: string;
}

export interface AppointmentCreatePayload {
  patient_reference: string;
  doctor_id: string;
  slot_id: string;
  reason_category: string;
}

export interface AppointmentRead {
  id: string;
  patient_reference: string;
  doctor_id: string;
  slot_id: string;
  appointment_status: 'CONFIRMED' | 'COMPLETED' | 'CANCELLED' | string;
  reason_category: string;
  created_at: string;
  updated_at: string;
  visit_completed_at?: string | null;
  follow_up_recommended: boolean;
  follow_up_date?: string | null;
  follow_up_notes?: string | null;
  doctor_name?: string | null;
  doctor_specialty?: string | null;
  slot_start_time?: string | null;
  slot_end_time?: string | null;
}

export type CanonicalLabStatus =
  | 'REGISTERED'
  | 'SAMPLE_COLLECTED'
  | 'PROCESSING'
  | 'COMPLETED'
  | 'CANCELLED';

export interface LabOrderRead {
  id: string;
  patient_reference: string;
  ordering_department_id: string;
  test_category: string;
  test_name?: string | null;
  workflow_status: string;
  lab_status: CanonicalLabStatus;
  expected_completion_at: string;
  assigned_team: string;
  delay_reason?: string | null;
  created_at: string;
  updated_at: string;
  department_name?: string | null;
}

export interface LabOrderCreatePayload {
  patient_reference: string;
  ordering_department_id?: string | null;
  test_name: string;
  test_category?: string;
  workflow_status?: string;
  assigned_team?: string;
  delay_reason?: string | null;
}

export interface LabOrderStatusUpdatePayload {
  workflow_status: string;
  delay_reason?: string | null;
}

export interface LabVerificationResponse {
  verified: boolean;
  test_name: string;
  lab_status: CanonicalLabStatus;
  status_explanation: string;
  next_step: string;
  last_updated_at: string;
  disclaimer: string;
}

export interface InsurancePlanRead {
  id: string;
  provider_id: string;
  provider_name?: string | null;
  plan_name: string;
  plan_type: string;
  coverage_summary: string;
  covered_services: string;
  supported_services: string;
  supported_services_list: string[];
  coverage_notes: string;
  copay_summary: string;
  exclusions_and_limitations?: string | null;
  preauthorization_required: boolean;
  cashless_available: boolean;
  reimbursement_available: boolean;
  network_notes?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface InsuranceProviderRead {
  id: string;
  hospital_id: string;
  name: string;
  provider_name: string;
  code: string;
  support_contact: string;
  contact_number: string;
  desk_location?: string | null;
  contact_hours?: string | null;
  is_active: boolean;
  is_synthetic_demo: boolean;
  plans: InsurancePlanRead[];
  disclaimer: string;
  created_at: string;
  updated_at: string;
}

export interface InsuranceProviderManageCreatePayload {
  hospital_id?: string;
  name: string;
  code: string;
  support_contact: string;
  desk_location?: string;
  contact_hours?: string;
  plan_name: string;
  plan_type: string;
  coverage_summary: string;
  covered_services: string;
  copay_summary: string;
  preauthorization_required: boolean;
  cashless_available: boolean;
  reimbursement_available: boolean;
}

export interface InsuranceDeskContactRead {
  hospital_name: string;
  department: string;
  desk_name: string;
  phone: string;
  contact_number: string;
  location: string;
  desk_location: string;
  hours: string;
  operating_hours: string;
  is_synthetic_demo: boolean;
  disclaimer: string;
}

export interface InsuranceSearchResponse {
  matched_count: number;
  query?: string | null;
  provider_name?: string | null;
  plan_type?: string | null;
  service?: string | null;
  cashless?: boolean | null;
  providers: InsuranceProviderRead[];
  matching_plans: InsurancePlanRead[];
  insurance_desk_contact: InsuranceDeskContactRead;
  insurance_desk: InsuranceDeskContactRead;
  is_synthetic_demo: boolean;
  disclaimer: string;
}

export interface InsuranceSupportTicketCreatePayload {
  patient_reference: string;
  provider_name?: string | null;
  plan_name?: string | null;
  question: string;
  contact_preference?: string | null;
}

export interface InsuranceSupportTicketRead {
  ticket_id: string;
  patient_reference: string;
  provider_name?: string | null;
  plan_name?: string | null;
  question: string;
  status: string;
  priority: string;
  assigned_department: string;
  created_at: string;
  disclaimer: string;
}

export type MaintenanceStatusType = 'OPEN' | 'ASSIGNED' | 'IN_PROGRESS' | 'RESOLVED';
export type MaintenancePriorityType = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface MaintenanceWorkOrderRead {
  id: string;
  hospital_id: string;
  work_order_code: string;
  title: string;
  description: string;
  category: string;
  location: string;
  equipment_reference?: string | null;
  priority: MaintenancePriorityType;
  status: MaintenanceStatusType;
  reported_by: string;
  assigned_to?: string | null;
  resolution_notes?: string | null;
  allowed_next_statuses: MaintenanceStatusType[];
  created_at: string;
  updated_at: string;
  resolved_at?: string | null;
}

export interface MaintenanceWorkOrderCreatePayload {
  hospital_id?: string;
  title: string;
  description: string;
  category: string;
  location: string;
  equipment_reference?: string | null;
  priority: MaintenancePriorityType;
  reported_by?: string;
  assigned_to?: string | null;
}

export interface MaintenanceWorkOrderStatusUpdatePayload {
  status: MaintenanceStatusType;
  assigned_to?: string | null;
  resolution_notes?: string | null;
}

export interface MaintenanceSummaryMetrics {
  total_work_orders: number;
  open_count: number;
  assigned_count: number;
  in_progress_count: number;
  resolved_count: number;
  critical_active_count: number;
  high_active_count: number;
}

export interface WorkflowExceptionRead {
  id: string;
  exception_type: string;
  title: string;
  description: string;
  priority: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string;
  responsible_department: string;
  assigned_to?: string | null;
  status: 'OPEN' | 'IN_PROGRESS' | 'RESOLVED' | 'DISMISSED' | string;
  affected_record_type: string;
  affected_record_id: string;
  detected_at: string;
  updated_at: string;
  resolved_at?: string | null;
  resolution_note?: string | null;
}

export interface AuditEventRead {
  id: string;
  actor_reference: string;
  action: string;
  entity_type: string;
  entity_id: string;
  details?: string | null;
  created_at: string;
}

export interface ToolCallTrace {
  tool_name: string;
  arguments: Record<string, unknown>;
  success: boolean;
  result_summary?: Record<string, unknown> | null;
  error?: string | null;
}

/** Tool execution shape returned by ConversationManager voice turns. */
export interface VoiceToolExecutionResult {
  tool_name: string;
  success: boolean;
  data?: unknown;
  error?: string | null;
}

export interface BookingDraftState {
  // Canonical backend BookingDraft fields.
  doctor_id?: string | null;
  doctor_name?: string | null;
  specialty?: string | null;
  slot_id?: string | null;
  slot_start_time?: string | null;
  patient_reference?: string | null;
  patient_name?: string | null;
  patient_phone?: string | null;
  is_new_patient?: boolean | null;
  reason_category?: string | null;
  // Compatibility names used by the existing frontend workflows.
  specialty_or_department?: string | null;
  selected_doctor_id?: string | null;
  selected_doctor_name?: string | null;
  selected_slot_id?: string | null;
  selected_slot_time?: string | null;
}

export interface ChatRequestPayload {
  session_id?: string | null;
  message: string;
  patient_reference?: string | null;
}

export interface SuggestedOption {
  label: string;
  value: string;
}

export interface ChatResponsePayload {
  session_id: string;
  assistant_reply: string;
  reply?: string;
  conversation_step: string;
  step?: string;
  confirmation_status: string;
  requires_confirmation: boolean;
  language: SupportedLanguage;
  draft: BookingDraftState;
  tool_calls: ToolCallTrace[];
  tool_trace?: ToolCallTrace[];
  missing_details?: string[];
  booked_appointment?: Record<string, unknown> | null;
  suggested_options?: SuggestedOption[];
}

export interface AgentConfigRead {
  provider: string;
  adapter_class: string;
  model: string;
  last_model_used?: string | null;
  live_key_configured: boolean;
  supported_languages: SupportedLanguage[];
  approved_tools: string[];
}

export interface VoiceLanguageOption {
  code: string;
  locale: string;
  name: string;
  native: string;
}

export interface VoiceConfigRead {
  voice_enabled: boolean;
  live_gnani_configured: boolean;
  stt_model: string;
  tts_model: string;
  default_voice: string;
  default_language: string;
  max_duration_seconds: number;
  supported_languages: VoiceLanguageOption[];
}

export interface VoiceTranscribeResponse {
  transcript: string;
  language_code: string;
  detected_language: string;
  confidence: number;
  model: string;
}

export interface VoiceTurnResponse {
  correlation_id?: string;
  transcript: string;
  detected_language: string;
  gnani_stt_language?: string | null;
  session_id: string;
  reply: string;
  assistant_reply?: string;
  language: string;
  step: string;
  conversation_step?: string;
  confirmation_status: string;
  requires_confirmation?: boolean;
  draft: BookingDraftState;
  tool_trace: VoiceToolExecutionResult[];
  tool_calls?: VoiceToolExecutionResult[];
  audio_base64?: string | null;
  audio_content_type?: string | null;
  tts_available: boolean;
  tts_error?: string | null;
  booked_appointment?: Record<string, any> | null;
}
