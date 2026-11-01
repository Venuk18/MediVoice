import React, { useMemo, useState } from 'react';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Filter,
  PlusCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  Wrench,
} from 'lucide-react';
import { usePlatform } from '../../context/PlatformContext';
import { StaffAuthGate } from '../../components/ui/StaffAuthGate';
import { ApiError, medivoiceApi } from '../../services/api';
import {
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

export const MaintenanceDashboardView: React.FC = () => {
  const {
    staffProfile,
    maintenanceWorkOrders,
    maintenanceSummary,
    workflowExceptions,
    auditEvents,
    refreshMaintenanceData,
    refreshOperationalData,
  } = usePlatform();

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [priorityFilter, setPriorityFilter] = useState<string>('ALL');
  const [categoryFilter, setCategoryFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedWorkOrderId, setSelectedWorkOrderId] = useState<string | null>(null);

  // Lifecycle Transition Inspector state
  const [targetStatus, setTargetStatus] = useState<MaintenanceStatusType | ''>('');
  const [assignedToInput, setAssignedToInput] = useState<string>('');
  const [resolutionNotesInput, setResolutionNotesInput] = useState<string>('');
  const [isUpdatingWorkOrder, setIsUpdatingWorkOrder] = useState<boolean>(false);

  // Create New Work Order Modal state
  const [showCreateForm, setShowCreateForm] = useState<boolean>(false);
  const [newTitle, setNewTitle] = useState<string>('');
  const [newDescription, setNewDescription] = useState<string>('');
  const [newCategory, setNewCategory] = useState<string>('BIOMEDICAL_EQUIPMENT');
  const [newLocation, setNewLocation] = useState<string>('Block B • Floor 2 • Diagnostic Wing');
  const [newEquipmentRef, setNewEquipmentRef] = useState<string>('BIO-UPS-204');
  const [newPriority, setNewPriority] = useState<MaintenancePriorityType>('HIGH');
  const [newAssignedTo, setNewAssignedTo] = useState<string>('');
  const [isCreatingWorkOrder, setIsCreatingWorkOrder] = useState<boolean>(false);

  // Workflow Exception Resolution state
  const [resolvingExceptionId, setResolvingExceptionId] = useState<string | null>(null);
  const [exceptionResolutionNote, setExceptionResolutionNote] = useState<string>('');

  // Feedback banner
  const [actionBanner, setActionBanner] = useState<{
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
        } ${wo.assigned_to || ''} ${wo.reported_by}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [maintenanceWorkOrders, statusFilter, priorityFilter, categoryFilter, searchQuery]);

  const selectedWorkOrder = useMemo(() => {
    if (!selectedWorkOrderId) return filteredWorkOrders[0] || null;
    return (
      filteredWorkOrders.find((w) => w.id === selectedWorkOrderId) ||
      maintenanceWorkOrders.find((w) => w.id === selectedWorkOrderId) ||
      filteredWorkOrders[0] ||
      null
    );
  }, [filteredWorkOrders, maintenanceWorkOrders, selectedWorkOrderId]);

  const handleSelectWorkOrder = (wo: MaintenanceWorkOrderRead) => {
    setSelectedWorkOrderId(wo.id);
    setTargetStatus(wo.allowed_next_statuses[0] || '');
    setAssignedToInput(wo.assigned_to || staffProfile?.display_name || 'Karthikeya Rao');
    setResolutionNotesInput(wo.resolution_notes || '');
  };

  // Keep inspector synced when selectedWorkOrder changes initially
  React.useEffect(() => {
    if (selectedWorkOrder) {
      setTargetStatus(selectedWorkOrder.allowed_next_statuses[0] || '');
      setAssignedToInput(
        selectedWorkOrder.assigned_to || staffProfile?.display_name || 'Karthikeya Rao'
      );
      setResolutionNotesInput(selectedWorkOrder.resolution_notes || '');
    }
  }, [selectedWorkOrder?.id]);

  const maintenanceAuditEvents = useMemo(() => {
    return auditEvents
      .filter(
        (ev) =>
          ev.entity_type === 'MaintenanceWorkOrder' ||
          ev.entity_type === 'WorkflowException'
      )
      .slice(0, 12);
  }, [auditEvents]);

  const handleTransitionStatus = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedWorkOrder || !targetStatus) return;

    setIsUpdatingWorkOrder(true);
    setActionBanner(null);
    try {
      const updated = await medivoiceApi.updateMaintenanceWorkOrderStatus(
        selectedWorkOrder.id,
        {
          status: targetStatus,
          assigned_to: assignedToInput.trim() || null,
          resolution_notes: resolutionNotesInput.trim() || null,
        }
      );
      setActionBanner({
        type: 'success',
        message: `Work order ${updated.work_order_code} transitioned to ${updated.status}. Audit trail recorded.`,
      });
      await Promise.all([refreshMaintenanceData(), refreshOperationalData()]);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : 'Failed to transition maintenance work order status.';
      setActionBanner({ type: 'error', message: msg });
    } finally {
      setIsUpdatingWorkOrder(false);
    }
  };

  const handleCreateWorkOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim() || !newDescription.trim() || !newLocation.trim()) return;

    setIsCreatingWorkOrder(true);
    setActionBanner(null);
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
      setActionBanner({
        type: 'success',
        message: `Created work order ${created.work_order_code} (${created.title}) with status ${created.status}.`,
      });
      setNewTitle('');
      setNewDescription('');
      setShowCreateForm(false);
      setSelectedWorkOrderId(created.id);
      await Promise.all([refreshMaintenanceData(), refreshOperationalData()]);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Unable to create maintenance work order.';
      setActionBanner({ type: 'error', message: msg });
    } finally {
      setIsCreatingWorkOrder(false);
    }
  };

  const handleResolveWorkflowException = async (exceptionId: string) => {
    const note =
      exceptionResolutionNote.trim() ||
      `Resolved by ${staffProfile?.display_name || 'Hospital Operations'}`;
    setResolvingExceptionId(exceptionId);
    setActionBanner(null);
    try {
      const resolved = await medivoiceApi.resolveWorkflowException(exceptionId, note);
      setActionBanner({
        type: 'success',
        message: `Hospital workflow exception "${resolved.title}" marked RESOLVED.`,
      });
      setExceptionResolutionNote('');
      await refreshOperationalData();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Unable to resolve workflow exception.';
      setActionBanner({ type: 'error', message: msg });
    } finally {
      setResolvingExceptionId(null);
    }
  };

  const getPriorityBadge = (priority: MaintenancePriorityType | string) => {
    switch (priority) {
      case 'CRITICAL':
        return 'border-rose-500/50 bg-rose-500/15 text-rose-300';
      case 'HIGH':
        return 'border-amber-500/50 bg-amber-500/15 text-amber-300';
      case 'MEDIUM':
        return 'border-[#38BDF8]/40 bg-[#38BDF8]/15 text-[#38BDF8]';
      default:
        return 'border-[#334155] bg-[#0B1020] text-[#94A3B8]';
    }
  };

  const getStatusBadge = (status: MaintenanceStatusType | string) => {
    switch (status) {
      case 'RESOLVED':
        return 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300';
      case 'IN_PROGRESS':
        return 'border-[#38BDF8]/40 bg-[#38BDF8]/15 text-[#38BDF8]';
      case 'ASSIGNED':
        return 'border-[#2DD4BF]/40 bg-[#2DD4BF]/15 text-[#2DD4BF]';
      case 'OPEN':
      default:
        return 'border-amber-500/40 bg-amber-500/15 text-amber-300';
    }
  };

  return (
    <StaffAuthGate
      requiredRoles={['MAINTENANCE_STAFF']}
      workspaceTitle="Hospital Staff & Facilities Maintenance Dashboard"
      workspaceSubtitle="Manage biomedical equipment, HVAC, electrical systems, validated work-order lifecycle transitions, and hospital workflow escalations."
    >
      <div className="mx-auto max-w-[1440px] space-y-6 px-4 py-8 sm:px-6 lg:px-8">
        {/* Workspace Header */}
        <div className="flex flex-col justify-between gap-4 rounded-2xl border border-[#334155] bg-[#111B2E] p-6 lg:flex-row lg:items-center">
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="inline-flex items-center gap-1.5 rounded-md border border-[#2DD4BF]/30 bg-[#2DD4BF]/10 px-2.5 py-1 font-mono text-xs font-semibold text-[#2DD4BF]">
                <Wrench className="h-3.5 w-3.5" />
                CLINICAL ENGINEERING & FACILITIES OPS
              </span>
              {staffProfile && (
                <span className="rounded border border-[#334155] bg-[#0B1020] px-2.5 py-1 font-mono text-xs text-[#E5EDF7]">
                  Engineer: {staffProfile.display_name} ({staffProfile.role})
                </span>
              )}
            </div>
            <h1 className="mt-2 font-display text-2xl font-bold text-[#E5EDF7] sm:text-3xl">
              Maintenance Work Orders & Operational Exceptions
            </h1>
            <p className="mt-1 text-sm text-[#94A3B8]">
              Enforces deterministic state transitions (<span className="font-mono">OPEN</span> →{' '}
              <span className="font-mono">ASSIGNED</span> →{' '}
              <span className="font-mono">IN_PROGRESS</span> →{' '}
              <span className="font-mono">RESOLVED</span>) with mandatory assignee and resolution
              verification.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <button
              type="button"
              onClick={() => setShowCreateForm((prev) => !prev)}
              className="inline-flex items-center gap-2 rounded-xl bg-[#2DD4BF] px-4 py-2.5 text-xs font-semibold text-[#0B1020] transition-colors hover:bg-[#2DD4BF]/90"
            >
              <PlusCircle className="h-4 w-4" />
              {showCreateForm ? 'Close Form' : 'Create Work Order'}
            </button>
            <button
              type="button"
              onClick={() => {
                void refreshMaintenanceData();
                void refreshOperationalData();
              }}
              className="inline-flex items-center gap-1.5 rounded-xl border border-[#334155] bg-[#0B1020] px-3.5 py-2.5 text-xs font-medium text-[#E5EDF7] transition-colors hover:border-[#38BDF8]"
            >
              <RefreshCw className="h-3.5 w-3.5 text-[#2DD4BF]" />
              Sync Operations
            </button>
          </div>
        </div>

        {/* Summary KPI Strip */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-4">
            <span className="text-xs font-medium text-[#94A3B8]">Total Work Orders</span>
            <p className="mt-1.5 font-mono text-2xl font-bold tabular-nums text-[#E5EDF7]">
              {maintenanceSummary?.total_work_orders ?? maintenanceWorkOrders.length}
            </p>
          </div>
          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-4">
            <span className="text-xs font-medium text-[#94A3B8]">Open Unassigned</span>
            <p className="mt-1.5 font-mono text-2xl font-bold tabular-nums text-amber-300">
              {maintenanceSummary?.open_count ??
                maintenanceWorkOrders.filter((w) => w.status === 'OPEN').length}
            </p>
          </div>
          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-4">
            <span className="text-xs font-medium text-[#94A3B8]">Assigned</span>
            <p className="mt-1.5 font-mono text-2xl font-bold tabular-nums text-[#2DD4BF]">
              {maintenanceSummary?.assigned_count ??
                maintenanceWorkOrders.filter((w) => w.status === 'ASSIGNED').length}
            </p>
          </div>
          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-4">
            <span className="text-xs font-medium text-[#94A3B8]">In Progress</span>
            <p className="mt-1.5 font-mono text-2xl font-bold tabular-nums text-[#38BDF8]">
              {maintenanceSummary?.in_progress_count ??
                maintenanceWorkOrders.filter((w) => w.status === 'IN_PROGRESS').length}
            </p>
          </div>
          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-4">
            <span className="text-xs font-medium text-[#94A3B8]">Resolved</span>
            <p className="mt-1.5 font-mono text-2xl font-bold tabular-nums text-emerald-400">
              {maintenanceSummary?.resolved_count ??
                maintenanceWorkOrders.filter((w) => w.status === 'RESOLVED').length}
            </p>
          </div>
          <div className="rounded-xl border border-rose-500/30 bg-[#111B2E] p-4">
            <span className="text-xs font-medium text-rose-300">Critical / High Active</span>
            <p className="mt-1.5 font-mono text-2xl font-bold tabular-nums text-rose-400">
              {(maintenanceSummary?.critical_active_count ?? 0) +
                (maintenanceSummary?.high_active_count ?? 0)}
            </p>
          </div>
        </div>

        {/* Create New Maintenance Work Order Form */}
        {showCreateForm && (
          <form
            onSubmit={(e) => void handleCreateWorkOrder(e)}
            className="rounded-2xl border border-[#2DD4BF]/40 bg-[#111B2E] p-6 space-y-4"
          >
            <div className="flex items-center justify-between border-b border-[#334155] pb-3">
              <div>
                <h2 className="font-display text-base font-bold text-[#E5EDF7]">
                  Dispatch New Facilities / Biomedical Work Order
                </h2>
                <p className="text-xs text-[#94A3B8]">
                  Providing an initial assignee automatically initializes the work order in{' '}
                  <span className="font-mono">ASSIGNED</span> status.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <label className="block text-xs font-medium text-[#94A3B8]">Issue Title</label>
                <input
                  type="text"
                  required
                  minLength={3}
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="e.g., ICU Negative Pressure Damper Calibration"
                  className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[#94A3B8]">Category</label>
                <select
                  value={newCategory}
                  onChange={(e) => setNewCategory(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 font-mono text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                >
                  {CATEGORIES.map((cat) => (
                    <option key={cat} value={cat}>
                      {cat}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-[#94A3B8]">Priority</label>
                <select
                  value={newPriority}
                  onChange={(e) => setNewPriority(e.target.value as MaintenancePriorityType)}
                  className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 font-mono text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                >
                  {PRIORITIES.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-[#94A3B8]">
                  Hospital Location
                </label>
                <input
                  type="text"
                  required
                  value={newLocation}
                  onChange={(e) => setNewLocation(e.target.value)}
                  placeholder="Block B • Floor 2 • Wing C"
                  className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[#94A3B8]">
                  Equipment Asset Tag (Optional)
                </label>
                <input
                  type="text"
                  value={newEquipmentRef}
                  onChange={(e) => setNewEquipmentRef(e.target.value)}
                  placeholder="BIO-MRI-CHILL-02"
                  className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 font-mono text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[#94A3B8]">
                  Assign Engineer Immediately (Optional)
                </label>
                <input
                  type="text"
                  value={newAssignedTo}
                  onChange={(e) => setNewAssignedTo(e.target.value)}
                  placeholder="e.g., Karthikeya Rao (Biomedical)"
                  className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                />
              </div>

              <div className="sm:col-span-2 lg:col-span-3">
                <label className="block text-xs font-medium text-[#94A3B8]">
                  Technical Description & Operational Impact
                </label>
                <textarea
                  rows={2}
                  required
                  minLength={5}
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="Describe telemetry fault, clinical impact, and safety precautions required..."
                  className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] p-3 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowCreateForm(false)}
                className="rounded-lg border border-[#334155] bg-[#0B1020] px-4 py-2 text-xs font-medium text-[#94A3B8] hover:text-[#E5EDF7]"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isCreatingWorkOrder}
                className="rounded-lg bg-[#2DD4BF] px-4 py-2 text-xs font-semibold text-[#0B1020] hover:bg-[#2DD4BF]/90 disabled:opacity-50"
              >
                {isCreatingWorkOrder ? 'Creating Work Order...' : 'Create Work Order'}
              </button>
            </div>
          </form>
        )}

        {actionBanner && (
          <div
            className={`flex items-center justify-between rounded-xl border p-4 text-xs ${
              actionBanner.type === 'success'
                ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
                : 'border-rose-500/40 bg-rose-500/10 text-rose-200'
            }`}
          >
            <div className="flex items-center gap-2.5">
              {actionBanner.type === 'success' ? (
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
              ) : (
                <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
              )}
              <span>{actionBanner.message}</span>
            </div>
            <button
              type="button"
              onClick={() => setActionBanner(null)}
              className="font-mono text-[11px] underline opacity-80 hover:opacity-100"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Main 12-Col Split: Work-Order Queue (7 Cols) + Validated Lifecycle Inspector (5 Cols) */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Left: Work Order Queue Table */}
          <div className="lg:col-span-7 flex flex-col rounded-2xl border border-[#334155] bg-[#111B2E]">
            <div className="flex flex-col gap-3 border-b border-[#334155] p-5 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-2">
                <Filter className="h-4 w-4 text-[#2DD4BF]" />
                <h2 className="font-display text-base font-bold text-[#E5EDF7]">
                  Facilities Work Orders ({filteredWorkOrders.length})
                </h2>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <select
                  aria-label="Filter by work order status"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="rounded-lg border border-[#334155] bg-[#0B1020] px-2.5 py-1.5 font-mono text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                >
                  <option value="ALL">All Statuses</option>
                  <option value="OPEN">OPEN</option>
                  <option value="ASSIGNED">ASSIGNED</option>
                  <option value="IN_PROGRESS">IN_PROGRESS</option>
                  <option value="RESOLVED">RESOLVED</option>
                </select>

                <select
                  aria-label="Filter by priority"
                  value={priorityFilter}
                  onChange={(e) => setPriorityFilter(e.target.value)}
                  className="rounded-lg border border-[#334155] bg-[#0B1020] px-2.5 py-1.5 font-mono text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                >
                  <option value="ALL">All Priorities</option>
                  {PRIORITIES.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>

                <select
                  aria-label="Filter by category"
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                  className="rounded-lg border border-[#334155] bg-[#0B1020] px-2.5 py-1.5 font-mono text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                >
                  <option value="ALL">All Categories</option>
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>

                <div className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-2 h-3.5 w-3.5 text-[#94A3B8]" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Code, asset, location..."
                    className="rounded-lg border border-[#334155] bg-[#0B1020] pl-8 pr-3 py-1.5 text-xs text-[#E5EDF7] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none"
                  />
                </div>
              </div>
            </div>

            <div className="divide-y divide-[#334155]/60">
              {filteredWorkOrders.length === 0 ? (
                <div className="py-12 text-center text-xs text-[#94A3B8]">
                  No maintenance work orders match the selected filters.
                </div>
              ) : (
                filteredWorkOrders.map((wo) => {
                  const isSelected = selectedWorkOrder?.id === wo.id;
                  return (
                    <div
                      key={wo.id}
                      onClick={() => handleSelectWorkOrder(wo)}
                      className={`cursor-pointer p-5 transition-colors ${
                        isSelected ? 'bg-[#2DD4BF]/10' : 'hover:bg-[#0B1020]/60'
                      }`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-xs font-bold text-[#2DD4BF]">
                            {wo.work_order_code}
                          </span>
                          <span
                            className={`rounded border px-2 py-0.5 font-mono text-[10px] font-semibold ${getPriorityBadge(
                              wo.priority
                            )}`}
                          >
                            {wo.priority}
                          </span>
                          <span className="rounded border border-[#334155] bg-[#0B1020] px-2 py-0.5 font-mono text-[10px] text-[#94A3B8]">
                            {wo.category}
                          </span>
                        </div>

                        <span
                          className={`rounded border px-2.5 py-0.5 font-mono text-[10px] font-semibold ${getStatusBadge(
                            wo.status
                          )}`}
                        >
                          {wo.status}
                        </span>
                      </div>

                      <h3 className="mt-2 font-display text-sm font-bold text-[#E5EDF7]">
                        {wo.title}
                      </h3>
                      <p className="mt-1 text-xs text-[#94A3B8] line-clamp-2">{wo.description}</p>

                      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 font-mono text-[11px] text-[#94A3B8]">
                        <span>Location: {wo.location}</span>
                        {wo.equipment_reference && (
                          <span className="text-[#38BDF8]">Asset: {wo.equipment_reference}</span>
                        )}
                      </div>

                      <div className="mt-1.5 flex flex-wrap items-center justify-between gap-2 text-[11px] text-[#94A3B8]">
                        <span>
                          Assigned:{' '}
                          <strong className="text-[#E5EDF7]">
                            {wo.assigned_to || 'Unassigned'}
                          </strong>
                        </span>
                        <span className="font-mono">
                          Updated: {new Date(wo.updated_at).toLocaleTimeString([], {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Right: Validated Work-Order Lifecycle Transition Inspector */}
          <div className="lg:col-span-5 space-y-6">
            <div className="rounded-2xl border border-[#334155] bg-[#111B2E] p-5">
              <div className="flex items-center justify-between border-b border-[#334155] pb-3.5">
                <h2 className="font-display text-base font-bold text-[#E5EDF7]">
                  Work-Order Lifecycle Inspector
                </h2>
              </div>

              {!selectedWorkOrder ? (
                <div className="py-10 text-center text-xs text-[#94A3B8]">
                  Select a work order from the queue to inspect details and transition its status.
                </div>
              ) : (
                <div className="mt-4 space-y-4">
                  <div className="rounded-xl border border-[#334155] bg-[#0B1020] p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs font-bold text-[#2DD4BF]">
                        {selectedWorkOrder.work_order_code}
                      </span>
                      <span
                        className={`rounded border px-2 py-0.5 font-mono text-[10px] font-semibold ${getStatusBadge(
                          selectedWorkOrder.status
                        )}`}
                      >
                        Current: {selectedWorkOrder.status}
                      </span>
                    </div>
                    <h3 className="font-display text-sm font-bold text-[#E5EDF7]">
                      {selectedWorkOrder.title}
                    </h3>
                    <p className="text-xs text-[#94A3B8]">{selectedWorkOrder.description}</p>
                    <div className="pt-1 font-mono text-[11px] text-[#94A3B8] space-y-0.5">
                      <div>Location: {selectedWorkOrder.location}</div>
                      {selectedWorkOrder.equipment_reference && (
                        <div>Asset Tag: {selectedWorkOrder.equipment_reference}</div>
                      )}
                      <div>Reported By: {selectedWorkOrder.reported_by}</div>
                    </div>
                    {selectedWorkOrder.resolution_notes && (
                      <div className="mt-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-2.5 text-xs text-emerald-200">
                        <span className="font-semibold">Resolution Notes: </span>
                        {selectedWorkOrder.resolution_notes}
                      </div>
                    )}
                  </div>

                  {selectedWorkOrder.allowed_next_statuses.length === 0 ? (
                    <div className="flex items-center gap-2.5 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-xs text-emerald-200">
                      <ShieldCheck className="h-4 w-4 shrink-0 text-emerald-400" />
                      <span>
                        This work order is in terminal <span className="font-mono">RESOLVED</span>{' '}
                        state. Completed at{' '}
                        {selectedWorkOrder.resolved_at
                          ? new Date(selectedWorkOrder.resolved_at).toLocaleString()
                          : 'recorded timestamp'}
                        .
                      </span>
                    </div>
                  ) : (
                    <form
                      onSubmit={(e) => void handleTransitionStatus(e)}
                      className="space-y-4"
                    >
                      <div>
                        <label className="block text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">
                          Allowed Next Lifecycle Status
                        </label>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {selectedWorkOrder.allowed_next_statuses.map((st) => (
                            <button
                              key={st}
                              type="button"
                              onClick={() => setTargetStatus(st)}
                              className={`rounded-lg border px-3.5 py-2 font-mono text-xs font-semibold transition-colors ${
                                targetStatus === st
                                  ? 'border-[#2DD4BF] bg-[#2DD4BF]/20 text-[#2DD4BF]'
                                  : 'border-[#334155] bg-[#0B1020] text-[#94A3B8] hover:text-[#E5EDF7]'
                              }`}
                            >
                              → {st}
                            </button>
                          ))}
                        </div>
                      </div>

                      <div>
                        <label className="block text-xs font-medium text-[#94A3B8]">
                          Assigned Engineer / Technician{' '}
                          {(targetStatus === 'ASSIGNED' || targetStatus === 'IN_PROGRESS') && (
                            <span className="text-amber-300">(Required)</span>
                          )}
                        </label>
                        <input
                          type="text"
                          required={targetStatus === 'ASSIGNED' || targetStatus === 'IN_PROGRESS'}
                          value={assignedToInput}
                          onChange={(e) => setAssignedToInput(e.target.value)}
                          placeholder="e.g., Karthikeya Rao (Biomedical Lead)"
                          className="mt-1.5 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-medium text-[#94A3B8]">
                          Engineering / Resolution Notes{' '}
                          {targetStatus === 'RESOLVED' && (
                            <span className="text-emerald-300">(Required for RESOLVED)</span>
                          )}
                        </label>
                        <textarea
                          rows={2}
                          required={targetStatus === 'RESOLVED'}
                          value={resolutionNotesInput}
                          onChange={(e) => setResolutionNotesInput(e.target.value)}
                          placeholder="Document root cause, parts replaced, and post-repair safety verification..."
                          className="mt-1.5 w-full rounded-lg border border-[#334155] bg-[#0B1020] p-3 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                        />
                      </div>

                      <button
                        type="submit"
                        disabled={isUpdatingWorkOrder || !targetStatus}
                        className="w-full rounded-xl bg-[#2DD4BF] px-4 py-2.5 text-xs font-semibold text-[#0B1020] transition-colors hover:bg-[#2DD4BF]/90 disabled:opacity-50"
                      >
                        {isUpdatingWorkOrder
                          ? 'Validating & Updating...'
                          : `Transition ${selectedWorkOrder.work_order_code} to ${targetStatus}`}
                      </button>
                    </form>
                  )}
                </div>
              )}
            </div>

            {/* Hospital Workflow Exceptions & Escalations (Overdue Labs + Insurance Tickets) */}
            <div className="rounded-2xl border border-[#334155] bg-[#111B2E] p-5">
              <div className="flex items-center justify-between border-b border-[#334155] pb-3">
                <div className="flex items-center gap-2">
                  <ClipboardList className="h-4 w-4 text-amber-400" />
                  <h3 className="font-display text-sm font-bold text-[#E5EDF7]">
                    Hospital Workflow Exceptions ({workflowExceptions.length})
                  </h3>
                </div>
              </div>

              <div className="mt-3 max-h-64 space-y-2.5 overflow-y-auto pr-1">
                {workflowExceptions.length === 0 ? (
                  <p className="py-4 text-center text-xs text-[#94A3B8]">
                    No active hospital workflow exceptions.
                  </p>
                ) : (
                  workflowExceptions.map((exc) => (
                    <div
                      key={exc.id}
                      className="rounded-xl border border-[#334155] bg-[#0B1020] p-3.5 text-xs space-y-2"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-mono text-[10px] font-semibold text-amber-300">
                          {exc.exception_type} • {exc.priority}
                        </span>
                        <span
                          className={`rounded border px-2 py-0.5 font-mono text-[10px] font-semibold ${getStatusBadge(
                            exc.status
                          )}`}
                        >
                          {exc.status}
                        </span>
                      </div>
                      <p className="font-semibold text-[#E5EDF7]">{exc.title}</p>
                      <p className="text-[11px] text-[#94A3B8]">{exc.description}</p>
                      {exc.status !== 'RESOLVED' && (
                        <div className="flex items-center gap-2 pt-1">
                          <input
                            type="text"
                            value={exceptionResolutionNote}
                            onChange={(e) => setExceptionResolutionNote(e.target.value)}
                            placeholder="Resolution note..."
                            className="flex-1 rounded border border-[#334155] bg-[#111B2E] px-2.5 py-1 text-[11px] text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                          />
                          <button
                            type="button"
                            disabled={resolvingExceptionId === exc.id}
                            onClick={() => void handleResolveWorkflowException(exc.id)}
                            className="rounded bg-[#2DD4BF]/20 border border-[#2DD4BF]/40 px-2.5 py-1 font-mono text-[10px] font-semibold text-[#2DD4BF] hover:bg-[#2DD4BF]/30 disabled:opacity-50"
                          >
                            {resolvingExceptionId === exc.id ? 'Resolving...' : 'Resolve'}
                          </button>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Facilities & Engineering Audit Trail */}
            <div className="rounded-2xl border border-[#334155] bg-[#111B2E] p-5">
              <div className="flex items-center justify-between border-b border-[#334155] pb-3">
                <div className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-[#2DD4BF]" />
                  <h3 className="font-display text-sm font-bold text-[#E5EDF7]">
                    Engineering & Exception Audit Trail
                  </h3>
                </div>
              </div>
              <div className="mt-3 max-h-48 space-y-2 overflow-y-auto pr-1">
                {maintenanceAuditEvents.length === 0 ? (
                  <p className="py-4 text-center text-xs text-[#94A3B8]">
                    No maintenance audit events recorded yet.
                  </p>
                ) : (
                  maintenanceAuditEvents.map((ev) => (
                    <div
                      key={ev.id}
                      className="rounded-lg border border-[#334155]/80 bg-[#0B1020] p-2.5 text-xs"
                    >
                      <div className="flex items-center justify-between font-mono text-[10px]">
                        <span className="font-semibold text-[#2DD4BF]">{ev.action}</span>
                        <span className="text-[#94A3B8]">
                          {new Date(ev.created_at).toLocaleTimeString([], {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                      </div>
                      <p className="mt-1 text-[11px] text-[#E5EDF7]">{ev.details}</p>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </StaffAuthGate>
  );
};
