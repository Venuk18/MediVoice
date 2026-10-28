import React, { useState } from 'react';
import {
  Activity,
  ChevronDown,
  FlaskConical,
  LogOut,
  RefreshCw,
  ShieldCheck,
  Stethoscope,
  UserCheck,
  Wrench,
} from 'lucide-react';
import { usePlatform } from '../../context/PlatformContext';
import { WorkspaceTab } from '../../types/api';

const WORKSPACE_NAV_ITEMS: Array<{
  id: WorkspaceTab;
  label: string;
  requiredRoleLabel?: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  {
    id: 'patient',
    label: 'Patient Portal & AI Assistant',
    icon: Activity,
  },
  {
    id: 'doctor',
    label: 'Doctor Workspace',
    requiredRoleLabel: 'DOCTOR',
    icon: Stethoscope,
  },
  {
    id: 'lab',
    label: 'Laboratory Operations',
    requiredRoleLabel: 'LAB_OPERATOR',
    icon: FlaskConical,
  },
  {
    id: 'maintenance',
    label: 'Facilities & Maintenance',
    requiredRoleLabel: 'MAINTENANCE_STAFF',
    icon: Wrench,
  },
];

export const TopNav: React.FC = () => {
  const {
    activeWorkspace,
    setActiveWorkspace,
    staffProfile,
    demoAccounts,
    loginAsStaff,
    logoutStaff,
    isAuthenticating,
    isSyncing,
    lastSyncedAt,
    refreshOperationalData,
    refreshMaintenanceData,
  } = usePlatform();

  const [roleMenuOpen, setRoleMenuOpen] = useState(false);

  const handleManualRefresh = async () => {
    await refreshOperationalData();
    await refreshMaintenanceData();
  };

  const handleQuickRoleSwitch = async (username: string, route: WorkspaceTab) => {
    const profile = await loginAsStaff(username);
    setRoleMenuOpen(false);
    if (profile) {
      setActiveWorkspace(route);
    }
  };

  return (
    <header className="sticky top-0 z-40 border-b border-[#334155]/80 bg-[#0B1020]/95 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-4 px-4 py-3.5 sm:px-6 lg:px-8">
        {/* Clean Brand Wordmark (No floating stat pills or location clutter per design rules) */}
        <button
          type="button"
          onClick={() => setActiveWorkspace('patient')}
          className="group flex items-center gap-3 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-[#2DD4BF] rounded-lg"
        >
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#2DD4BF]/40 bg-[#111B2E] text-[#2DD4BF] transition-colors group-hover:border-[#2DD4BF]">
            <Activity className="h-5 w-5" />
          </div>
          <span className="font-display text-lg font-bold tracking-tight text-[#E5EDF7]">
            Aarogya One Hospital
          </span>
        </button>

        {/* Primary Workspace Navigation (4 Top-Level Items) */}
        <nav
          aria-label="Hospital Platform Workspaces"
          className="flex flex-wrap items-center gap-1 rounded-xl border border-[#334155]/80 bg-[#111B2E]/90 p-1"
        >
          {WORKSPACE_NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeWorkspace === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setActiveWorkspace(item.id)}
                className={`flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-medium transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-[#38BDF8] sm:text-sm ${
                  isActive
                    ? 'bg-[#2DD4BF] text-[#0B1020] font-semibold shadow-sm'
                    : 'text-[#94A3B8] hover:bg-[#0B1020]/60 hover:text-[#E5EDF7]'
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="whitespace-nowrap">{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Right Controls: Sync Action + Role-Based Staff Session Switcher */}
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => void handleManualRefresh()}
            disabled={isSyncing}
            title={lastSyncedAt ? `Last synchronized at ${lastSyncedAt}` : 'Synchronize with hospital backend'}
            className="flex items-center gap-1.5 rounded-lg border border-[#334155] bg-[#111B2E] px-3 py-2 text-xs font-medium text-[#94A3B8] transition-colors hover:border-[#38BDF8]/60 hover:text-[#E5EDF7] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#38BDF8] disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 text-[#38BDF8] ${isSyncing ? 'animate-spin' : ''}`} />
            <span className="hidden xl:inline font-mono tabular-nums">
              {lastSyncedAt ? `Sync ${lastSyncedAt}` : 'Sync Data'}
            </span>
          </button>

          {/* Staff Session Dropdown */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setRoleMenuOpen((prev) => !prev)}
              aria-expanded={roleMenuOpen}
              className="flex items-center gap-2 rounded-lg border border-[#334155] bg-[#111B2E] px-3.5 py-2 text-xs font-medium text-[#E5EDF7] transition-colors hover:border-[#2DD4BF]/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#2DD4BF]"
            >
              {staffProfile ? (
                <>
                  <UserCheck className="h-4 w-4 text-[#2DD4BF]" />
                  <span className="max-w-[150px] truncate font-semibold">
                    {staffProfile.display_name}
                  </span>
                  <span className="rounded bg-[#2DD4BF]/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-[#2DD4BF]">
                    {staffProfile.role}
                  </span>
                </>
              ) : (
                <>
                  <ShieldCheck className="h-4 w-4 text-[#94A3B8]" />
                  <span>Staff Role Sign-In</span>
                </>
              )}
              <ChevronDown className="h-3.5 w-3.5 text-[#94A3B8]" />
            </button>

            {roleMenuOpen && (
              <div className="absolute right-0 mt-2 w-80 rounded-xl border border-[#334155] bg-[#111B2E] p-3 shadow-2xl z-50">
                <div className="mb-2 flex items-center justify-between border-b border-[#334155]/70 pb-2">
                  <div>
                    <p className="text-xs font-semibold text-[#E5EDF7]">
                      Hospital Staff RBAC Switcher
                    </p>
                    <p className="text-[11px] text-[#94A3B8]">
                      Synthetic demo credentials enforced on backend API
                    </p>
                  </div>
                  {staffProfile && (
                    <button
                      type="button"
                      onClick={() => {
                        logoutStaff();
                        setRoleMenuOpen(false);
                      }}
                      className="flex items-center gap-1 rounded border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-[11px] font-medium text-rose-300 hover:bg-rose-500/20"
                    >
                      <LogOut className="h-3 w-3" />
                      Sign Out
                    </button>
                  )}
                </div>

                <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
                  {demoAccounts.map((acc) => {
                    const isCurrent = staffProfile?.username === acc.username;
                    return (
                      <button
                        key={acc.username}
                        type="button"
                        disabled={isAuthenticating}
                        onClick={() => void handleQuickRoleSwitch(acc.username, acc.workspace_route)}
                        className={`w-full rounded-lg border p-2.5 text-left transition-all ${
                          isCurrent
                            ? 'border-[#2DD4BF] bg-[#2DD4BF]/10'
                            : 'border-[#334155]/70 bg-[#0B1020]/70 hover:border-[#38BDF8]/60'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-semibold text-[#E5EDF7]">
                            {acc.display_name}
                          </span>
                          <span className="rounded bg-[#0B1020] px-1.5 py-0.5 font-mono text-[10px] font-semibold text-[#38BDF8] border border-[#334155]">
                            {acc.role}
                          </span>
                        </div>
                        <p className="mt-0.5 text-[11px] text-[#94A3B8] truncate">
                          {acc.badge_label}
                        </p>
                        <p className="mt-1 font-mono text-[10px] text-[#2DD4BF]">
                          User: {acc.username} {isCurrent ? '• Active Session' : '• Click to Sign In'}
                        </p>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};
