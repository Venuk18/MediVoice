import React, { useMemo, useState } from 'react';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardList,
  Clock,
  FilePlus2,
  FlaskConical,
  LayoutDashboard,
  LogOut,
  RefreshCw,
  Search,
  ShieldAlert,
} from 'lucide-react';
import { usePlatform } from '../../app/PlatformContext';
import { StaffAuthGate } from '../../components/StaffAuthGate';
import { ApiError, medivoiceApi } from '../../services/api';
import { AppRoutePath, CanonicalLabStatus, LabOrderRead } from '../../types/api';

const CANONICAL_STATUSES: CanonicalLabStatus[] = [
  'REGISTERED',
  'SAMPLE_COLLECTED',
  'PROCESSING',
  'COMPLETED',
  'CANCELLED',
];

const LAB_SIDEBAR_ITEMS: Array<{
  label: string;
  route: AppRoutePath;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  { label: 'Lab Overview', route: '/lab', icon: LayoutDashboard },
  { label: 'Lab Order Queue & Detail', route: '/lab/orders', icon: ClipboardList },
];

export const LaboratoryWorkspaceView: React.FC = () => {
  const {
    currentRoute,
    navigate,
    staffProfile,
    logoutStaff,
    hospital,
    labOrders,
    workflowExceptions,
    auditEvents,
    refreshOperationalData,
  } = usePlatform();

  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null);

  // Order status transition state
  const [nextStatus, setNextStatus] = useState<CanonicalLabStatus>('PROCESSING');
  const [delayReasonInput, setDelayReasonInput] = useState<string>('');
  const [showTransitionConfirm, setShowTransitionConfirm] = useState<boolean>(false);
  const [isUpdatingStatus, setIsUpdatingStatus] = useState<boolean>(false);

  // Create new lab order modal state
  const [showCreateOrder, setShowCreateOrder] = useState<boolean>(false);
  const [newPatientRef, setNewPatientRef] = useState<string>('PAT-2024-9182');
  const [newDepartmentId, setNewDepartmentId] = useState<string>(
    '22222222-2222-2222-2222-222222222221'
  );
  const [newTestName, setNewTestName] = useState<string>('Comprehensive Metabolic Panel (CMP)');
  const [newTestCategory, setNewTestCategory] = useState<string>('Biochemistry');
  const [newAssignedTeam, setNewAssignedTeam] = useState<string>('Central Clinical Lab Team A');
  const [isCreatingOrder, setIsCreatingOrder] = useState<boolean>(false);

  const [isDetectingOverdue, setIsDetectingOverdue] = useState<boolean>(false);
  const [banner, setBanner] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

  const nowMs = Date.now();
  const isOrderOverdue = (order: LabOrderRead): boolean => {
    if (order.lab_status === 'COMPLETED' || order.lab_status === 'CANCELLED') return false;
    const expectedMs = new Date(order.expected_completion_at).getTime();
    return !Number.isNaN(expectedMs) && expectedMs < nowMs;
  };

  const filteredOrders = useMemo(() => {
    return labOrders.filter((order) => {
      if (statusFilter === 'OVERDUE') {
        if (!isOrderOverdue(order)) return false;
      } else if (statusFilter !== 'ALL' && order.lab_status !== statusFilter) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.trim().toLowerCase();
        const hay = `${order.patient_reference} ${order.test_name || ''} ${order.test_category} ${
          order.department_name || ''
        }`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [labOrders, statusFilter, searchQuery, nowMs]);

  const selectedOrder = useMemo(() => {
    if (!selectedOrderId) return filteredOrders[0] || null;
    return (
      filteredOrders.find((o) => o.id === selectedOrderId) ||
      labOrders.find((o) => o.id === selectedOrderId) ||
      filteredOrders[0] ||
      null
    );
  }, [filteredOrders, labOrders, selectedOrderId]);

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
    return auditEvents.filter((ev) => ev.entity_type === 'LabOrder').slice(0, 10);
  }, [auditEvents]);

  const openLabExceptions = useMemo(() => {
    return workflowExceptions.filter(
      (ex) => ex.affected_record_type === 'LabOrder' && ex.status !== 'RESOLVED'
    );
  }, [workflowExceptions]);

  const handleCommitStatusUpdate = async () => {
    if (!selectedOrder) return;
    setIsUpdatingStatus(true);
    setBanner(null);
    try {
      const updated = await medivoiceApi.updateLabOrderStatus(selectedOrder.id, {
        workflow_status: nextStatus,
        delay_reason: delayReasonInput.trim() || null,
      });
      setBanner({
        type: 'success',
        message: `Lab order ${updated.id.slice(0, 8)} (${updated.patient_reference}) transitioned to ${updated.lab_status}. Patients can check status with the code on their receipt.`,
      });
      setShowTransitionConfirm(false);
      await refreshOperationalData();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Unable to update lab order status.';
      setBanner({ type: 'error', message: msg });
    } finally {
      setIsUpdatingStatus(false);
    }
  };

  const handleCreateLabOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPatientRef.trim() || !newTestName.trim()) return;
    setIsCreatingOrder(true);
    setBanner(null);
    try {
      const created = await medivoiceApi.createLabOrder({
        patient_reference: newPatientRef.trim(),
        ordering_department_id: newDepartmentId || null,
        test_name: newTestName.trim(),
        test_category: newTestCategory.trim() || 'Pathology',
        workflow_status: 'REGISTERED',
        assigned_team: newAssignedTeam.trim() || 'Central Diagnostics Lab',
      });
      setBanner({
        type: 'success',
        message: `Registered synthetic lab order "${created.test_name}" for ${created.patient_reference} with a 6-digit verification code.`,
      });
      setShowCreateOrder(false);
      setSelectedOrderId(created.id);
      await refreshOperationalData();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Failed to create synthetic lab order.';
      setBanner({ type: 'error', message: msg });
    } finally {
      setIsCreatingOrder(false);
    }
  };

  const handleDetectOverdue = async () => {
    setIsDetectingOverdue(true);
    setBanner(null);
    try {
      const detected = await medivoiceApi.triggerOverdueLabDetection();
      setBanner({
        type: 'success',
        message:
          detected.length > 0
            ? `Escalated ${detected.length} overdue lab order(s) to the Hospital Workflow Exception queue.`
            : 'SLA check complete: All overdue lab orders are already tracked in workflow exceptions.',
      });
      await refreshOperationalData();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : 'Unable to run overdue SLA detection.';
      setBanner({ type: 'error', message: msg });
    } finally {
      setIsDetectingOverdue(false);
    }
  };

  return (
    <StaffAuthGate
      requiredRoles={['LAB_OPERATOR']}
      workspaceTitle="Laboratory Operator Workspace"
      workspaceSubtitle="Manage diagnostic sample queues, canonical processing transitions, turnaround SLA alerts, and patient verification state."
    >
      <div className="staff-workspace min-h-screen text-[#17233B] flex flex-col lg:flex-row">
        {/* Left Role-Specific Sidebar */}
        <aside className="staff-sidebar w-full lg:w-64 shrink-0 border-b lg:border-b-0 lg:border-r flex flex-col justify-between p-5">
          <div className="space-y-6">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold text-blue-700">
                <FlaskConical className="h-4 w-4" />
                <span>Laboratory Workspace</span>
              </div>
              <h2 className="mt-1 font-display text-lg font-bold text-slate-900">
                Aarogya One Hospital
              </h2>
              <p className="text-xs text-slate-500">
                {staffProfile?.display_name} · Clinical Pathology
              </p>
            </div>

            <nav aria-label="Laboratory Workspace Navigation" className="space-y-1">
              {LAB_SIDEBAR_ITEMS.map((item) => {
                const Icon = item.icon;
                const isActive = currentRoute === item.route;
                return (
                  <button
                    key={item.route}
                    type="button"
                    onClick={() => navigate(item.route)}
                    className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors whitespace-nowrap ${
                      isActive
                        ? 'bg-gradient-to-r from-blue-600 to-violet-600 text-white font-semibold shadow-md shadow-blue-100'
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
                <span>Laboratory Workspace</span>
                <span aria-hidden="true">/</span>
                <span className="font-semibold text-slate-800">
                  {currentRoute === '/lab/orders' ? 'Order Queue & Transitions' : 'Overview'}
                </span>
              </div>
              <h1 className="mt-1 font-display text-2xl font-bold text-slate-900">
                Diagnostic Order Queue & Sample Lifecycle
              </h1>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setShowCreateOrder((prev) => !prev)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-teal-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-teal-700 whitespace-nowrap"
              >
                <FilePlus2 className="h-3.5 w-3.5" />
                <span>{showCreateOrder ? 'Close Form' : 'New Lab Order'}</span>
              </button>
              <button
                type="button"
                onClick={() => void refreshOperationalData()}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 whitespace-nowrap"
              >
                <RefreshCw className="h-3.5 w-3.5 text-teal-600" />
                <span>Sync Queue</span>
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

          {/* Overdue Turnaround Alert Banner */}
          {metrics.overdue > 0 && (
            <div className="flex flex-col justify-between gap-4 rounded-xl border border-amber-300 bg-amber-50 p-4 sm:flex-row sm:items-center">
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-5 w-5 shrink-0 text-amber-600 mt-0.5" />
                <div className="text-xs">
                  <p className="font-semibold text-amber-900">
                    {metrics.overdue} Order(s) Requiring Attention (Turnaround SLA Exceeded · Active
                    Exceptions: {openLabExceptions.length})
                  </p>
                  <p className="mt-0.5 text-amber-800">
                    Escalate overdue diagnostic orders to the Maintenance & Operations Conflict
                    Queue for supervisor resolution.
                  </p>
                </div>
              </div>
              <button
                type="button"
                disabled={isDetectingOverdue}
                onClick={() => void handleDetectOverdue()}
                className="inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-amber-700 disabled:opacity-50 whitespace-nowrap shrink-0"
              >
                <ShieldAlert className="h-4 w-4" />
                {isDetectingOverdue ? 'Scanning SLA...' : 'Escalate Overdue to Conflicts'}
              </button>
            </div>
          )}

          {/* Create Synthetic Lab Order Form */}
          {showCreateOrder && (
            <form
              onSubmit={(e) => void handleCreateLabOrder(e)}
              className="rounded-xl border border-teal-300 bg-white p-5 space-y-4 text-xs"
            >
              <div className="flex items-center justify-between border-b border-slate-200 pb-3">
                <h2 className="font-display text-sm font-bold text-slate-900">
                  Register New Synthetic Lab Order (Auto-Generates 6-Digit Verification Code)
                </h2>
                Patients can check the status using the code on their receipt.
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div>
                  <label className="block font-medium text-slate-700">Patient Reference</label>
                  <input
                    type="text"
                    required
                    value={newPatientRef}
                    onChange={(e) => setNewPatientRef(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5 font-mono"
                  />
                </div>
                <div>
                  <label className="block font-medium text-slate-700">Test Name</label>
                  <input
                    type="text"
                    required
                    value={newTestName}
                    onChange={(e) => setNewTestName(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5"
                  />
                </div>
                <div>
                  <label className="block font-medium text-slate-700">Category</label>
                  <input
                    type="text"
                    required
                    value={newTestCategory}
                    onChange={(e) => setNewTestCategory(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5"
                  />
                </div>
                <div>
                  <label className="block font-medium text-slate-700">Assigned Team</label>
                  <input
                    type="text"
                    value={newAssignedTeam}
                    onChange={(e) => setNewAssignedTeam(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-1.5"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowCreateOrder(false)}
                  className="rounded-lg border border-slate-300 px-3 py-1.5 text-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isCreatingOrder}
                  className="rounded-lg bg-teal-600 px-4 py-1.5 font-semibold text-white hover:bg-teal-700"
                >
                  {isCreatingOrder ? 'Registering...' : 'Register Order'}
                </button>
              </div>
            </form>
          )}

          {/* KPI Strip */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <span className="text-xs text-slate-500">Total Orders</span>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-slate-900">
                {metrics.total}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <span className="text-xs text-slate-500">Registered</span>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-amber-700">
                {metrics.registered}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <span className="text-xs text-slate-500">Sample Collected</span>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-teal-700">
                {metrics.sampleCollected}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <span className="text-xs text-slate-500">Processing</span>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-sky-700">
                {metrics.processing}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <span className="text-xs text-slate-500">Completed</span>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-emerald-700">
                {metrics.completed}
              </p>
            </div>
            <div className="rounded-xl border border-amber-200 bg-white p-4">
              <span className="text-xs text-amber-800">Overdue Attention</span>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-amber-700">
                {metrics.overdue}
              </p>
            </div>
          </div>

          {/* Main 12-Col Split: Lab Queue Table (7 Cols) + Order Detail & Transition Inspector (5 Cols) */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
            <div className="lg:col-span-7 rounded-xl border border-slate-200 bg-white overflow-hidden">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 p-4">
                <h2 className="font-display text-sm font-bold text-slate-900">
                  Lab Order Queue ({filteredOrders.length})
                </h2>
                <div className="flex items-center gap-2">
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-400" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Patient or test..."
                      className="rounded-lg border border-slate-200 bg-slate-50 pl-8 pr-2.5 py-1 text-xs text-slate-900"
                    />
                  </div>
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    aria-label="Filter lab orders by status"
                    className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 font-mono text-xs text-slate-700"
                  >
                    <option value="ALL">All Statuses</option>
                    {CANONICAL_STATUSES.map((st) => (
                      <option key={st} value={st}>
                        {st}
                      </option>
                    ))}
                    <option value="OVERDUE">OVERDUE ONLY</option>
                  </select>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold text-slate-500">
                      <th className="py-2.5 pl-4 pr-2">Order & Patient</th>
                      <th className="px-2 py-2.5">Test / Category</th>
                      <th className="px-2 py-2.5">Expected SLA</th>
                      <th className="py-2.5 pl-2 pr-4">Current Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 text-xs">
                    {filteredOrders.map((order) => {
                      const isSelected = selectedOrder?.id === order.id;
                      const overdue = isOrderOverdue(order);
                      return (
                        <tr
                          key={order.id}
                          onClick={() => {
                            setSelectedOrderId(order.id);
                            setNextStatus(order.lab_status);
                            setDelayReasonInput(order.delay_reason || '');
                            setShowTransitionConfirm(false);
                          }}
                          className={`cursor-pointer transition-colors ${
                            isSelected ? 'bg-teal-50/80' : 'hover:bg-slate-50'
                          }`}
                        >
                          <td className="py-3 pl-4 pr-2 align-top">
                            <div className="font-mono font-semibold text-slate-900">
                              {order.patient_reference}
                            </div>
                            <div className="font-mono text-[10px] text-slate-500">
                              #{order.id.slice(0, 8)}
                            </div>
                          </td>
                          <td className="px-2 py-3 align-top">
                            <div className="font-medium text-slate-900">
                              {order.test_name || order.test_category}
                            </div>
                            <div className="text-[11px] text-slate-500">
                              {order.test_category} · {order.assigned_team}
                            </div>
                          </td>
                          <td className="px-2 py-3 align-top font-mono text-[11px] tabular-nums">
                            <div className="text-slate-700">
                              {new Date(order.expected_completion_at).toLocaleString([], {
                                month: 'short',
                                day: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </div>
                            {overdue && (
                              <span className="text-[10px] font-semibold text-amber-700">
                                Overdue SLA
                              </span>
                            )}
                          </td>
                          <td className="py-3 pl-2 pr-4 align-top font-mono text-[11px] font-semibold text-teal-700">
                            {order.lab_status}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Right 5 Cols: Order Detail & Status Transition Confirmation */}
            <div className="lg:col-span-5 space-y-6">
              <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-200 pb-3">
                  <h3 className="font-display text-sm font-bold text-slate-900">
                    Order Detail & Permitted Transitions
                  </h3>
                  <span className="font-mono text-[11px] text-teal-700">
                    Status updates are saved to the lab queue.
                  </span>
                </div>

                {!selectedOrder ? (
                  <p className="py-8 text-center text-xs text-slate-500">
                    Select a lab order to inspect details and update status.
                  </p>
                ) : (
                  <div className="space-y-4 text-xs">
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-1.5">
                      <div className="flex items-center justify-between font-mono">
                        <span className="font-bold text-slate-900">
                          Patient: {selectedOrder.patient_reference}
                        </span>
                        <span className="font-semibold text-teal-700">
                          {selectedOrder.lab_status}
                        </span>
                      </div>
                      <p className="font-semibold text-slate-900">
                        {selectedOrder.test_name || selectedOrder.test_category}
                      </p>
                      <p className="text-slate-600">
                        Category: {selectedOrder.test_category} · Team:{' '}
                        {selectedOrder.assigned_team}
                      </p>
                    </div>

                    <div>
                      <label className="block font-medium text-slate-700">
                        Select Permitted Canonical Status
                      </label>
                      <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
                        {CANONICAL_STATUSES.map((st) => (
                          <button
                            key={st}
                            type="button"
                            onClick={() => {
                              setNextStatus(st);
                              setShowTransitionConfirm(false);
                            }}
                            className={`rounded-lg border px-2.5 py-2 font-mono text-[11px] font-semibold transition-colors ${
                              nextStatus === st
                                ? 'border-teal-600 bg-teal-600 text-white'
                                : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100'
                            }`}
                          >
                            {st}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div>
                      <label className="block font-medium text-slate-700">
                        Processing Note / Delay Reason (Optional)
                      </label>
                      <input
                        type="text"
                        value={delayReasonInput}
                        onChange={(e) => setDelayReasonInput(e.target.value)}
                        placeholder="e.g. Analyzer calibration check..."
                        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900"
                      />
                    </div>

                    {!showTransitionConfirm ? (
                      <button
                        type="button"
                        onClick={() => setShowTransitionConfirm(true)}
                        className="w-full rounded-lg bg-teal-600 px-4 py-2.5 font-semibold text-white hover:bg-teal-700"
                      >
                        Prepare Status Update to {nextStatus}
                      </button>
                    ) : (
                      <div className="rounded-lg border border-amber-300 bg-amber-50 p-3.5 space-y-2.5">
                        <p className="font-semibold text-amber-900">
                          Confirm persisting status transition to {nextStatus} for{' '}
                          {selectedOrder.patient_reference}?
                        </p>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            disabled={isUpdatingStatus}
                            onClick={() => void handleCommitStatusUpdate()}
                            className="rounded-lg bg-slate-900 px-3.5 py-1.5 font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
                          >
                            {isUpdatingStatus ? 'Persisting...' : 'Confirm Update'}
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

              {/* Lab Audit History */}
              <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-3">
                <div className="flex items-center gap-2 border-b border-slate-200 pb-2.5">
                  <Activity className="h-4 w-4 text-teal-600" />
                  <h3 className="font-display text-sm font-bold text-slate-900">
                    Recent Lab Status History
                  </h3>
                </div>
                <div className="max-h-52 space-y-2 overflow-y-auto pr-1 text-xs">
                  {labAuditEvents.map((ev) => (
                    <div
                      key={ev.id}
                      className="rounded-lg border border-slate-200 bg-slate-50 p-2.5"
                    >
                      <div className="flex items-center justify-between font-mono text-[10px] text-slate-500">
                        <span className="font-semibold text-teal-700">{ev.action}</span>
                        <span>{new Date(ev.created_at).toLocaleTimeString()}</span>
                      </div>
                      <p className="mt-1 text-slate-700">{ev.details}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </StaffAuthGate>
  );
};
