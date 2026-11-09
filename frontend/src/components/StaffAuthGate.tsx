import React from 'react';
import { ArrowLeft, ArrowRight, Lock, ShieldAlert } from 'lucide-react';
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
  const { staffProfile, hasRolePermission, navigate, logoutStaff } = usePlatform();

  if (staffProfile && hasRolePermission(requiredRoles)) return <>{children}</>;

  const isWrongRole = Boolean(staffProfile);
  return (
    <main className="staff-workspace min-h-screen px-4 py-12 text-[#17233B] sm:px-6 lg:px-8">
      <div className="mx-auto max-w-2xl">
        <button type="button" onClick={() => navigate('/')} className="mb-6 inline-flex items-center gap-2 text-sm font-semibold text-slate-600 hover:text-violet-700">
          <ArrowLeft className="h-4 w-4" /> Return to patient site
        </button>
        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <div className="flex items-start gap-4">
            <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl ${isWrongRole ? 'bg-amber-50 text-amber-700' : 'bg-violet-50 text-violet-700'}`}>
              {isWrongRole ? <ShieldAlert className="h-6 w-6" /> : <Lock className="h-6 w-6" />}
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[.12em] text-violet-700">Staff workspace</p>
              <h1 className="mt-1 font-display text-2xl font-bold">{workspaceTitle}</h1>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">{workspaceSubtitle}</p>
            </div>
          </div>
          {isWrongRole ? (
            <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
              <p className="font-semibold">This workspace is limited to {requiredRoles.join(' or ')} staff.</p>
              <p className="mt-1">You are signed in as {staffProfile?.display_name} ({staffProfile?.role}).</p>
              <div className="mt-4 flex flex-wrap gap-3">
                <button type="button" onClick={() => { if (staffProfile?.role === 'DEMO_VIEWER') navigate('/staff/demo'); else if (staffProfile?.role === 'DOCTOR') navigate('/doctor'); else if (staffProfile?.role === 'LAB_OPERATOR') navigate('/lab'); else navigate('/maintenance'); }} className="rounded-full bg-amber-800 px-4 py-2 text-xs font-semibold text-white hover:bg-amber-900">Open your workspace</button>
                <button type="button" onClick={logoutStaff} className="rounded-full border border-amber-300 bg-white px-4 py-2 text-xs font-semibold text-amber-950 hover:bg-amber-100">Sign out</button>
              </div>
            </div>
          ) : (
            <div className="mt-6 rounded-2xl bg-violet-50 p-5">
              <p className="text-sm font-semibold text-slate-900">Sign in through the Staff Portal to continue.</p>
              <p className="mt-1 text-sm text-slate-600">Your account role determines which workspace you can access.</p>
              <button type="button" onClick={() => navigate('/staff/login')} className="mt-4 inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-violet-600 to-blue-600 px-5 py-2.5 text-sm font-semibold text-white">
                Go to Staff Portal <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          )}
        </section>
      </div>
    </main>
  );
};
