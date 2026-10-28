import React, { useState } from 'react';
import {
  AlertTriangle,
  KeyRound,
  Lock,
  LogIn,
  ShieldAlert,
  ShieldCheck,
  UserCheck,
} from 'lucide-react';
import { usePlatform } from '../../context/PlatformContext';
import { StaffRoleType } from '../../types/api';

interface StaffAuthGateProps {
  requiredRoles: StaffRoleType[];
  workspaceTitle: string;
  workspaceSubtitle: string;
  children: React.ReactNode;
}

export const StaffAuthGate: React.FC<StaffAuthGateProps> = ({
  requiredRoles,
  workspaceTitle,
  workspaceSubtitle,
  children,
}) => {
  const {
    staffProfile,
    demoAccounts,
    loginAsStaff,
    isAuthenticating,
    authError,
    hasRolePermission,
  } = usePlatform();

  const matchingAccounts = demoAccounts.filter(
    (acc) => requiredRoles.includes(acc.role) || acc.role === 'ADMIN'
  );

  const [usernameInput, setUsernameInput] = useState(
    matchingAccounts[0]?.username || 'dr.sharma'
  );
  const [passwordInput, setPasswordInput] = useState('');

  if (staffProfile && hasRolePermission(requiredRoles)) {
    return <>{children}</>;
  }

  const isWrongRole = Boolean(staffProfile && !hasRolePermission(requiredRoles));

  const handleFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!usernameInput.trim()) return;
    await loginAsStaff(usernameInput.trim(), passwordInput.trim() || undefined);
  };

  return (
    <div className="mx-auto max-w-4xl px-4 py-12 sm:px-6 lg:px-8">
      <div className="rounded-2xl border border-[#334155] bg-[#111B2E] p-6 sm:p-8">
        {/* Status Banner: 401 Unauthenticated vs 403 Unauthorized Role */}
        <div className="flex flex-col gap-4 border-b border-[#334155] pb-6 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3.5">
            <div
              className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border ${
                isWrongRole
                  ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
                  : 'border-[#38BDF8]/40 bg-[#38BDF8]/10 text-[#38BDF8]'
              }`}
            >
              {isWrongRole ? <ShieldAlert className="h-5 w-5" /> : <Lock className="h-5 w-5" />}
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`rounded px-2 py-0.5 font-mono text-xs font-semibold ${
                    isWrongRole
                      ? 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                      : 'bg-[#38BDF8]/15 text-[#38BDF8] border border-[#38BDF8]/30'
                  }`}
                >
                  {isWrongRole ? 'HTTP 403 • ROLE RESTRICTED' : 'HTTP 401 • STAFF AUTH REQUIRED'}
                </span>
                <span className="font-mono text-xs text-[#94A3B8]">
                  Required Role: {requiredRoles.join(' or ')}
                </span>
              </div>
              <h1 className="mt-2 font-display text-2xl font-bold text-[#E5EDF7]">
                {workspaceTitle}
              </h1>
              <p className="mt-1 text-sm text-[#94A3B8]">{workspaceSubtitle}</p>
            </div>
          </div>
        </div>

        {isWrongRole && staffProfile && (
          <div className="mt-5 flex items-start gap-3 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-xs text-amber-200">
            <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
            <div>
              <p className="font-semibold">
                Signed in as {staffProfile.display_name} ({staffProfile.role})
              </p>
              <p className="mt-1 text-amber-200/85">
                Backend role-based authorization blocks <span className="font-mono">{staffProfile.role}</span> accounts
                from performing <span className="font-mono">{requiredRoles.join('/')}</span> operations. Select an
                authorized synthetic staff account below to switch sessions.
              </p>
            </div>
          </div>
        )}

        {authError && (
          <div className="mt-5 rounded-xl border border-rose-500/40 bg-rose-500/10 p-3.5 text-xs text-rose-200">
            {authError}
          </div>
        )}

        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-12">
          {/* Quick Demo Account Selector */}
          <div className="lg:col-span-7 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">
                Approved Synthetic Accounts for This Workspace
              </h2>
              <span className="font-mono text-[11px] text-[#2DD4BF]">
                POST /api/v1/auth/login
              </span>
            </div>

            <div className="space-y-2.5">
              {matchingAccounts.map((acc) => (
                <div
                  key={acc.username}
                  className="flex flex-col justify-between gap-3 rounded-xl border border-[#334155] bg-[#0B1020] p-4 sm:flex-row sm:items-center"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-display text-sm font-bold text-[#E5EDF7]">
                        {acc.display_name}
                      </span>
                      <span className="rounded border border-[#2DD4BF]/40 bg-[#2DD4BF]/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-[#2DD4BF]">
                        {acc.role}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-[#94A3B8]">{acc.badge_label}</p>
                    <p className="mt-1.5 font-mono text-[11px] text-[#38BDF8]">
                      username: {acc.username} • password: {acc.demo_password}
                    </p>
                  </div>

                  <button
                    type="button"
                    disabled={isAuthenticating}
                    onClick={() => void loginAsStaff(acc.username, acc.demo_password)}
                    className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-[#2DD4BF] px-4 py-2 text-xs font-semibold text-[#0B1020] transition-colors hover:bg-[#2DD4BF]/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#38BDF8] disabled:opacity-50"
                  >
                    <UserCheck className="h-4 w-4" />
                    Sign In as {acc.display_name.split(' ')[0]}
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Direct Credential Sign-In Form */}
          <div className="lg:col-span-5">
            <form
              onSubmit={(e) => void handleFormSubmit(e)}
              className="rounded-xl border border-[#334155] bg-[#0B1020] p-5 space-y-4"
            >
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-[#94A3B8]">
                <KeyRound className="h-4 w-4 text-[#38BDF8]" />
                <span>Staff Credential Login</span>
              </div>

              <div>
                <label
                  htmlFor="staff-username-input"
                  className="block text-xs font-medium text-[#E5EDF7]"
                >
                  Staff Username
                </label>
                <input
                  id="staff-username-input"
                  type="text"
                  value={usernameInput}
                  onChange={(e) => setUsernameInput(e.target.value)}
                  placeholder="e.g., dr.sharma, lab.vikram, maint.karthik"
                  className="mt-1.5 w-full rounded-lg border border-[#334155] bg-[#111B2E] px-3 py-2 font-mono text-xs text-[#E5EDF7] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none"
                />
              </div>

              <div>
                <label
                  htmlFor="staff-password-input"
                  className="block text-xs font-medium text-[#E5EDF7]"
                >
                  Demo Password (Optional for Synthetic Switch)
                </label>
                <input
                  id="staff-password-input"
                  type="password"
                  value={passwordInput}
                  onChange={(e) => setPasswordInput(e.target.value)}
                  placeholder="Enter demo password"
                  className="mt-1.5 w-full rounded-lg border border-[#334155] bg-[#111B2E] px-3 py-2 font-mono text-xs text-[#E5EDF7] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none"
                />
              </div>

              <button
                type="submit"
                disabled={isAuthenticating || !usernameInput.trim()}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-[#38BDF8]/50 bg-[#38BDF8]/15 px-4 py-2.5 text-xs font-semibold text-[#38BDF8] transition-colors hover:bg-[#38BDF8]/25 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#38BDF8] disabled:opacity-50"
              >
                <LogIn className="h-4 w-4" />
                {isAuthenticating ? 'Verifying Staff Token...' : 'Authenticate Staff Session'}
              </button>

              <div className="flex items-start gap-2 pt-1 text-[11px] text-[#94A3B8]">
                <ShieldCheck className="h-4 w-4 shrink-0 text-[#2DD4BF]" />
                <span>
                  Issues an HMAC-SHA256 signed Bearer token verified on every protected API mutation.
                </span>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};
