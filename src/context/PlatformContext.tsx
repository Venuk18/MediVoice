import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import {
  AgentConfigRead,
  AppointmentRead,
  AuditEventRead,
  DemoStaffAccount,
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

const STORAGE_TOKEN_KEY = 'medivoice_staff_token_v1';

interface PlatformContextValue {
  activeWorkspace: WorkspaceTab;
  setActiveWorkspace: (tab: WorkspaceTab) => void;
  activePatientRef: string;
  setActivePatientRef: (ref: string) => void;

  // Authentication & RBAC
  staffProfile: StaffProfile | null;
  token: string | null;
  demoAccounts: DemoStaffAccount[];
  isAuthenticating: boolean;
  authError: string | null;
  loginAsStaff: (username: string, password?: string) => Promise<StaffProfile | null>;
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
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspaceTab>('patient');
  const [activePatientRef, setActivePatientRef] = useState<string>('PAT-2024-9182');

  const [staffProfile, setStaffProfile] = useState<StaffProfile | null>(null);
  const [token, setToken] = useState<string | null>(() => {
    try {
      return localStorage.getItem(STORAGE_TOKEN_KEY);
    } catch {
      return null;
    }
  });
  const [demoAccounts, setDemoAccounts] = useState<DemoStaffAccount[]>([]);
  const [isAuthenticating, setIsAuthenticating] = useState<boolean>(false);
  const [authError, setAuthError] = useState<string | null>(null);

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

  const [isInitialLoading, setIsInitialLoading] = useState<boolean>(true);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [backendConnected, setBackendConnected] = useState<boolean>(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);

  const hasRolePermission = useCallback(
    (allowedRoles: StaffRoleType[]): boolean => {
      if (!staffProfile) return false;
      if (staffProfile.role === 'ADMIN') return true;
      return allowedRoles.includes(staffProfile.role);
    },
    [staffProfile]
  );

  const refreshMaintenanceData = useCallback(async () => {
    if (!staffProfile) return;
    if (staffProfile.role !== 'MAINTENANCE_STAFF' && staffProfile.role !== 'ADMIN') {
      return;
    }
    try {
      const [orders, summary] = await Promise.all([
        medivoiceApi.getMaintenanceWorkOrders(),
        medivoiceApi.getMaintenanceSummary(),
      ]);
      setMaintenanceWorkOrders(orders);
      setMaintenanceSummary(summary);
    } catch {
      // Handled by caller or RBAC gate
    }
  }, [staffProfile]);

  const refreshOperationalData = useCallback(async () => {
    setIsSyncing(true);
    setSyncError(null);
    try {
      const [
        hospRes,
        docsRes,
        apptsRes,
        labsRes,
        insProvRes,
        insContactRes,
        ticketsRes,
        excRes,
        auditsRes,
        demosRes,
        agentCfgRes,
      ] = await Promise.all([
        medivoiceApi.getHospital().catch(() => null),
        medivoiceApi.getDoctors(),
        medivoiceApi.getAppointments(),
        medivoiceApi.getLabOrders(),
        medivoiceApi.getInsuranceProviders(),
        medivoiceApi.getInsuranceContact().catch(() => null),
        medivoiceApi.getInsuranceSupportTickets().catch(() => []),
        medivoiceApi.getWorkflowExceptions().catch(() => []),
        medivoiceApi.getAuditEvents({ limit: 60 }).catch(() => []),
        medivoiceApi.getDemoAccounts().catch(() => []),
        medivoiceApi.getAgentConfig().catch(() => null),
      ]);

      if (hospRes) setHospital(hospRes);
      setDoctors(docsRes);
      setAppointments(apptsRes);
      setLabOrders(labsRes);
      setInsuranceProviders(insProvRes);
      if (insContactRes) setInsuranceContact(insContactRes);
      setSupportTickets(ticketsRes);
      setWorkflowExceptions(excRes);
      setAuditEvents(auditsRes);
      if (demosRes.length > 0) setDemoAccounts(demosRes);
      if (agentCfgRes) setAgentConfig(agentCfgRes);

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
  }, []);

  // Verify existing stored token on mount
  useEffect(() => {
    if (!token) {
      setApiAuthToken(null);
      setStaffProfile(null);
      return;
    }
    setApiAuthToken(token);
    medivoiceApi
      .getCurrentStaff(token)
      .then((profile) => {
        setStaffProfile(profile);
      })
      .catch(() => {
        setApiAuthToken(null);
        setToken(null);
        setStaffProfile(null);
        try {
          localStorage.removeItem(STORAGE_TOKEN_KEY);
        } catch {
          // ignore storage errors
        }
      });
  }, [token]);

  // Initial load & periodic sync
  useEffect(() => {
    void refreshOperationalData();
    const interval = window.setInterval(() => {
      void refreshOperationalData();
    }, 20000);
    return () => window.clearInterval(interval);
  }, [refreshOperationalData]);

  // Refresh maintenance data whenever maintenance/admin staff logs in or switches to maintenance tab
  useEffect(() => {
    if (
      staffProfile &&
      (staffProfile.role === 'MAINTENANCE_STAFF' || staffProfile.role === 'ADMIN')
    ) {
      void refreshMaintenanceData();
    } else {
      setMaintenanceWorkOrders([]);
      setMaintenanceSummary(null);
    }
  }, [staffProfile, activeWorkspace, refreshMaintenanceData]);

  const loginAsStaff = useCallback(
    async (username: string, password?: string): Promise<StaffProfile | null> => {
      setIsAuthenticating(true);
      setAuthError(null);
      try {
        const res = await medivoiceApi.loginStaff(username, password);
        setApiAuthToken(res.access_token);
        setToken(res.access_token);
        setStaffProfile(res.staff);
        try {
          localStorage.setItem(STORAGE_TOKEN_KEY, res.access_token);
        } catch {
          // ignore storage errors
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
    setMaintenanceWorkOrders([]);
    setMaintenanceSummary(null);
    try {
      localStorage.removeItem(STORAGE_TOKEN_KEY);
    } catch {
      // ignore storage errors
    }
  }, []);

  return (
    <PlatformContext.Provider
      value={{
        activeWorkspace,
        setActiveWorkspace,
        activePatientRef,
        setActivePatientRef,
        staffProfile,
        token,
        demoAccounts,
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
      }}
    >
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
