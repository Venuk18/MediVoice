import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  AgentConfigRead,
  AppointmentRead,
  AppRoutePath,
  AuditEventRead,
  DoctorRead,
  HospitalDetailRead,
  InsuranceDeskContactRead,
  InsuranceProviderRead,
  InsuranceSupportTicketRead,
  LabOrderRead,
  MaintenanceSummaryMetrics,
  MaintenanceWorkOrderRead,
  StaffProfile,
  StaffRoleType,
  WorkflowExceptionRead,
  WorkspaceTab,
} from '../types/api';
import { ApiError, medivoiceApi, setApiAuthToken } from '../services/api';
import { useMediVoiceRoute } from '../hooks/useMediVoiceRoute';
import { clearPatientAppointmentReferences } from '../services/patientAppointmentAccess';

const STORAGE_TOKEN_KEY = 'medivoice_staff_token_v1';

export interface PlatformContextValue {
  currentRoute: AppRoutePath;
  selectedEntityId: string | null;
  navigate: (route: AppRoutePath, entityId?: string | null) => void;
  activeWorkspace: WorkspaceTab;
  setActiveWorkspace: (tab: WorkspaceTab) => void;
  activePatientRef: string;
  setActivePatientRef: (ref: string) => void;

  // MediVoice AI Prefill / Launch State
  initialChatPrompt: string | null;
  launchMediVoiceWithPrompt: (prompt?: string) => void;
  clearInitialChatPrompt: () => void;

  // Authentication & RBAC
  staffProfile: StaffProfile | null;
  token: string | null;
  isAuthenticating: boolean;
  authError: string | null;
  loginAsStaff: (username: string, password: string) => Promise<StaffProfile | null>;
  logoutStaff: () => void;
  hasRolePermission: (allowedRoles: StaffRoleType[]) => boolean;

  // Shared Operational State
  hospital: HospitalDetailRead | null;
  doctors: DoctorRead[];
  appointments: AppointmentRead[];
  labOrders: LabOrderRead[];
  insuranceProviders: InsuranceProviderRead[];
  insuranceContact: InsuranceDeskContactRead | null;
  supportTickets: InsuranceSupportTicketRead[];
  maintenanceWorkOrders: MaintenanceWorkOrderRead[];
  maintenanceSummary: MaintenanceSummaryMetrics | null;
  workflowExceptions: WorkflowExceptionRead[];
  auditEvents: AuditEventRead[];
  agentConfig: AgentConfigRead | null;

  // Sync & Connection Status
  isInitialLoading: boolean;
  isSyncing: boolean;
  backendConnected: boolean;
  syncError: string | null;
  lastSyncedAt: string | null;
  refreshOperationalData: () => Promise<void>;
  refreshMaintenanceData: () => Promise<void>;
}

const PlatformContext = createContext<PlatformContextValue | undefined>(undefined);

export const PlatformProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const {
    currentRoute,
    selectedEntityId,
    navigate,
    activeWorkspace,
    setActiveWorkspace,
  } = useMediVoiceRoute();

  const [activePatientRef, setActivePatientRef] = useState<string>('');
  const [initialChatPrompt, setInitialChatPrompt] = useState<string | null>(null);

  // Authentication & Session
  const [staffProfile, setStaffProfile] = useState<StaffProfile | null>(null);
  const [token, setToken] = useState<string | null>(() => {
    try {
      return localStorage.getItem(STORAGE_TOKEN_KEY);
    } catch {
      return null;
    }
  });
  const [isAuthenticating, setIsAuthenticating] = useState<boolean>(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [isAuthSettled, setIsAuthSettled] = useState<boolean>(false);

  // Domain State Stores
  const [hospital, setHospital] = useState<HospitalDetailRead | null>(null);
  const [doctors, setDoctors] = useState<DoctorRead[]>([]);
  const [appointments, setAppointments] = useState<AppointmentRead[]>([]);
  const [labOrders, setLabOrders] = useState<LabOrderRead[]>([]);
  const [insuranceProviders, setInsuranceProviders] = useState<InsuranceProviderRead[]>([]);
  const [insuranceContact, setInsuranceContact] = useState<InsuranceDeskContactRead | null>(null);
  const [supportTickets, setSupportTickets] = useState<InsuranceSupportTicketRead[]>([]);
  const [maintenanceWorkOrders, setMaintenanceWorkOrders] = useState<MaintenanceWorkOrderRead[]>([]);
  const [maintenanceSummary, setMaintenanceSummary] = useState<MaintenanceSummaryMetrics | null>(null);
  const [workflowExceptions, setWorkflowExceptions] = useState<WorkflowExceptionRead[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEventRead[]>([]);
  const [agentConfig, setAgentConfig] = useState<AgentConfigRead | null>(null);

  // Connection & Lifecycle Status
  const [isInitialLoading, setIsInitialLoading] = useState<boolean>(true);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [backendConnected, setBackendConnected] = useState<boolean>(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);

  // In-flight request deduplication map (prevents duplicate bursts for identical endpoints)
  const inFlightRef = useRef<Map<string, Promise<unknown>>>(new Map());

  const dedupe = useCallback(<T,>(key: string, fn: () => Promise<T>): Promise<T> => {
    const existing = inFlightRef.current.get(key) as Promise<T> | undefined;
    if (existing) {
      return existing;
    }
    const promise = fn().finally(() => {
      inFlightRef.current.delete(key);
    });
    inFlightRef.current.set(key, promise);
    return promise;
  }, []);

  const launchMediVoiceWithPrompt = useCallback(
    (prompt?: string) => {
      if (prompt) setInitialChatPrompt(prompt);
      if (currentRoute === '/') {
        const chatSection = document.getElementById('medivoice-ai-chat');
        if (chatSection) {
          chatSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
          setTimeout(() => {
            const inputEl = document.getElementById('medivoice-message-input') as HTMLInputElement | null;
            if (inputEl) inputEl.focus();
          }, 450);
          return;
        }
      }
      navigate('/medivoice');
    },
    [currentRoute, navigate]
  );

  const clearInitialChatPrompt = useCallback(() => {
    setInitialChatPrompt(null);
  }, []);

  const hasRolePermission = useCallback(
    (allowedRoles: StaffRoleType[]): boolean => {
      if (!staffProfile) return false;
      if (staffProfile.role === 'ADMIN') return true;
      return allowedRoles.includes(staffProfile.role);
    },
    [staffProfile]
  );

  // Role-Aware, Route-Aware Data Loader
  const loadContextData = useCallback(
    async (options?: { force?: boolean; isBackgroundPoll?: boolean }) => {
      const force = options?.force ?? false;
      const isBackgroundPoll = options?.isBackgroundPoll ?? false;

      if (!isBackgroundPoll) {
        setIsSyncing(true);
      }
      setSyncError(null);

      const isStaff = Boolean(staffProfile && token && staffProfile.role !== 'DEMO_VIEWER');
      const role = staffProfile?.role;
      const promises: Promise<unknown>[] = [];

      // 1. Core Public Data: Hospital profile and Doctor directory
      if (force || !hospital) {
        promises.push(
          dedupe('hospital', () => medivoiceApi.getHospital())
            .then((h) => {
              if (h) setHospital(h);
            })
            .catch(() => null)
        );
      }
      if (force || doctors.length === 0) {
        promises.push(
          dedupe('doctors', () => medivoiceApi.getDoctors())
            .then((d) => {
              if (d && d.length > 0) setDoctors(d);
            })
            .catch(() => null)
        );
      }

      // 2. Route-Dependent Lazy Loading: Insurance coverage data
      const needsInsurance =
        currentRoute === '/insurance' ||
        currentRoute === '/support' ||
        activeWorkspace === 'maintenance' ||
        role === 'MAINTENANCE_STAFF';

      if (needsInsurance && (force || insuranceProviders.length === 0)) {
        promises.push(
          dedupe('insuranceProviders', () => medivoiceApi.getInsuranceProviders())
            .then((providers) => {
              if (providers) setInsuranceProviders(providers);
            })
            .catch(() => [])
        );
        promises.push(
          dedupe('insuranceContact', () => medivoiceApi.getInsuranceContact())
            .then((contact) => {
              if (contact) setInsuranceContact(contact);
            })
            .catch(() => null)
        );
      }

      // 3. Role-Specific Operational Data (Only for verified staff sessions)
      if (isStaff) {
        // DOCTOR Persona
        if (role === 'DOCTOR' || (role === 'ADMIN' && activeWorkspace === 'doctor')) {
          promises.push(
            dedupe('appointments', () => medivoiceApi.getAppointments())
              .then((appts) => {
                if (appts) setAppointments(appts);
              })
              .catch(() => [])
          );
          promises.push(
            dedupe('auditEvents', () => medivoiceApi.getAuditEvents({ limit: 60 }))
              .then((events) => {
                if (events) setAuditEvents(events);
              })
              .catch(() => [])
          );
        }

        // LABORATORY Persona
        if (role === 'LAB_OPERATOR' || (role === 'ADMIN' && activeWorkspace === 'lab')) {
          promises.push(
            dedupe('labOrders', () => medivoiceApi.getLabOrders())
              .then((orders) => {
                if (orders) setLabOrders(orders);
              })
              .catch(() => [])
          );
          promises.push(
            dedupe('workflowExceptions', () => medivoiceApi.getWorkflowExceptions())
              .then((exceptions) => {
                if (exceptions) setWorkflowExceptions(exceptions);
              })
              .catch(() => [])
          );
          promises.push(
            dedupe('auditEvents', () => medivoiceApi.getAuditEvents({ limit: 60 }))
              .then((events) => {
                if (events) setAuditEvents(events);
              })
              .catch(() => [])
          );
        }

        // MAINTENANCE Persona
        if (role === 'MAINTENANCE_STAFF' || (role === 'ADMIN' && activeWorkspace === 'maintenance')) {
          promises.push(
            dedupe('maintenanceWorkOrders', () => medivoiceApi.getMaintenanceWorkOrders())
              .then((orders) => {
                if (orders) setMaintenanceWorkOrders(orders);
              })
              .catch(() => [])
          );
          promises.push(
            dedupe('maintenanceSummary', () => medivoiceApi.getMaintenanceSummary())
              .then((summary) => {
                if (summary) setMaintenanceSummary(summary);
              })
              .catch(() => null)
          );
          promises.push(
            dedupe('supportTickets', () => medivoiceApi.getInsuranceSupportTickets())
              .then((tickets) => {
                if (tickets) setSupportTickets(tickets);
              })
              .catch(() => [])
          );
          promises.push(
            dedupe('workflowExceptions', () => medivoiceApi.getWorkflowExceptions())
              .then((exceptions) => {
                if (exceptions) setWorkflowExceptions(exceptions);
              })
              .catch(() => [])
          );
          promises.push(
            dedupe('auditEvents', () => medivoiceApi.getAuditEvents({ limit: 60 }))
              .then((events) => {
                if (events) setAuditEvents(events);
              })
              .catch(() => [])
          );
        }
      }

      try {
        await Promise.all(promises);
        setBackendConnected(true);
        setLastSyncedAt(
          new Date().toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          })
        );
      } catch (err) {
        const message =
          err instanceof ApiError
            ? err.message
            : 'Unable to reach the Aarogya One Hospital backend service. Please verify the API server is running.';
        setSyncError(message);
        setBackendConnected(false);
      } finally {
        setIsSyncing(false);
        setIsInitialLoading(false);
      }
    },
    [
      activeWorkspace,
      currentRoute,
      dedupe,
      doctors.length,
      hospital,
      insuranceProviders.length,
      staffProfile,
      token,
    ]
  );

  const refreshOperationalData = useCallback(async () => {
    await loadContextData({ force: true });
  }, [loadContextData]);

  const refreshMaintenanceData = useCallback(async () => {
    if (!staffProfile) return;
    if (staffProfile.role !== 'MAINTENANCE_STAFF' && staffProfile.role !== 'ADMIN') {
      return;
    }
    try {
      const [orders, summary] = await Promise.all([
        dedupe('maintenanceWorkOrders', () => medivoiceApi.getMaintenanceWorkOrders()),
        dedupe('maintenanceSummary', () => medivoiceApi.getMaintenanceSummary()),
      ]);
      setMaintenanceWorkOrders(orders);
      setMaintenanceSummary(summary);
    } catch {
      // Handled by caller or RBAC gate
    }
  }, [dedupe, staffProfile]);

  // Phase 1: Authentication Settlement (Executes first on mount to avoid duplicate unauthenticated bursts)
  useEffect(() => {
    let isMounted = true;
    const initialToken = token;

    if (!initialToken) {
      setApiAuthToken(null);
      setStaffProfile(null);
      setIsAuthSettled(true);
      return;
    }

    setApiAuthToken(initialToken);
    medivoiceApi
      .getCurrentStaff(initialToken)
      .then((profile) => {
        if (isMounted) {
          setStaffProfile(profile);
          setIsAuthSettled(true);
        }
      })
      .catch(() => {
        if (isMounted) {
          setApiAuthToken(null);
          setToken(null);
          setStaffProfile(null);
          try {
            localStorage.removeItem(STORAGE_TOKEN_KEY);
          } catch {
            // ignore
          }
          setIsAuthSettled(true);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  // Phase 2: Route & Workspace-Aware Initial Loading (Only runs after auth state is settled)
  useEffect(() => {
    if (!isAuthSettled) return;
    void loadContextData();
  }, [isAuthSettled, activeWorkspace, currentRoute, staffProfile?.role]);

  // Phase 3: Background Operational Polling (30s interval for current workspace)
  useEffect(() => {
    if (!isAuthSettled) return;
    const interval = window.setInterval(() => {
      void loadContextData({ isBackgroundPoll: true });
    }, 30000);
    return () => window.clearInterval(interval);
  }, [isAuthSettled, loadContextData]);

  const loginAsStaff = useCallback(
    async (username: string, password: string): Promise<StaffProfile | null> => {
      setIsAuthenticating(true);
      setAuthError(null);
      try {
        const res = await medivoiceApi.loginStaff(username, password);
        if (res.staff.role === 'DEMO_VIEWER') {
          clearPatientAppointmentReferences();
          setActivePatientRef('');
          setAppointments([]);
          setLabOrders([]);
          setSupportTickets([]);
          setWorkflowExceptions([]);
          setAuditEvents([]);
        }
        setApiAuthToken(res.access_token);
        setToken(res.access_token);
        setStaffProfile(res.staff);
        try {
          localStorage.setItem(STORAGE_TOKEN_KEY, res.access_token);
        } catch {
          // ignore
        }
        return res.staff;
      } catch (err) {
        const msg =
          err instanceof ApiError
            ? err.message
            : 'Staff authentication failed. Please check credentials and try again.';
        setAuthError(msg);
        return null;
      } finally {
        setIsAuthenticating(false);
      }
    },
    []
  );

  const logoutStaff = useCallback(() => {
    setApiAuthToken(null);
    setToken(null);
    setStaffProfile(null);
    setAuthError(null);
    setLabOrders([]);
    setAppointments([]);
    setSupportTickets([]);
    setInsuranceProviders([]);
    setInsuranceContact(null);
    setWorkflowExceptions([]);
    setAuditEvents([]);
    setMaintenanceWorkOrders([]);
    setMaintenanceSummary(null);
    try {
      localStorage.removeItem(STORAGE_TOKEN_KEY);
    } catch {
      // ignore
    }
  }, []);

  // Memoized Platform Context Value to prevent unnecessary consumer re-renders
  const contextValue = useMemo<PlatformContextValue>(
    () => ({
      currentRoute,
      selectedEntityId,
      navigate,
      activeWorkspace,
      setActiveWorkspace,
      activePatientRef,
      setActivePatientRef,
      initialChatPrompt,
      launchMediVoiceWithPrompt,
      clearInitialChatPrompt,
      staffProfile,
      token,
      isAuthenticating,
      authError,
      loginAsStaff,
      logoutStaff,
      hasRolePermission,
      hospital,
      doctors,
      appointments,
      labOrders,
      insuranceProviders,
      insuranceContact,
      supportTickets,
      maintenanceWorkOrders,
      maintenanceSummary,
      workflowExceptions,
      auditEvents,
      agentConfig,
      isInitialLoading,
      isSyncing,
      backendConnected,
      syncError,
      lastSyncedAt,
      refreshOperationalData,
      refreshMaintenanceData,
    }),
    [
      currentRoute,
      selectedEntityId,
      navigate,
      activeWorkspace,
      setActiveWorkspace,
      activePatientRef,
      setActivePatientRef,
      initialChatPrompt,
      launchMediVoiceWithPrompt,
      clearInitialChatPrompt,
      staffProfile,
      token,
      isAuthenticating,
      authError,
      loginAsStaff,
      logoutStaff,
      hasRolePermission,
      hospital,
      doctors,
      appointments,
      labOrders,
      insuranceProviders,
      insuranceContact,
      supportTickets,
      maintenanceWorkOrders,
      maintenanceSummary,
      workflowExceptions,
      auditEvents,
      agentConfig,
      isInitialLoading,
      isSyncing,
      backendConnected,
      syncError,
      lastSyncedAt,
      refreshOperationalData,
      refreshMaintenanceData,
    ]
  );

  return (
    <PlatformContext.Provider value={contextValue}>
      {children}
    </PlatformContext.Provider>
  );
};

export function usePlatform(): PlatformContextValue {
  const ctx = useContext(PlatformContext);
  if (!ctx) {
    throw new Error('usePlatform must be used within a PlatformProvider');
  }
  return ctx;
}
