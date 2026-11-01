import React, { useMemo, useState } from 'react';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  FilePlus2,
  Filter,
  FlaskConical,
  RefreshCw,
  Search,
  ShieldAlert,
} from 'lucide-react';
import { usePlatform } from '../../context/PlatformContext';
import { StaffAuthGate } from '../../components/ui/StaffAuthGate';
import { ApiError, medivoiceApi } from '../../services/api';
import { CanonicalLabStatus, LabOrderRead } from '../../types/api';

const CANONICAL_STATUSES: CanonicalLabStatus[] = [
  'REGISTERED',
  'SAMPLE_COLLECTED',
  'PROCESSING',
  'COMPLETED',
  'CANCELLED',
];

export const LabDashboardView: React.FC = () => {
  const {
    staffProfile,
    hospital,
    labOrders,
    workflowExceptions,
    auditEvents,
    refreshOperationalData,
  } = usePlatform();

  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [departmentFilter, setDepartmentFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);

  // Status transition form state
  const [nextStatus, setNextStatus] = useState<CanonicalLabStatus>('PROCESSING');
  const [delayReasonInput, setDelayReasonInput] = useState<string>('');
  const [isUpdatingStatus, setIsUpdatingStatus] = useState<boolean>(false);

  // New synthetic lab order modal/drawer state
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [newPatientRef, setNewPatientRef] = useState<string>('PAT-2024-9182');
  const [newDepartmentId, setNewDepartmentId] = useState<string>(
    '22222222-2222-2222-2222-222222222221'
  );
  const [newTestName, setNewTestName] = useState<string>('Comprehensive Metabolic Panel (CMP)');
  const [newTestCategory, setNewTestCategory] = useState<string>('Biochemistry');
  const [newAssignedTeam, setNewAssignedTeam] = useState<string>('Central Clinical Lab Team A');
  const [isCreatingOrder, setIsCreatingOrder] = useState<boolean>(false);

  // Overdue exception detection state
  const [isDetectingOverdue, setIsDetectingOverdue] = useState<boolean>(false);

  // Feedback banner
  const [actionBanner, setActionBanner] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

  const nowMs = Date.now();

  const isOrderOverdue = (order: LabOrderRead): boolean => {
    if (order.lab_status === 'COMPLETED' || order.lab_status === 'CANCELLED') {
      return false;
    }
    const expectedMs = new Date(order.expected_completion_at).getTime();
    return !Number.isNaN(expectedMs) && expectedMs < nowMs;
  };

  // Filtered lab orders
  const filteredOrders = useMemo(() => {
    return labOrders.filter((order) => {
      if (statusFilter === 'OVERDUE') {
        if (!isOrderOverdue(order)) return false;
      } else if (statusFilter !== 'ALL' && order.lab_status !== statusFilter) {
        return false;
      }

      if (departmentFilter !== 'ALL' && order.ordering_department_id !== departmentFilter) {
        return false;
      }

      if (searchQuery.trim()) {
        const q = searchQuery.trim().toLowerCase();
        const hay = `${order.patient_reference} ${order.test_name || ''} ${order.test_category} ${
          order.department_name || ''
        } ${order.assigned_team}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }

      return true;
    });
  }, [labOrders, statusFilter, departmentFilter, searchQuery, nowMs]);

  const selectedOrder = useMemo(() => {
    if (!selectedOrderId) return filteredOrders[0] || null;
    return (
      filteredOrders.find((o) => o.id === selectedOrderId) ||
      labOrders.find((o) => o.id === selectedOrderId) ||
      filteredOrders[0] ||
      null
    );
  }, [filteredOrders, labOrders, selectedOrderId]);

  // Queue KPI metrics
  const metrics = useMemo(() => {
    const total = labOrders.length;
    const registered = labOrders.filter((o) => o.lab_status === 'REGISTERED').length;
    const sampleCollected = labOrders.filter((o) => o.lab_status === 'SAMPLE_COLLECTED').length;
    const processing = labOrders.filter((o) => o.lab_status === 'PROCESSING').length;
    const completed = labOrders.filter((o) => o.lab_status === 'COMPLETED').length;
    const overdue = labOrders.filter((o) => isOrderOverdue(o)).length;
    return { total, registered, sampleCollected, processing, completed, overdue };
  }, [labOrders, nowMs]);

  const labAuditEvents = useMemo(() => {
    return auditEvents.filter((ev) => ev.entity_type === 'LabOrder').slice(0, 12);
  }, [auditEvents]);

  const openLabExceptions = useMemo(() => {
    return workflowExceptions.filter(
      (ex) => ex.affected_record_type === 'LabOrder' && ex.status !== 'RESOLVED'
    );
  }, [workflowExceptions]);

  const handleSelectOrder = (order: LabOrderRead) => {
    setSelectedOrderId(order.id);
    setNextStatus(order.lab_status);
    setDelayReasonInput(order.delay_reason || '');
  };

  const handleStatusUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedOrder) return;

    setIsUpdatingStatus(true);
    setActionBanner(null);
    try {
      const updated = await medivoiceApi.updateLabOrderStatus(selectedOrder.id, {
        workflow_status: nextStatus,
        delay_reason: delayReasonInput.trim() || null,
      });
      setActionBanner({
        type: 'success',
        message: `Lab order for ${updated.patient_reference} (${
          updated.test_name || updated.test_category
        }) updated to ${updated.lab_status}. Patient verification portal synchronized.`,
      });
      await refreshOperationalData();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Unable to update lab order status.';
      setActionBanner({ type: 'error', message: msg });
    } finally {
      setIsUpdatingStatus(false);
    }
  };

  const handleCreateLabOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPatientRef.trim() || !newTestName.trim()) return;

    setIsCreatingOrder(true);
    setActionBanner(null);
    try {
      const created = await medivoiceApi.createLabOrder({
        patient_reference: newPatientRef.trim(),
        ordering_department_id: newDepartmentId || null,
        test_name: newTestName.trim(),
        test_category: newTestCategory.trim() || 'Pathology',
        workflow_status: 'REGISTERED',
        assigned_team: newAssignedTeam.trim() || 'Central Diagnostics Lab',
      });
      setActionBanner({
        type: 'success',
        message: `Registered new synthetic lab order (${created.test_name}) for ${created.patient_reference} with a 6-digit verification code.`,
      });
      setShowCreateModal(false);
      setSelectedOrderId(created.id);
      await refreshOperationalData();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Failed to create synthetic lab order.';
      setActionBanner({ type: 'error', message: msg });
    } finally {
      setIsCreatingOrder(false);
    }
  };

  const handleDetectOverdueExceptions = async () => {
    setIsDetectingOverdue(true);
    setActionBanner(null);
    try {
      const detected = await medivoiceApi.triggerOverdueLabDetection();
      setActionBanner({
        type: 'success',
        message:
          detected.length > 0
            ? `Deterministic SLA check escalated ${detected.length} overdue lab order(s) to the Hospital Workflow Exception queue.`
            : 'Turnaround SLA audit finished: All overdue lab orders already have active workflow exception records.',
      });
      await refreshOperationalData();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Unable to run overdue turnaround check.';
      setActionBanner({ type: 'error', message: msg });
    } finally {
      setIsDetectingOverdue(false);
    }
  };

  const getStatusBadgeClasses = (status: CanonicalLabStatus) => {
    switch (status) {
      case 'COMPLETED':
        return 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300';
      case 'PROCESSING':
        return 'border-[#38BDF8]/40 bg-[#38BDF8]/15 text-[#38BDF8]';
      case 'SAMPLE_COLLECTED':
        return 'border-[#2DD4BF]/40 bg-[#2DD4BF]/15 text-[#2DD4BF]';
      case 'REGISTERED':
        return 'border-amber-500/40 bg-amber-500/15 text-amber-300';
      case 'CANCELLED':
        return 'border-rose-500/40 bg-rose-500/15 text-rose-300';
      default:
        return 'border-[#334155] bg-[#0B1020] text-[#94A3B8]';
    }
  };

  return (
    <StaffAuthGate
      requiredRoles={['LAB_OPERATOR']}
      workspaceTitle="Laboratory Operator Dashboard"
      workspaceSubtitle="Manage diagnostic test orders, canonical sample lifecycle stages, turnaround SLAs, and patient verification status."
    >
      <div className="mx-auto max-w-[1440px] space-y-6 px-4 py-8 sm:px-6 lg:px-8">
        {/* Workspace Header */}
        <div className="flex flex-col justify-between gap-4 rounded-2xl border border-[#334155] bg-[#111B2E] p-6 lg:flex-row lg:items-center">
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="inline-flex items-center gap-1.5 rounded-md border border-[#2DD4BF]/30 bg-[#2DD4BF]/10 px-2.5 py-1 font-mono text-xs font-semibold text-[#2DD4BF]">
                <FlaskConical className="h-3.5 w-3.5" />
                DIAGNOSTIC LAB OPERATIONS
              </span>
              {staffProfile && (
                <span className="rounded border border-[#334155] bg-[#0B1020] px-2.5 py-1 font-mono text-xs text-[#E5EDF7]">
                  Operator: {staffProfile.display_name} ({staffProfile.role})
                </span>
              )}
            </div>
            <h1 className="mt-2 font-display text-2xl font-bold text-[#E5EDF7] sm:text-3xl">
              Clinical Pathology & Sample Processing Queue
            </h1>
            <p className="mt-1 text-sm text-[#94A3B8]">
              Every status transition immediately updates the patient&apos;s 6-digit verification
              portal and writes an immutable audit log entry.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <button
              type="button"
              onClick={() => setShowCreateModal((prev) => !prev)}
              className="inline-flex items-center gap-2 rounded-xl bg-[#2DD4BF] px-4 py-2.5 text-xs font-semibold text-[#0B1020] transition-colors hover:bg-[#2DD4BF]/90"
            >
              <FilePlus2 className="h-4 w-4" />
              {showCreateModal ? 'Close Order Form' : 'New Synthetic Lab Order'}
            </button>
            <button
              type="button"
              onClick={() => void refreshOperationalData()}
              className="inline-flex items-center gap-1.5 rounded-xl border border-[#334155] bg-[#0B1020] px-3.5 py-2.5 text-xs font-medium text-[#E5EDF7] transition-colors hover:border-[#38BDF8]"
            >
              <RefreshCw className="h-3.5 w-3.5 text-[#2DD4BF]" />
              Refresh Queue
            </button>
          </div>
        </div>

        {/* Overdue Turnaround Alert Banner */}
        {metrics.overdue > 0 && (
          <div className="flex flex-col justify-between gap-4 rounded-2xl border border-amber-500/40 bg-amber-500/10 p-5 sm:flex-row sm:items-center">
            <div className="flex items-start gap-3.5">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" />
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-display text-sm font-bold text-amber-200">
                    Turnaround SLA Breach Detected ({metrics.overdue} Overdue Order
                    {metrics.overdue === 1 ? '' : 's'})
                  </span>
                  <span className="rounded border border-amber-400/30 bg-amber-500/20 px-2 py-0.5 font-mono text-[10px] font-semibold text-amber-200">
                    Active Exceptions: {openLabExceptions.length}
                  </span>
                </div>
                <p className="mt-1 text-xs text-amber-100/85">
                  One or more diagnostic samples have exceeded their expected completion timestamp
                  without reaching <span className="font-mono">COMPLETED</span>. Run deterministic
                  SLA detection to escalate overdue orders to hospital workflow exceptions.
                </p>
              </div>
            </div>

            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={() => setStatusFilter(statusFilter === 'OVERDUE' ? 'ALL' : 'OVERDUE')}
                className="rounded-lg border border-amber-400/40 bg-[#0B1020]/70 px-3 py-2 text-xs font-semibold text-amber-200 transition-colors hover:bg-[#0B1020]"
              >
                {statusFilter === 'OVERDUE' ? 'Show All Orders' : 'Filter Overdue Only'}
              </button>
              <button
                type="button"
                disabled={isDetectingOverdue}
                onClick={() => void handleDetectOverdueExceptions()}
                className="inline-flex items-center gap-1.5 rounded-lg bg-amber-400 px-3.5 py-2 text-xs font-semibold text-[#0B1020] transition-colors hover:bg-amber-300 disabled:opacity-50"
              >
                <ShieldAlert className="h-4 w-4" />
                {isDetectingOverdue ? 'Scanning SLA...' : 'Escalate Overdue to Exceptions'}
              </button>
            </div>
          </div>
        )}

        {/* New Synthetic Lab Order Collapsible Form */}
        {showCreateModal && (
          <form
            onSubmit={(e) => void handleCreateLabOrder(e)}
            className="rounded-2xl border border-[#2DD4BF]/40 bg-[#111B2E] p-6 space-y-4"
          >
            <div className="flex items-center justify-between border-b border-[#334155] pb-3">
              <div>
                <h2 className="font-display text-base font-bold text-[#E5EDF7]">
                  Register New Synthetic Lab Order
                </h2>
                <p className="text-xs text-[#94A3B8]">
                  Automatically generates a unique 6-digit verification code for patient status
                  lookup.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <div>
                <label className="block text-xs font-medium text-[#94A3B8]">
                  Patient Reference
                </label>
                <input
                  type="text"
                  required
                  value={newPatientRef}
                  onChange={(e) => setNewPatientRef(e.target.value)}
                  placeholder="PAT-2024-9182"
                  className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 font-mono text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[#94A3B8]">Test Name</label>
                <input
                  type="text"
                  required
                  value={newTestName}
                  onChange={(e) => setNewTestName(e.target.value)}
                  placeholder="e.g., Lipid Profile, HbA1c"
                  className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[#94A3B8]">Test Category</label>
                <input
                  type="text"
                  required
                  value={newTestCategory}
                  onChange={(e) => setNewTestCategory(e.target.value)}
                  placeholder="Biochemistry / Hematology"
                  className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[#94A3B8]">
                  Ordering Department
                </label>
                <select
                  value={newDepartmentId}
                  onChange={(e) => setNewDepartmentId(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                >
                  {(hospital?.departments || []).map((dept) => (
                    <option key={dept.id} value={dept.id}>
                      {dept.name}
                    </option>
                  ))}
                  {(!hospital || hospital.departments.length === 0) && (
                    <option value="22222222-2222-2222-2222-222222222221">Cardiology</option>
                  )}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-[#94A3B8]">Assigned Team</label>
                <input
                  type="text"
                  value={newAssignedTeam}
                  onChange={(e) => setNewAssignedTeam(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="rounded-lg border border-[#334155] bg-[#0B1020] px-4 py-2 text-xs font-medium text-[#94A3B8] hover:text-[#E5EDF7]"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isCreatingOrder}
                className="rounded-lg bg-[#2DD4BF] px-4 py-2 text-xs font-semibold text-[#0B1020] hover:bg-[#2DD4BF]/90 disabled:opacity-50"
              >
                {isCreatingOrder ? 'Registering Order...' : 'Register Diagnostic Order'}
              </button>
            </div>
          </form>
        )}

        {/* Queue KPI Strip */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-4">
            <span className="text-xs font-medium text-[#94A3B8]">Total Lab Orders</span>
            <p className="mt-1.5 font-mono text-2xl font-bold tabular-nums text-[#E5EDF7]">
              {metrics.total}
            </p>
          </div>
          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-4">
            <span className="text-xs font-medium text-[#94A3B8]">Registered</span>
            <p className="mt-1.5 font-mono text-2xl font-bold tabular-nums text-amber-300">
              {metrics.registered}
            </p>
          </div>
          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-4">
            <span className="text-xs font-medium text-[#94A3B8]">Sample Collected</span>
            <p className="mt-1.5 font-mono text-2xl font-bold tabular-nums text-[#2DD4BF]">
              {metrics.sampleCollected}
            </p>
          </div>
          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-4">
            <span className="text-xs font-medium text-[#94A3B8]">Processing</span>
            <p className="mt-1.5 font-mono text-2xl font-bold tabular-nums text-[#38BDF8]">
              {metrics.processing}
            </p>
          </div>
          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-4">
            <span className="text-xs font-medium text-[#94A3B8]">Completed Ready</span>
            <p className="mt-1.5 font-mono text-2xl font-bold tabular-nums text-emerald-400">
              {metrics.completed}
            </p>
          </div>
          <div className="rounded-xl border border-amber-500/30 bg-[#111B2E] p-4">
            <span className="text-xs font-medium text-amber-300">Overdue SLA</span>
            <p className="mt-1.5 font-mono text-2xl font-bold tabular-nums text-amber-400">
              {metrics.overdue}
            </p>
          </div>
        </div>

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

        {/* Main 12-Column Split: Lab Queue Table (7 Cols) + Inspector & Audit (5 Cols) */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Left: High-Density Lab Order Queue */}
          <div className="lg:col-span-7 flex flex-col rounded-2xl border border-[#334155] bg-[#111B2E]">
            <div className="flex flex-col gap-3 border-b border-[#334155] p-5 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-2">
                <Filter className="h-4 w-4 text-[#2DD4BF]" />
                <h2 className="font-display text-base font-bold text-[#E5EDF7]">
                  Diagnostic Order Queue ({filteredOrders.length})
                </h2>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <select
                  aria-label="Filter lab orders by status"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="rounded-lg border border-[#334155] bg-[#0B1020] px-2.5 py-1.5 font-mono text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                >
                  <option value="ALL">All Statuses</option>
                  <option value="REGISTERED">REGISTERED</option>
                  <option value="SAMPLE_COLLECTED">SAMPLE_COLLECTED</option>
                  <option value="PROCESSING">PROCESSING</option>
                  <option value="COMPLETED">COMPLETED</option>
                  <option value="CANCELLED">CANCELLED</option>
                  <option value="OVERDUE">OVERDUE SLA ONLY</option>
                </select>

                <select
                  aria-label="Filter lab orders by department"
                  value={departmentFilter}
                  onChange={(e) => setDepartmentFilter(e.target.value)}
                  className="rounded-lg border border-[#334155] bg-[#0B1020] px-2.5 py-1.5 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                >
                  <option value="ALL">All Departments</option>
                  {(hospital?.departments || []).map((dept) => (
                    <option key={dept.id} value={dept.id}>
                      {dept.name}
                    </option>
                  ))}
                </select>

                <div className="relative">
                  <Search className="pointer-events-none absolute left-2.5 top-2 h-3.5 w-3.5 text-[#94A3B8]" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Patient ref or test..."
                    className=" rounded-lg border border-[#334155] bg-[#0B1020] pl-8 pr-3 py-1.5 text-xs text-[#E5EDF7] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none"
                  />
                </div>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-[#334155] bg-[#0B1020]/60 font-mono text-[11px] uppercase tracking-wider text-[#94A3B8]">
                    <th className="py-3 pl-5 pr-3">Patient & Order</th>
                    <th className="px-3 py-3">Test / Department</th>
                    <th className="px-3 py-3">Turnaround SLA</th>
                    <th className="py-3 pl-3 pr-5">Canonical Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#334155]/60 text-xs">
                  {filteredOrders.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="py-10 text-center text-[#94A3B8]">
                        No diagnostic lab orders match the current filter criteria.
                      </td>
                    </tr>
                  ) : (
                    filteredOrders.map((order) => {
                      const isSelected = selectedOrder?.id === order.id;
                      const overdue = isOrderOverdue(order);
                      return (
                        <tr
                          key={order.id}
                          onClick={() => handleSelectOrder(order)}
                          className={`cursor-pointer transition-colors ${
                            isSelected
                              ? 'bg-[#2DD4BF]/10'
                              : 'hover:bg-[#0B1020]/60'
                          }`}
                        >
                          <td className="py-3.5 pl-5 pr-3 align-top">
                            <div className="font-mono font-semibold text-[#E5EDF7]">
                              {order.patient_reference}
                            </div>
                            <div className="mt-0.5 font-mono text-[10px] text-[#94A3B8]">
                              ID: {order.id.slice(0, 8)}
                            </div>
                          </td>

                          <td className="px-3 py-3.5 align-top">
                            <div className="font-medium text-[#E5EDF7]">
                              {order.test_name || order.test_category}
                            </div>
                            <div className="mt-0.5 text-[11px] text-[#94A3B8]">
                              {order.department_name || order.test_category} • {order.assigned_team}
                            </div>
                            {order.delay_reason && (
                              <div className="mt-1 inline-block rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-300">
                                Note: {order.delay_reason}
                              </div>
                            )}
                          </td>

                          <td className="px-3 py-3.5 align-top font-mono text-[11px] tabular-nums">
                            <div className="text-[#E5EDF7]">
                              {new Date(order.expected_completion_at).toLocaleString([], {
                                month: 'short',
                                day: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </div>
                            {overdue ? (
                              <span className="mt-1 inline-flex items-center gap-1 rounded border border-amber-500/40 bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300">
                                <Clock className="h-3 w-3" />
                                OVERDUE SLA
                              </span>
                            ) : (
                              <span className="text-[10px] text-[#94A3B8]">On Schedule</span>
                            )}
                          </td>

                          <td className="py-3.5 pl-3 pr-5 align-top">
                            <span
                              className={`inline-block rounded border px-2 py-0.5 font-mono text-[10px] font-semibold ${getStatusBadgeClasses(
                                order.lab_status
                              )}`}
                            >
                              {order.lab_status}
                            </span>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Right: Order Status Transition Inspector & Audit Trail */}
          <div className="lg:col-span-5 space-y-6">
            <div className="rounded-2xl border border-[#334155] bg-[#111B2E] p-5">
              <div className="flex items-center justify-between border-b border-[#334155] pb-3.5">
                <h2 className="font-display text-base font-bold text-[#E5EDF7]">
                  Sample Lifecycle Transition
                </h2>
              </div>

              {!selectedOrder ? (
                <div className="py-10 text-center text-xs text-[#94A3B8]">
                  Select a lab order from the queue to update its sample processing stage.
                </div>
              ) : (
                <form
                  onSubmit={(e) => void handleStatusUpdate(e)}
                  className="mt-4 space-y-4"
                >
                  <div className="rounded-xl border border-[#334155] bg-[#0B1020] p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs font-bold text-[#2DD4BF]">
                        {selectedOrder.patient_reference}
                      </span>
                      <span
                        className={`rounded border px-2 py-0.5 font-mono text-[10px] font-semibold ${getStatusBadgeClasses(
                          selectedOrder.lab_status
                        )}`}
                      >
                        Current: {selectedOrder.lab_status}
                      </span>
                    </div>
                    <p className="font-display text-sm font-bold text-[#E5EDF7]">
                      {selectedOrder.test_name || selectedOrder.test_category}
                    </p>
                    <p className="text-xs text-[#94A3B8]">
                      Category: {selectedOrder.test_category} • Team: {selectedOrder.assigned_team}
                    </p>
                    <p className="font-mono text-[11px] text-[#94A3B8]">
                      Updated: {new Date(selectedOrder.updated_at).toLocaleString()}
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">
                      Select Target Canonical Stage
                    </label>
                    <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
                      {CANONICAL_STATUSES.map((st) => (
                        <button
                          key={st}
                          type="button"
                          onClick={() => setNextStatus(st)}
                          className={`rounded-lg border px-2.5 py-2 font-mono text-[11px] font-semibold transition-colors ${
                            nextStatus === st
                              ? 'border-[#2DD4BF] bg-[#2DD4BF]/20 text-[#2DD4BF]'
                              : 'border-[#334155] bg-[#0B1020] text-[#94A3B8] hover:text-[#E5EDF7]'
                          }`}
                        >
                          {st}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label
                      htmlFor="lab-delay-reason"
                      className="block text-xs font-medium text-[#94A3B8]"
                    >
                      Processing Note / Delay Reason (Optional)
                    </label>
                    <input
                      id="lab-delay-reason"
                      type="text"
                      value={delayReasonInput}
                      onChange={(e) => setDelayReasonInput(e.target.value)}
                      placeholder="e.g., Recalibrating analyzer, hemolyzed sample re-run..."
                      className="mt-1.5 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#E5EDF7] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={isUpdatingStatus}
                    className="w-full rounded-xl bg-[#2DD4BF] px-4 py-2.5 text-xs font-semibold text-[#0B1020] transition-colors hover:bg-[#2DD4BF]/90 disabled:opacity-50"
                  >
                    {isUpdatingStatus
                      ? 'Persisting Status Transition...'
                      : `Commit Transition to ${nextStatus}`}
                  </button>
                </form>
              )}
            </div>

            {/* Laboratory Audit Trail */}
            <div className="rounded-2xl border border-[#334155] bg-[#111B2E] p-5">
              <div className="flex items-center justify-between border-b border-[#334155] pb-3">
                <div className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-[#38BDF8]" />
                  <h3 className="font-display text-sm font-bold text-[#E5EDF7]">
                    Laboratory Audit Trail
                  </h3>
                </div>
                <span className="font-mono text-[11px] text-[#94A3B8]">
                  Entity: LabOrder
                </span>
              </div>

              <div className="mt-3 max-h-60 space-y-2.5 overflow-y-auto pr-1">
                {labAuditEvents.length === 0 ? (
                  <p className="py-4 text-center text-xs text-[#94A3B8]">
                    No recent laboratory audit events recorded.
                  </p>
                ) : (
                  labAuditEvents.map((ev) => (
                    <div
                      key={ev.id}
                      className="rounded-lg border border-[#334155]/80 bg-[#0B1020] p-3 text-xs"
                    >
                      <div className="flex items-center justify-between font-mono text-[10px]">
                        <span className="font-semibold text-[#2DD4BF]">{ev.action}</span>
                        <span className="text-[#94A3B8]">
                          {new Date(ev.created_at).toLocaleTimeString([], {
                            hour: '2-digit',
                            minute: '2-digit',
                            second: '2-digit',
                          })}
                        </span>
                      </div>
                      <p className="mt-1 text-[#E5EDF7]">{ev.details}</p>
                      <p className="mt-1 font-mono text-[10px] text-[#94A3B8]">
                        Actor: {ev.actor_reference}
                      </p>
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
