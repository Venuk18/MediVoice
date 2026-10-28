import React, { useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  KeyRound,
  Lock,
  LogIn,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';
import { usePlatform } from '../app/PlatformContext';
import { StaffRoleType } from '../types/api';

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
    loginAsStaff,
    logoutStaff,
    isAuthenticating,
    authError,
    hasRolePermission,
    navigate,
  } = usePlatform();

  const [usernameInput, setUsernameInput] = useState('');
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
    <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A] py-12 px-4 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-2xl">
        <div className="mb-6 flex items-center justify-between">
          <button
            type="button"
            onClick={() => navigate('/')}
            className="inline-flex items-center gap-2 text-xs font-semibold text-slate-600 hover:text-slate-900 whitespace-nowrap shrink-0"
          >
            <ArrowLeft className="h-4 w-4" />
            Return to Public Hospital Website
          </button>
          <button
            type="button"
            onClick={() => navigate('/staff/login')}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-teal-700 hover:text-teal-900 whitespace-nowrap shrink-0"
          >
            Open Dedicated Staff Portal
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-6 sm:p-8 shadow-sm">
          <div className="flex flex-col gap-4 border-b border-slate-200 pb-6 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex items-start gap-3.5">
              <div
                className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border ${
                  isWrongRole
                    ? 'border-amber-300 bg-amber-50 text-amber-700'
                    : 'border-teal-200 bg-teal-50 text-teal-700'
                }`}
              >
                {isWrongRole ? <ShieldAlert className="h-5 w-5" /> : <Lock className="h-5 w-5" />}
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span className="font-mono font-semibold text-slate-800">
                    {isWrongRole ? 'HTTP 403 · Role Restricted' : 'HTTP 401 · Staff Sign-In Required'}
                  </span>
                  <span aria-hidden="true">·</span>
                  <span className="font-mono">
                    Authorized Role: {requiredRoles.join(' or ')}
                  </span>
                </div>
                <h1 className="mt-1.5 font-display text-2xl font-bold text-slate-900">
                  {workspaceTitle}
                </h1>
                <p className="mt-1 text-sm text-slate-600">{workspaceSubtitle}</p>
              </div>
            </div>
          </div>

          {isWrongRole && staffProfile && (
            <div className="mt-5 flex flex-col gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 text-xs text-amber-900">
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 mt-0.5" />
                <div>
                  <p className="font-semibold">
                    Currently signed in as {staffProfile.display_name} ({staffProfile.role})
                  </p>
                  <p className="mt-1 text-amber-800">
                    Role-based access control restricts <span className="font-mono">{staffProfile.role}</span> accounts
                    from accessing <span className="font-mono">{requiredRoles.join('/')}</span> workspaces.
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2 pl-7">
                <button
                  type="button"
                  onClick={() => {
                    if (staffProfile.role === 'DOCTOR') navigate('/doctor');
                    else if (staffProfile.role === 'LAB_OPERATOR') navigate('/lab');
                    else navigate('/maintenance');
                  }}
                  className="rounded-lg bg-amber-700 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-amber-800 whitespace-nowrap"
                >
                  Go to Your Authorized Workspace
                </button>
                <button
                  type="button"
                  onClick={logoutStaff}
                  className="rounded-lg border border-amber-300 bg-white px-3.5 py-1.5 text-xs font-semibold text-amber-900 hover:bg-amber-100 whitespace-nowrap"
                >
                  Sign Out to Switch Account
                </button>
              </div>
            </div>
          )}

          {authError && (
            <div className="mt-5 rounded-lg border border-rose-300 bg-rose-50 p-3.5 text-xs text-rose-800">
              {authError}
            </div>
          )}

          <div className="mt-6">
            <form
              onSubmit={(e) => void handleFormSubmit(e)}
              className="rounded-lg border border-slate-200 bg-slate-50/70 p-5 space-y-4"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
                  <KeyRound className="h-4 w-4 text-teal-600" />
                  <span>Staff Portal Credential Sign-In</span>
                </div>
                <span className="font-mono text-xs text-teal-700">POST /api/v1/auth/login</span>
              </div>

              <div>
                <label
                  htmlFor="staff-username-input"
                  className="block text-xs font-medium text-slate-700"
                >
                  Staff Username
                </label>
                <input
                  id="staff-username-input"
                  type="text"
                  required
                  value={usernameInput}
                  onChange={(e) => setUsernameInput(e.target.value)}
                  placeholder="Enter authorized staff username"
                  className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-xs text-slate-900 placeholder-slate-400 focus:border-teal-600 focus:outline-none"
                />
              </div>

              <div>
                <label
                  htmlFor="staff-password-input"
                  className="block text-xs font-medium text-slate-700"
                >
                  Staff Password
                </label>
                <input
                  id="staff-password-input"
                  type="password"
                  value={passwordInput}
                  onChange={(e) => setPasswordInput(e.target.value)}
                  placeholder="Enter staff password"
                  className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-xs text-slate-900 placeholder-slate-400 focus:border-teal-600 focus:outline-none"
                />
              </div>

              <button
                type="submit"
                disabled={isAuthenticating || !usernameInput.trim()}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-xs font-semibold text-white transition-colors hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 disabled:opacity-50 whitespace-nowrap"
              >
                <LogIn className="h-4 w-4" />
                {isAuthenticating ? 'Verifying Staff Credentials...' : 'Sign In to Workspace'}
              </button>

              <div className="flex items-start gap-2 pt-1 text-[11px] text-slate-500">
                <ShieldCheck className="h-4 w-4 shrink-0 text-teal-600" />
                <span>
                  Protected by HMAC-SHA256 Bearer authentication and role-based access control.
                </span>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};
