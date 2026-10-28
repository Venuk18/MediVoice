import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardList,
  HeartHandshake,
  LayoutDashboard,
  LifeBuoy,
  LogOut,
  PlusCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  Stethoscope,
  Trash2,
  UserPlus,
  Wrench,
} from 'lucide-react';
import { usePlatform } from '../../app/PlatformContext';
import { StaffAuthGate } from '../../components/StaffAuthGate';
import { ApiError, medivoiceApi } from '../../services/api';
import {
  AppRoutePath,
  MaintenancePriorityType,
  MaintenanceStatusType,
  MaintenanceWorkOrderRead,
} from '../../types/api';

const CATEGORIES = [
  'BIOMEDICAL_EQUIPMENT',
  'HVAC_CLIMATE',
  'ELECTRICAL_POWER',
  'MEDICAL_GAS',
  'SANITATION_SAFETY',
  'FACILITIES_GENERAL',
];

const PRIORITIES: MaintenancePriorityType[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];

const MAINTENANCE_SIDEBAR_ITEMS: Array<{
  label: string;
  route: AppRoutePath;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  { label: 'Operations Overview', route: '/maintenance', icon: LayoutDashboard },
  { label: 'Work Orders & Detail', route: '/maintenance/work-orders', icon: ClipboardList },
  { label: 'Create Work Order', route: '/maintenance/new-request', icon: PlusCircle },
  { label: 'Manage Doctors (Add/Remove)', route: '/maintenance/doctors', icon: Stethoscope },
  { label: 'Manage Insurances (Add/Remove)', route: '/maintenance/insurance', icon: HeartHandshake },
  { label: 'Conflicts & Support Tickets', route: '/maintenance/tickets', icon: LifeBuoy },
];

export const MaintenanceWorkspaceView: React.FC = () => {
  const {
    currentRoute,
    navigate,
    staffProfile,
    logoutStaff,
    hospital,
    doctors,
    insuranceProviders,
    supportTickets,
    maintenanceWorkOrders,
    maintenanceSummary,
    workflowExceptions,
    auditEvents,
    refreshMaintenanceData,
    refreshOperationalData,
  } = usePlatform();

  // Work Order Filters & Selection
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [priorityFilter, setPriorityFilter] = useState<string>('ALL');
  const [categoryFilter, setCategoryFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedWorkOrderId, setSelectedWorkOrderId] = useState<string | null>(null);

  // Lifecycle Transition Inspector
  const [targetStatus, setTargetStatus] = useState<MaintenanceStatusType | ''>('');
  const [assignedToInput, setAssignedToInput] = useState<string>('');
  const [resolutionNotesInput, setResolutionNotesInput] = useState<string>('');
  const [showTransitionConfirm, setShowTransitionConfirm] = useState<boolean>(false);
  const [isUpdatingWorkOrder, setIsUpdatingWorkOrder] = useState<boolean>(false);

  // Create Work Order Form (`/maintenance/new-request`)
  const [newTitle, setNewTitle] = useState<string>('');
  const [newDescription, setNewDescription] = useState<string>('');
  const [newCategory, setNewCategory] = useState<string>('BIOMEDICAL_EQUIPMENT');
  const [newLocation, setNewLocation] = useState<string>('Block B · Floor 2 · Diagnostic Wing');
  const [newEquipmentRef, setNewEquipmentRef] = useState<string>('BIO-UPS-204');
  const [newPriority, setNewPriority] = useState<MaintenancePriorityType>('HIGH');
  const [newAssignedTo, setNewAssignedTo] = useState<string>('');
  const [isCreatingWorkOrder, setIsCreatingWorkOrder] = useState<boolean>(false);

  // Manage Doctors Form (`/maintenance/doctors`)
  const [docDisplayName, setDocDisplayName] = useState<string>('');
  const [docSpecialty, setDocSpecialty] = useState<string>('Cardiology');
  const [docDepartmentName, setDocDepartmentName] = useState<string>('Cardiology');
  const [isAddingDoctor, setIsAddingDoctor] = useState<boolean>(false);
  const [removingDoctorId, setRemovingDoctorId] = useState<string | null>(null);

  // Manage Insurance Providers Form (`/maintenance/insurance`)
  const [insName, setInsName] = useState<string>('');
  const [insCode, setInsCode] = useState<string>('INS-NEW');
  const [insContact, setInsContact] = useState<string>('1800-100-4299 (TPA Desk)');
  const [insPlanName, setInsPlanName] = useState<string>('');
  const [insPlanType, setInsPlanType] = useState<string>('Family Floater & Cashless');
  const [insCoveredServices, setInsCoveredServices] = useState<string>(
    'Cardiology, Neurology, Orthopedics, Pediatrics, General Medicine, Diagnostics'
  );
  const [insCashless, setInsCashless] = useState<boolean>(true);
  const [isAddingInsurance, setIsAddingInsurance] = useState<boolean>(false);
  const [removingInsuranceId, setRemovingInsuranceId] = useState<string | null>(null);

  // Conflicts & Human Support Tickets Resolution (`/maintenance/tickets`)
  const [assigneeByException, setAssigneeByException] = useState<Record<string, string>>({});
  const [noteByException, setNoteByException] = useState<Record<string, string>>({});
  const [processingExceptionId, setProcessingExceptionId] = useState<string | null>(null);

  const [banner, setBanner] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

  const filteredWorkOrders = useMemo(() => {
    return maintenanceWorkOrders.filter((wo) => {
      if (statusFilter !== 'ALL' && wo.status !== statusFilter) return false;
      if (priorityFilter !== 'ALL' && wo.priority !== priorityFilter) return false;
      if (categoryFilter !== 'ALL' && wo.category !== categoryFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.trim().toLowerCase();
        const hay = `${wo.work_order_code} ${wo.title} ${wo.location} ${
          wo.equipment_reference || ''
        } ${wo.assigned_to || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [maintenanceWorkOrders, statusFilter, priorityFilter, categoryFilter, searchQuery]);

  const selectedWorkOrder: MaintenanceWorkOrderRead | null = useMemo(() => {
    if (!selectedWorkOrderId) return filteredWorkOrders[0] || null;
    return (
      filteredWorkOrders.find((w) => w.id === selectedWorkOrderId) ||
      maintenanceWorkOrders.find((w) => w.id === selectedWorkOrderId) ||
      filteredWorkOrders[0] ||
      null
    );
  }, [filteredWorkOrders, maintenanceWorkOrders, selectedWorkOrderId]);

  useEffect(() => {
    if (selectedWorkOrder) {
      setTargetStatus(selectedWorkOrder.allowed_next_statuses[0] || '');
      setAssignedToInput(
        selectedWorkOrder.assigned_to || staffProfile?.display_name || 'Karthikeya Rao'
      );
      setResolutionNotesInput(selectedWorkOrder.resolution_notes || '');
      setShowTransitionConfirm(false);
    }
  }, [selectedWorkOrder?.id]);

  // ============================================================================
  // Handlers: Work Orders
  // ============================================================================
  const handleCommitWorkOrderTransition = async () => {
    if (!selectedWorkOrder || !targetStatus) return;
    setIsUpdatingWorkOrder(true);
    setBanner(null);
    try {
      const updated = await medivoiceApi.updateMaintenanceWorkOrderStatus(selectedWorkOrder.id, {
        status: targetStatus,
        assigned_to: assignedToInput.trim() || null,
        resolution_notes: resolutionNotesInput.trim() || null,
      });
      setBanner({
        type: 'success',
        message: `Work order ${updated.work_order_code} transitioned to ${updated.status}.`,
      });
      setShowTransitionConfirm(false);
      await Promise.all([refreshMaintenanceData(), refreshOperationalData()]);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : 'Failed to transition maintenance work order.';
      setBanner({ type: 'error', message: msg });
    } finally {
      setIsUpdatingWorkOrder(false);
    }
  };

  const handleCreateWorkOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim() || !newDescription.trim() || !newLocation.trim()) return;
    setIsCreatingWorkOrder(true);
    setBanner(null);
    try {
      const created = await medivoiceApi.createMaintenanceWorkOrder({
        title: newTitle.trim(),
        description: newDescription.trim(),
        category: newCategory,
        location: newLocation.trim(),
        equipment_reference: newEquipmentRef.trim() || null,
        priority: newPriority,
        reported_by: staffProfile?.display_name || 'Facilities Engineering Desk',
        assigned_to: newAssignedTo.trim() || null,
      });
      setBanner({
        type: 'success',
        message: `Created work order ${created.work_order_code} (${created.title}) in ${created.status} state.`,
      });
      setNewTitle('');
      setNewDescription('');
      setSelectedWorkOrderId(created.id);
      await Promise.all([refreshMaintenanceData(), refreshOperationalData()]);
      navigate('/maintenance/work-orders');
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Unable to create maintenance work order.';
      setBanner({ type: 'error', message: msg });
    } finally {
      setIsCreatingWorkOrder(false);
    }
  };

  // ============================================================================
  // Handlers: Add or Remove Doctors (`/maintenance/doctors`)
  // ============================================================================
  const handleAddDoctor = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!docDisplayName.trim() || !docSpecialty.trim()) return;
    setIsAddingDoctor(true);
    setBanner(null);
    try {
      const created = await medivoiceApi.createDoctor({
        display_name: docDisplayName.trim(),
        specialty: docSpecialty.trim(),
        department_name: docDepartmentName.trim() || docSpecialty.trim(),
      });
      setBanner({
        type: 'success',
        message: `Added ${created.display_name} (${created.specialty}) to active hospital directory with 6 open appointment slots.`,
      });
      setDocDisplayName('');
      await refreshOperationalData();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Unable to add doctor.';
      setBanner({ type: 'error', message: msg });
    } finally {
      setIsAddingDoctor(false);
    }
  };

  const handleRemoveDoctor = async (doctorId: string, name: string) => {
    setRemovingDoctorId(doctorId);
    setBanner(null);
    try {
      await medivoiceApi.removeDoctor(doctorId);
      setBanner({
        type: 'success',
        message: `Removed ${name} from the active hospital doctor directory.`,
      });
      await refreshOperationalData();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : 'Unable to remove doctor.';
      setBanner({ type: 'error', message: msg });
    } finally {
      setRemovingDoctorId(null);
    }
  };

  // ============================================================================
  // Handlers: Add or Remove Insurance Providers (`/maintenance/insurance`)
  // ============================================================================
  const handleAddInsuranceProvider = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!insName.trim() || !insPlanName.trim()) return;
    setIsAddingInsurance(true);
    setBanner(null);
    try {
      const created = await medivoiceApi.createInsuranceProvider({
        name: insName.trim(),
        code: insCode.trim() || 'INS-DEMO',
        support_contact: insContact.trim() || '1800-100-4299',
        plan_name: insPlanName.trim(),
        plan_type: insPlanType.trim() || 'Family Floater & Cashless',
        coverage_summary:
          'Covers inpatient hospitalization, surgical procedures, and diagnostic workups subject to policy terms.',
        covered_services: insCoveredServices.trim(),
        copay_summary: '10% standard co-pay; pre-authorization required.',
        preauthorization_required: true,
        cashless_available: insCashless,
        reimbursement_available: true,
      });
      setBanner({
        type: 'success',
        message: `Added insurance provider "${created.name}" (${created.code}) and plan "${insPlanName.trim()}" to active hospital directory.`,
      });
      setInsName('');
      setInsPlanName('');
      await refreshOperationalData();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Unable to add insurance provider.';
      setBanner({ type: 'error', message: msg });
    } finally {
      setIsAddingInsurance(false);
    }
  };

  const handleRemoveInsuranceProvider = async (providerId: string, name: string) => {
    setRemovingInsuranceId(providerId);
    setBanner(null);
    try {
      await medivoiceApi.removeInsuranceProvider(providerId);
      setBanner({
        type: 'success',
        message: `Removed insurance provider "${name}" from active hospital coverage directory.`,
      });
      await refreshOperationalData();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Unable to remove insurance provider.';
      setBanner({ type: 'error', message: msg });
    } finally {
      setRemovingInsuranceId(null);
    }
  };

  // ============================================================================
  // Handlers: Conflicts & Human Support Needed Tickets (`/maintenance/tickets`)
  // ============================================================================
  const handleAssignException = async (exceptionId: string) => {
    const assignee =
      (assigneeByException[exceptionId] || '').trim() ||
      staffProfile?.display_name ||
      'TPA & Operations Coordinator';
    setProcessingExceptionId(exceptionId);
    setBanner(null);
    try {
      const updated = await medivoiceApi.assignWorkflowException(exceptionId, assignee);
      setBanner({
        type: 'success',
        message: `Assigned ticket/conflict "${updated.title}" to ${updated.assigned_to}.`,
      });
      await refreshOperationalData();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Unable to assign workflow ticket.';
      setBanner({ type: 'error', message: msg });
    } finally {
      setProcessingExceptionId(null);
    }
  };

  const handleResolveException = async (exceptionId: string) => {
    const note =
      (noteByException[exceptionId] || '').trim() ||
      `Verified and resolved by ${staffProfile?.display_name || 'Hospital Operations'}.`;
    setProcessingExceptionId(exceptionId);
    setBanner(null);
    try {
      const updated = await medivoiceApi.resolveWorkflowException(exceptionId, note);
      setBanner({
        type: 'success',
        message: `Marked "${updated.title}" as RESOLVED.`,
      });
      await refreshOperationalData();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Unable to resolve workflow ticket.';
      setBanner({ type: 'error', message: msg });
    } finally {
      setProcessingExceptionId(null);
    }
  };

  const operationalConflicts = useMemo(() => {
    return workflowExceptions.filter((e) => e.exception_type !== 'INSURANCE_SUPPORT_TICKET');
  }, [workflowExceptions]);

  const humanSupportExceptionRecords = useMemo(() => {
    return workflowExceptions.filter((e) => e.exception_type === 'INSURANCE_SUPPORT_TICKET');
  }, [workflowExceptions]);

  return (
    <StaffAuthGate
      requiredRoles={['MAINTENANCE_STAFF']}
      workspaceTitle="Hospital Maintenance & Operations Control Center"
      workspaceSubtitle="Manage facilities work orders, add or remove hospital doctors and insurance providers, and resolve operational conflicts & human-support tickets."
    >
      <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A] flex flex-col lg:flex-row">
        {/* Left Role-Specific Sidebar */}
        <aside className="w-full lg:w-68 shrink-0 border-b lg:border-b-0 lg:border-r border-slate-200 bg-white flex flex-col justify-between p-5">
          <div className="space-y-6">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold text-teal-700">
                <Wrench className="h-4 w-4" />
                <span>Maintenance & Operations</span>
              </div>
              <h2 className="mt-1 font-display text-lg font-bold text-slate-900">
                Aarogya One Hospital
              </h2>
              <p className="text-xs text-slate-500">
                {staffProfile?.display_name} · {staffProfile?.role}
              </p>
            </div>

            <nav aria-label="Maintenance Workspace Navigation" className="space-y-1">
              {MAINTENANCE_SIDEBAR_ITEMS.map((item) => {
                const Icon = item.icon;
                const isActive = currentRoute === item.route;
                return (
                  <button
                    key={item.route}
                    type="button"
                    onClick={() => navigate(item.route)}
                    className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors whitespace-nowrap ${
                      isActive
                        ? 'bg-teal-600 text-white font-semibold'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                    }`}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </nav>
          </div>

          <div className="mt-6 border-t border-slate-200 pt-4 space-y-2">
            <button
              type="button"
              onClick={() => navigate('/')}
              className="flex w-full items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-100 whitespace-nowrap"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Patient Hospital Website</span>
            </button>
            <button
              type="button"
              onClick={logoutStaff}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-rose-600 hover:bg-rose-50 whitespace-nowrap"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span>Sign Out ({staffProfile?.username})</span>
            </button>
          </div>
        </aside>

        {/* Main Viewport */}
        <div className="flex-1 p-6 sm:p-8 space-y-6 max-w-[1200px]">
          <div className="flex flex-col justify-between gap-4 border-b border-slate-200 pb-5 sm:flex-row sm:items-center">
            <div>
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <span>Maintenance & Operations</span>
                <span aria-hidden="true">/</span>
                <span className="font-semibold text-slate-800">
                  {MAINTENANCE_SIDEBAR_ITEMS.find((i) => i.route === currentRoute)?.label ||
                    'Overview'}
                </span>
              </div>
              <h1 className="mt-1 font-display text-2xl font-bold text-slate-900">
                Hospital Facilities, Roster, Insurance & Ticket Operations
              </h1>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => navigate('/maintenance/new-request')}
                className="inline-flex items-center gap-1.5 rounded-lg bg-teal-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-teal-700 whitespace-nowrap"
              >
                <PlusCircle className="h-3.5 w-3.5" />
                <span>New Work Order</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  void refreshMaintenanceData();
                  void refreshOperationalData();
                }}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 whitespace-nowrap"
              >
                <RefreshCw className="h-3.5 w-3.5 text-teal-600" />
                <span>Sync All</span>
              </button>
            </div>
          </div>

          {banner && (
            <div
              className={`flex items-center justify-between rounded-lg border p-4 text-xs ${
                banner.type === 'success'
                  ? 'border-emerald-300 bg-emerald-50 text-emerald-900'
                  : 'border-rose-300 bg-rose-50 text-rose-900'
              }`}
            >
              <div className="flex items-center gap-2">
                {banner.type === 'success' ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                ) : (
                  <AlertCircle className="h-4 w-4 text-rose-600" />
                )}
                <span>{banner.message}</span>
              </div>
              <button
                type="button"
                onClick={() => setBanner(null)}
                className="underline opacity-80 hover:opacity-100"
              >
                Dismiss
              </button>
            </div>
          )}

          {/* KPI Strip */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <span className="text-xs text-slate-500">Open Work Orders</span>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-amber-700">
                {maintenanceSummary?.open_count ??
                  maintenanceWorkOrders.filter((w) => w.status === 'OPEN').length}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <span className="text-xs text-slate-500">Assigned / In Progress</span>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-teal-700">
                {(maintenanceSummary?.assigned_count ?? 0) +
                  (maintenanceSummary?.in_progress_count ?? 0)}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <span className="text-xs text-slate-500">Resolved Work Orders</span>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-emerald-700">
                {maintenanceSummary?.resolved_count ??
                  maintenanceWorkOrders.filter((w) => w.status === 'RESOLVED').length}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <span className="text-xs text-slate-500">Active Doctors</span>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-slate-900">
                {doctors.length}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <span className="text-xs text-slate-500">Active Insurers</span>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-slate-900">
                {insuranceProviders.length}
              </p>
            </div>
            <div className="rounded-xl border border-rose-200 bg-white p-4">
              <span className="text-xs text-rose-700">Conflicts & Tickets</span>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-rose-600">
                {workflowExceptions.filter((e) => e.status !== 'RESOLVED').length}
              </p>
            </div>
          </div>

          {/* =================================================================
              OVERVIEW (`/maintenance`)
          ================================================================= */}
          {currentRoute === '/maintenance' && (
            <div className="space-y-6">
              {/* Quick Operational Action Cards */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div className="rounded-xl border border-slate-200 bg-white p-5 flex flex-col justify-between">
                  <div>
                    <p className="text-xs font-semibold text-teal-700">01. Physician Roster</p>
                    <h3 className="mt-1 font-display text-base font-bold text-slate-900">
                      Add or Remove Hospital Doctors
                    </h3>
                    <p className="mt-1 text-xs text-slate-600">
                      Currently {doctors.length} active specialists across 5 clinical departments.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => navigate('/maintenance/doctors')}
                    className="mt-4 rounded-lg bg-slate-900 px-3.5 py-2 text-xs font-semibold text-white hover:bg-slate-800"
                  >
                    Manage Doctors →
                  </button>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-5 flex flex-col justify-between">
                  <div>
                    <p className="text-xs font-semibold text-teal-700">02. Insurance Registry</p>
                    <h3 className="mt-1 font-display text-base font-bold text-slate-900">
                      Add or Remove Insurance Plans
                    </h3>
                    <p className="mt-1 text-xs text-slate-600">
                      Currently {insuranceProviders.length} active insurance providers for patient
                      search.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => navigate('/maintenance/insurance')}
                    className="mt-4 rounded-lg bg-slate-900 px-3.5 py-2 text-xs font-semibold text-white hover:bg-slate-800"
                  >
                    Manage Insurances →
                  </button>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white p-5 flex flex-col justify-between">
                  <div>
                    <p className="text-xs font-semibold text-rose-700">
                      03. Escalations & Conflicts
                    </p>
                    <h3 className="mt-1 font-display text-base font-bold text-slate-900">
                      Conflicts & Human-Support Tickets
                    </h3>
                    <p className="mt-1 text-xs text-slate-600">
                      {operationalConflicts.length} operational SLA conflict(s) ·{' '}
                      {humanSupportExceptionRecords.length} human-support insurance ticket(s).
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => navigate('/maintenance/tickets')}
                    className="mt-4 rounded-lg bg-teal-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-teal-700"
                  >
                    Resolve Tickets & Conflicts →
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* =================================================================
              WORK ORDERS & DETAIL (`/maintenance`, `/maintenance/work-orders`)
          ================================================================= */}
          {(currentRoute === '/maintenance' ||
            currentRoute === '/maintenance/work-orders') && (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
              <div className="lg:col-span-7 rounded-xl border border-slate-200 bg-white overflow-hidden">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 p-4">
                  <h2 className="font-display text-sm font-bold text-slate-900">
                    Facilities Work Orders ({filteredWorkOrders.length})
                  </h2>
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="relative">
                      <Search className="pointer-events-none absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-400" />
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Code, title, location..."
                        className="rounded-lg border border-slate-200 bg-slate-50 pl-8 pr-2.5 py-1 text-xs text-slate-900"
                      />
                    </div>
                    <select
                      value={statusFilter}
                      onChange={(e) => setStatusFilter(e.target.value)}
                      aria-label="Filter work orders by status"
                      className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 font-mono text-xs text-slate-700"
                    >
                      <option value="ALL">All Statuses</option>
                      <option value="OPEN">OPEN</option>
                      <option value="ASSIGNED">ASSIGNED</option>
                      <option value="IN_PROGRESS">IN_PROGRESS</option>
                      <option value="RESOLVED">RESOLVED</option>
                    </select>
                  </div>
                </div>

                <div className="divide-y divide-slate-200">
                  {filteredWorkOrders.map((wo) => {
                    const isSelected = selectedWorkOrder?.id === wo.id;
                    return (
                      <div
                        key={wo.id}
                        onClick={() => setSelectedWorkOrderId(wo.id)}
                        className={`cursor-pointer p-4 transition-colors text-xs ${
                          isSelected ? 'bg-teal-50/80' : 'hover:bg-slate-50'
                        }`}
                      >
                        <div className="flex items-center justify-between font-mono">
                          <span className="font-bold text-teal-700">
                            {wo.work_order_code} · {wo.priority}
                          </span>
                          <span className="font-semibold text-slate-800">{wo.status}</span>
                        </div>
                        <h3 className="mt-1 font-display text-sm font-bold text-slate-900">
                          {wo.title}
                        </h3>
                        <p className="mt-0.5 text-slate-600 line-clamp-2">{wo.description}</p>
                        <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
                          <span>Location: {wo.location}</span>
                          <span>Assigned: {wo.assigned_to || 'Unassigned'}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Right 5 Cols: Work-Order Detail & Lifecycle Transition */}
              <div className="lg:col-span-5 rounded-xl border border-slate-200 bg-white p-5 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-200 pb-3">
                  <h3 className="font-display text-sm font-bold text-slate-900">
                    Work-Order Detail & Lifecycle
                  </h3>
                  <span className="font-mono text-[11px] text-teal-700">
                    OPEN → ASSIGNED → IN_PROGRESS → RESOLVED
                  </span>
                </div>

                {!selectedWorkOrder ? (
                  <p className="py-8 text-center text-xs text-slate-500">
                    Select a work order to inspect and transition its status.
                  </p>
                ) : (
                  <div className="space-y-4 text-xs">
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-1.5">
                      <div className="flex items-center justify-between font-mono">
                        <span className="font-bold text-slate-900">
                          {selectedWorkOrder.work_order_code}
                        </span>
                        <span className="font-semibold text-teal-700">
                          {selectedWorkOrder.status}
                        </span>
                      </div>
                      <p className="font-semibold text-slate-900">{selectedWorkOrder.title}</p>
                      <p className="text-slate-600">{selectedWorkOrder.description}</p>
                      <p className="font-mono text-[11px] text-slate-500">
                        Category: {selectedWorkOrder.category} · Location:{' '}
                        {selectedWorkOrder.location}
                      </p>
                    </div>

                    {selectedWorkOrder.allowed_next_statuses.length === 0 ? (
                      <div className="flex items-center gap-2 rounded-lg border border-emerald-300 bg-emerald-50 p-3.5 text-emerald-900">
                        <ShieldCheck className="h-4 w-4 shrink-0 text-emerald-600" />
                        <span>
                          Work order is in terminal <strong>RESOLVED</strong> state.{' '}
                          {selectedWorkOrder.resolution_notes}
                        </span>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        <div>
                          <label className="block font-medium text-slate-700">
                            Permitted Next Lifecycle Stage
                          </label>
                          <div className="mt-1.5 flex flex-wrap gap-2">
                            {selectedWorkOrder.allowed_next_statuses.map((st) => (
                              <button
                                key={st}
                                type="button"
                                onClick={() => {
                                  setTargetStatus(st);
                                  setShowTransitionConfirm(false);
                                }}
                                className={`rounded-lg border px-3 py-1.5 font-mono text-xs font-semibold ${
                                  targetStatus === st
                                    ? 'border-teal-600 bg-teal-600 text-white'
                                    : 'border-slate-200 bg-slate-50 text-slate-700'
                                }`}
                              >
                                → {st}
                              </button>
                            ))}
                          </div>
                        </div>

                        <div>
                          <label className="block font-medium text-slate-700">
                            Assigned Engineer (Required for ASSIGNED / IN_PROGRESS)
                          </label>
                          <input
                            type="text"
                            value={assignedToInput}
                            onChange={(e) => setAssignedToInput(e.target.value)}
                            className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-slate-900"
                          />
                        </div>

                        <div>
                          <label className="block font-medium text-slate-700">
                            Resolution Notes (Required for RESOLVED)
                          </label>
                          <textarea
                            rows={2}
                            value={resolutionNotesInput}
                            onChange={(e) => setResolutionNotesInput(e.target.value)}
                            placeholder="Document root cause and safety verification..."
                            className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2.5 text-slate-900"
                          />
                        </div>

                        {!showTransitionConfirm ? (
                          <button
                            type="button"
                            onClick={() => setShowTransitionConfirm(true)}
                            className="w-full rounded-lg bg-teal-600 px-4 py-2 font-semibold text-white hover:bg-teal-700"
                          >
                            Prepare Transition to {targetStatus}
                          </button>
                        ) : (
                          <div className="rounded-lg border border-amber-300 bg-amber-50 p-3.5 space-y-2">
                            <p className="font-semibold text-amber-900">
                              Confirm transitioning {selectedWorkOrder.work_order_code} to{' '}
                              {targetStatus}?
                            </p>
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                disabled={isUpdatingWorkOrder}
                                onClick={() => void handleCommitWorkOrderTransition()}
                                className="rounded-lg bg-slate-900 px-3.5 py-1.5 font-semibold text-white"
                              >
                                {isUpdatingWorkOrder ? 'Saving...' : 'Confirm Transition'}
                              </button>
                              <button
                                type="button"
                                onClick={() => setShowTransitionConfirm(false)}
                                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-slate-700"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* =================================================================
              CREATE WORK ORDER (`/maintenance/new-request`)
          ================================================================= */}
          {currentRoute === '/maintenance/new-request' && (
            <form
              onSubmit={(e) => void handleCreateWorkOrder(e)}
              className="rounded-xl border border-slate-200 bg-white p-6 space-y-4 max-w-3xl text-xs"
            >
              <div className="border-b border-slate-200 pb-3">
                <h2 className="font-display text-base font-bold text-slate-900">
                  Create Facilities / Biomedical Maintenance Work Order
                </h2>
                <p className="text-slate-500">
                  Persists a new work order via{' '}
                  <span className="font-mono">POST /api/v1/maintenance/work-orders</span>.
                </p>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="block font-medium text-slate-700">Issue Title</label>
                  <input
                    type="text"
                    required
                    minLength={3}
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                    placeholder="e.g. MRI Chiller Loop Pressure Alert"
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </div>
                <div>
                  <label className="block font-medium text-slate-700">Category</label>
                  <select
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono"
                  >
                    {CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block font-medium text-slate-700">Location</label>
                  <input
                    type="text"
                    required
                    value={newLocation}
                    onChange={(e) => setNewLocation(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </div>
                <div>
                  <label className="block font-medium text-slate-700">Equipment Reference</label>
                  <input
                    type="text"
                    value={newEquipmentRef}
                    onChange={(e) => setNewEquipmentRef(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono"
                  />
                </div>
                <div>
                  <label className="block font-medium text-slate-700">Priority</label>
                  <select
                    value={newPriority}
                    onChange={(e) => setNewPriority(e.target.value as MaintenancePriorityType)}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono"
                  >
                    {PRIORITIES.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block font-medium text-slate-700">
                    Initial Assigned Staff (Optional)
                  </label>
                  <input
                    type="text"
                    value={newAssignedTo}
                    onChange={(e) => setNewAssignedTo(e.target.value)}
                    placeholder="e.g. Karthikeya Rao"
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="block font-medium text-slate-700">Description</label>
                  <textarea
                    rows={3}
                    required
                    minLength={5}
                    value={newDescription}
                    onChange={(e) => setNewDescription(e.target.value)}
                    placeholder="Describe equipment symptom and safety impact..."
                    className="mt-1 w-full rounded-lg border border-slate-300 p-3"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => navigate('/maintenance/work-orders')}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isCreatingWorkOrder}
                  className="rounded-lg bg-teal-600 px-5 py-2 font-semibold text-white hover:bg-teal-700"
                >
                  {isCreatingWorkOrder ? 'Submitting...' : 'Submit Work Order'}
                </button>
              </div>
            </form>
          )}

          {/* =================================================================
              MANAGE DOCTORS: ADD OR REMOVE (`/maintenance/doctors`)
          ================================================================= */}
          {currentRoute === '/maintenance/doctors' && (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
              <div className="lg:col-span-5 rounded-xl border border-slate-200 bg-white p-6 space-y-4 text-xs">
                <div className="border-b border-slate-200 pb-3">
                  <div className="flex items-center gap-2 font-semibold text-teal-700">
                    <UserPlus className="h-4 w-4" />
                    <span>Add Specialist to Hospital Roster</span>
                  </div>
                  <p className="mt-1 text-slate-500">
                    Persists doctor via <span className="font-mono">POST /api/v1/doctors</span> and
                    seeds 6 open appointment slots automatically.
                  </p>
                </div>

                <form onSubmit={(e) => void handleAddDoctor(e)} className="space-y-3">
                  <div>
                    <label className="block font-medium text-slate-700">Doctor Full Name</label>
                    <input
                      type="text"
                      required
                      minLength={3}
                      value={docDisplayName}
                      onChange={(e) => setDocDisplayName(e.target.value)}
                      placeholder="e.g. Dr. Kavita Reddy"
                      className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700">Department</label>
                    <select
                      value={docDepartmentName}
                      onChange={(e) => {
                        setDocDepartmentName(e.target.value);
                        setDocSpecialty(e.target.value);
                      }}
                      className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                    >
                      {(hospital?.departments || []).map((d) => (
                        <option key={d.id} value={d.name}>
                          {d.name}
                        </option>
                      ))}
                      {(!hospital || hospital.departments.length === 0) && (
                        <>
                          <option value="Cardiology">Cardiology</option>
                          <option value="Neurology">Neurology</option>
                          <option value="Orthopedics">Orthopedics</option>
                          <option value="Pediatrics">Pediatrics</option>
                          <option value="General Medicine">General Medicine</option>
                        </>
                      )}
                    </select>
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700">Clinical Specialty</label>
                    <input
                      type="text"
                      required
                      value={docSpecialty}
                      onChange={(e) => setDocSpecialty(e.target.value)}
                      placeholder="e.g. Interventional Cardiology"
                      className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={isAddingDoctor}
                    className="w-full rounded-lg bg-teal-600 px-4 py-2.5 font-semibold text-white hover:bg-teal-700 disabled:opacity-50"
                  >
                    {isAddingDoctor ? 'Adding Specialist...' : 'Add Doctor & Seed Slots'}
                  </button>
                </form>
              </div>

              <div className="lg:col-span-7 rounded-xl border border-slate-200 bg-white p-6 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-200 pb-3">
                  <h2 className="font-display text-base font-bold text-slate-900">
                    Active Hospital Doctors ({doctors.length})
                  </h2>
                  <span className="font-mono text-xs text-slate-500">
                    DELETE /api/v1/doctors/&#123;id&#125;
                  </span>
                </div>

                <div className="divide-y divide-slate-200 text-xs">
                  {doctors.map((doc) => (
                    <div
                      key={doc.id}
                      className="py-3.5 flex items-center justify-between gap-4"
                    >
                      <div>
                        <p className="font-display text-sm font-bold text-slate-900">
                          {doc.display_name}
                        </p>
                        <p className="text-slate-600">
                          {doc.specialty} · Department: {doc.department_name || doc.specialty}
                        </p>
                      </div>
                      <button
                        type="button"
                        disabled={removingDoctorId === doc.id}
                        onClick={() => void handleRemoveDoctor(doc.id, doc.display_name)}
                        className="inline-flex items-center gap-1 rounded-lg border border-rose-300 bg-rose-50 px-3 py-1.5 font-semibold text-rose-700 hover:bg-rose-100 disabled:opacity-50 whitespace-nowrap"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        {removingDoctorId === doc.id ? 'Removing...' : 'Remove'}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* =================================================================
              MANAGE INSURANCES: ADD OR REMOVE (`/maintenance/insurance`)
          ================================================================= */}
          {currentRoute === '/maintenance/insurance' && (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
              <div className="lg:col-span-5 rounded-xl border border-slate-200 bg-white p-6 space-y-4 text-xs">
                <div className="border-b border-slate-200 pb-3">
                  <h2 className="font-display text-base font-bold text-slate-900">
                    Add Insurance Provider & Plan
                  </h2>
                  <p className="text-slate-500">
                    Persists via <span className="font-mono">POST /api/v1/insurance/providers</span>{' '}
                    for immediate patient & MediVoice AI search.
                  </p>
                </div>

                <form onSubmit={(e) => void handleAddInsuranceProvider(e)} className="space-y-3">
                  <div>
                    <label className="block font-medium text-slate-700">Provider Name</label>
                    <input
                      type="text"
                      required
                      minLength={3}
                      value={insName}
                      onChange={(e) => setInsName(e.target.value)}
                      placeholder="e.g. NavaBharat Health Assurance"
                      className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block font-medium text-slate-700">Provider Code</label>
                      <input
                        type="text"
                        required
                        value={insCode}
                        onChange={(e) => setInsCode(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono"
                      />
                    </div>
                    <div>
                      <label className="block font-medium text-slate-700">TPA Contact</label>
                      <input
                        type="text"
                        required
                        value={insContact}
                        onChange={(e) => setInsContact(e.target.value)}
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700">Initial Plan Name</label>
                    <input
                      type="text"
                      required
                      minLength={3}
                      value={insPlanName}
                      onChange={(e) => setInsPlanName(e.target.value)}
                      placeholder="e.g. NavaBharat Platinum Cashless Care"
                      className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                    />
                  </div>
                  <div>
                    <label className="block font-medium text-slate-700">Covered Services</label>
                    <input
                      type="text"
                      required
                      value={insCoveredServices}
                      onChange={(e) => setInsCoveredServices(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                    />
                  </div>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={insCashless}
                      onChange={(e) => setInsCashless(e.target.checked)}
                    />
                    <span className="font-medium text-slate-700">Cashless Settlement Enabled</span>
                  </label>

                  <button
                    type="submit"
                    disabled={isAddingInsurance}
                    className="w-full rounded-lg bg-teal-600 px-4 py-2.5 font-semibold text-white hover:bg-teal-700 disabled:opacity-50"
                  >
                    {isAddingInsurance ? 'Adding Provider...' : 'Add Insurance Provider & Plan'}
                  </button>
                </form>
              </div>

              <div className="lg:col-span-7 rounded-xl border border-slate-200 bg-white p-6 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-200 pb-3">
                  <h2 className="font-display text-base font-bold text-slate-900">
                    Active Insurance Providers ({insuranceProviders.length})
                  </h2>
                  <span className="font-mono text-xs text-slate-500">
                    DELETE /api/v1/insurance/providers/&#123;id&#125;
                  </span>
                </div>

                <div className="divide-y divide-slate-200 text-xs">
                  {insuranceProviders.map((prov) => (
                    <div
                      key={prov.id}
                      className="py-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-center"
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-semibold text-teal-700">{prov.code}</span>
                          <span className="font-display text-sm font-bold text-slate-900">
                            {prov.name}
                          </span>
                        </div>
                        <p className="mt-0.5 text-slate-600">
                          Plans ({prov.plans.length}):{' '}
                          {prov.plans.map((p) => p.plan_name).join(', ')}
                        </p>
                      </div>
                      <button
                        type="button"
                        disabled={removingInsuranceId === prov.id}
                        onClick={() => void handleRemoveInsuranceProvider(prov.id, prov.name)}
                        className="inline-flex items-center gap-1 rounded-lg border border-rose-300 bg-rose-50 px-3 py-1.5 font-semibold text-rose-700 hover:bg-rose-100 disabled:opacity-50 whitespace-nowrap shrink-0"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        {removingInsuranceId === prov.id ? 'Removing...' : 'Remove Provider'}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* =================================================================
              CONFLICTS & HUMAN SUPPORT NEEDED TICKETS (`/maintenance/tickets`)
          ================================================================= */}
          {currentRoute === '/maintenance/tickets' && (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
              {/* Left 6 Cols: Operational Conflicts & SLA Escalations */}
              <div className="lg:col-span-6 rounded-xl border border-slate-200 bg-white p-5 space-y-4">
                <div className="border-b border-slate-200 pb-3">
                  <div className="flex items-center gap-2 font-semibold text-amber-700 text-xs">
                    <AlertTriangle className="h-4 w-4" />
                    <span>Operational Conflicts & Overdue SLA Escalations</span>
                  </div>
                  <h2 className="mt-1 font-display text-base font-bold text-slate-900">
                    Workflow Conflicts ({operationalConflicts.length})
                  </h2>
                </div>

                <div className="space-y-3 text-xs">
                  {operationalConflicts.length === 0 ? (
                    <p className="py-6 text-center text-slate-500">
                      No active workflow conflicts or overdue SLA exceptions.
                    </p>
                  ) : (
                    operationalConflicts.map((exc) => (
                      <div
                        key={exc.id}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-2.5"
                      >
                        <div className="flex items-center justify-between font-mono text-[11px]">
                          <span className="font-semibold text-amber-800">
                            {exc.exception_type} · {exc.priority}
                          </span>
                          <span className="font-semibold text-teal-700">{exc.status}</span>
                        </div>
                        <p className="font-bold text-slate-900">{exc.title}</p>
                        <p className="text-slate-600">{exc.description}</p>
                        <p className="font-mono text-[11px] text-slate-500">
                          Assigned: {exc.assigned_to || 'Unassigned'}
                        </p>

                        {exc.status !== 'RESOLVED' && (
                          <div className="space-y-2 pt-2 border-t border-slate-200">
                            <div className="flex gap-2">
                              <input
                                type="text"
                                value={assigneeByException[exc.id] || ''}
                                onChange={(e) =>
                                  setAssigneeByException((prev) => ({
                                    ...prev,
                                    [exc.id]: e.target.value,
                                  }))
                                }
                                placeholder="Assign staff member..."
                                className="flex-1 rounded border border-slate-300 bg-white px-2.5 py-1"
                              />
                              <button
                                type="button"
                                disabled={processingExceptionId === exc.id}
                                onClick={() => void handleAssignException(exc.id)}
                                className="rounded border border-slate-300 bg-white px-3 py-1 font-semibold text-slate-700 hover:bg-slate-100"
                              >
                                Assign
                              </button>
                            </div>
                            <div className="flex gap-2">
                              <input
                                type="text"
                                value={noteByException[exc.id] || ''}
                                onChange={(e) =>
                                  setNoteByException((prev) => ({
                                    ...prev,
                                    [exc.id]: e.target.value,
                                  }))
                                }
                                placeholder="Resolution note..."
                                className="flex-1 rounded border border-slate-300 bg-white px-2.5 py-1"
                              />
                              <button
                                type="button"
                                disabled={processingExceptionId === exc.id}
                                onClick={() => void handleResolveException(exc.id)}
                                className="rounded bg-teal-600 px-3 py-1 font-semibold text-white hover:bg-teal-700"
                              >
                                Resolve Conflict
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Right 6 Cols: Human-Support Needed Insurance Tickets */}
              <div className="lg:col-span-6 rounded-xl border border-slate-200 bg-white p-5 space-y-4">
                <div className="border-b border-slate-200 pb-3">
                  <div className="flex items-center gap-2 font-semibold text-teal-700 text-xs">
                    <LifeBuoy className="h-4 w-4" />
                    <span>Human-Support Needed Escalation Queue</span>
                  </div>
                  <h2 className="mt-1 font-display text-base font-bold text-slate-900">
                    Patient Insurance Support Tickets ({humanSupportExceptionRecords.length})
                  </h2>
                </div>

                <div className="space-y-3 text-xs">
                  {humanSupportExceptionRecords.length === 0 ? (
                    <p className="py-6 text-center text-slate-500">
                      No human-support insurance tickets currently waiting in queue.
                    </p>
                  ) : (
                    humanSupportExceptionRecords.map((ticket) => (
                      <div
                        key={ticket.id}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-2.5"
                      >
                        <div className="flex items-center justify-between font-mono text-[11px]">
                          <span className="font-semibold text-teal-800">
                            Ticket #{ticket.id.slice(0, 8)} · Patient {ticket.affected_record_id}
                          </span>
                          <span className="font-semibold text-slate-800">{ticket.status}</span>
                        </div>
                        <p className="font-bold text-slate-900">{ticket.title}</p>
                        <p className="whitespace-pre-line text-slate-600">{ticket.description}</p>
                        {ticket.resolution_note && (
                          <p className="text-emerald-700 font-medium">
                            Resolution: {ticket.resolution_note}
                          </p>
                        )}

                        {ticket.status !== 'RESOLVED' && (
                          <div className="flex gap-2 pt-2 border-t border-slate-200">
                            <input
                              type="text"
                              value={noteByException[ticket.id] || ''}
                              onChange={(e) =>
                                setNoteByException((prev) => ({
                                  ...prev,
                                  [ticket.id]: e.target.value,
                                }))
                              }
                              placeholder="Enter TPA human verification response..."
                              className="flex-1 rounded border border-slate-300 bg-white px-2.5 py-1.5"
                            />
                            <button
                              type="button"
                              disabled={processingExceptionId === ticket.id}
                              onClick={() => void handleResolveException(ticket.id)}
                              className="rounded bg-teal-600 px-3.5 py-1.5 font-semibold text-white hover:bg-teal-700 whitespace-nowrap"
                            >
                              Resolve Ticket
                            </button>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </StaffAuthGate>
  );
};
