import React, { useState } from 'react';
import { ArrowLeft, Lock, ShieldAlert } from 'lucide-react';
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
  const { staffProfile, loginAsStaff, isAuthenticating, authError, hasRolePermission } = usePlatform();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  if (staffProfile && hasRolePermission(requiredRoles)) return <>{children}</>;
  const wrongRole = Boolean(staffProfile);

  return (
    <main className="mx-auto min-h-[70vh] max-w-2xl px-4 py-12 text-slate-900 sm:px-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <div className="flex items-start gap-4">
          <div className="rounded-2xl bg-violet-50 p-3 text-violet-700">
            {wrongRole ? <ShieldAlert className="h-6 w-6" /> : <Lock className="h-6 w-6" />}
          </div>
          <div>
            <h1 className="font-display text-2xl font-bold">{workspaceTitle}</h1>
            <p className="mt-2 text-sm text-slate-600">{workspaceSubtitle}</p>
          </div>
        </div>
        {wrongRole && <p className="mt-5 rounded-xl bg-amber-50 p-4 text-sm text-amber-950">This workspace requires {requiredRoles.join(' or ')} access. Signed in as {staffProfile?.display_name} ({staffProfile?.role}).</p>}
        {authError && <p role="alert" className="mt-5 rounded-xl bg-rose-50 p-4 text-sm text-rose-900">{authError}</p>}
        <form className="mt-6 space-y-4" onSubmit={(event) => { event.preventDefault(); void loginAsStaff(username.trim(), password); }}>
          <label className="block text-sm font-medium">Staff username<input required autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-300 px-3 py-2.5" /></label>
          <label className="block text-sm font-medium">Password<input required type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} className="mt-1.5 w-full rounded-xl border border-slate-300 px-3 py-2.5" /></label>
          <button type="submit" disabled={isAuthenticating || !username.trim() || !password} className="w-full rounded-xl bg-violet-700 px-4 py-3 text-sm font-semibold text-white disabled:opacity-50">{isAuthenticating ? 'Signing in…' : 'Sign in to staff workspace'}</button>
        </form>
      </section>
    </main>
  );
};