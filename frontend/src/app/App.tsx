import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { PlatformProvider, usePlatform } from './PlatformContext';
import { TopNav } from '../components/TopNav';
import { PatientWebsiteView } from '../features/patient/PatientWebsiteView';
import { DoctorWorkspaceView } from '../features/doctor/DoctorWorkspaceView';
import { LaboratoryWorkspaceView } from '../features/laboratory/LaboratoryWorkspaceView';
import { MaintenanceWorkspaceView } from '../features/maintenance/MaintenanceWorkspaceView';

const MediVoicePlatformShell: React.FC = () => {
  const {
    currentRoute,
    activeWorkspace,
    navigate,
    backendConnected,
    isInitialLoading,
    syncError,
    refreshOperationalData,
  } = usePlatform();

  const isPatientExperience = activeWorkspace === 'patient';
  const isStaffPortalRoute = currentRoute === '/staff/login' || currentRoute === '/login';

  return (
    <div
      className={
        isPatientExperience
          ? 'patient-shell min-h-screen flex flex-col selection:bg-violet-200 selection:text-violet-950'
          : 'staff-workspace min-h-screen text-[#17233B] flex flex-col selection:bg-violet-200 selection:text-violet-950'
      }
    >
      {isPatientExperience && !isStaffPortalRoute && <TopNav />}

      {!backendConnected && !isInitialLoading && syncError && (
        <div className="border-b border-rose-500/40 bg-rose-500/10 px-4 py-3 text-xs text-rose-200">
          <div className="mx-auto flex max-w-[1440px] flex-col items-start justify-between gap-2 sm:flex-row sm:items-center">
            <div className="flex items-center gap-2.5">
              <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
              <span>
                <strong>Backend Connection Alert:</strong> {syncError}
              </span>
            </div>
            <button
              type="button"
              onClick={() => void refreshOperationalData()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-rose-400/40 bg-[#0B1020] px-3 py-1 font-mono text-[11px] font-semibold text-rose-200 hover:bg-rose-500/20"
            >
              <RefreshCw className="h-3 w-3" />
              Retry Connection
            </button>
          </div>
        </div>
      )}

      <main className="flex-1">
        {activeWorkspace === 'patient' && <PatientWebsiteView />}
        {activeWorkspace === 'doctor' && <DoctorWorkspaceView />}
        {activeWorkspace === 'lab' && <LaboratoryWorkspaceView />}
        {activeWorkspace === 'maintenance' && <MaintenanceWorkspaceView />}
      </main>

      {isPatientExperience && !isStaffPortalRoute && (
        <footer className="border-t border-violet-100 bg-white py-8 text-xs text-slate-500">
          <div className="mx-auto flex max-w-[1440px] flex-col justify-between gap-6 px-4 sm:px-6 lg:flex-row lg:items-center lg:px-8">
            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-900">
                <span className="font-display font-bold">MediVoice AI</span>
                <span aria-hidden="true">·</span>
                <span>Aarogya One Hospital</span>
              </div>
              <p className="text-[11px] text-[#94A3B8]">
                Routine scheduling, 6-digit laboratory verification, and document-grounded insurance
                guidance. Not an autonomous medical diagnosis system.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-5 text-xs">
              <button
                type="button"
                onClick={() => navigate('/doctors')}
                className="hover:text-violet-700 whitespace-nowrap"
              >
                Find Doctors
              </button>
              <button
                type="button"
                onClick={() => navigate('/appointments')}
                className="hover:text-violet-700 whitespace-nowrap"
              >
                Appointments
              </button>
              <button
                type="button"
                onClick={() => navigate('/lab-status')}
                className="hover:text-violet-700 whitespace-nowrap"
              >
                Lab Status
              </button>
              <button
                type="button"
                onClick={() => navigate('/insurance')}
                className="hover:text-violet-700 whitespace-nowrap"
              >
                Insurance Help
              </button>
              <button
                type="button"
                onClick={() => navigate('/staff/login')}
                className="text-slate-400 hover:text-violet-700 whitespace-nowrap"
              >
                Staff Portal
              </button>
            </div>
          </div>
        </footer>
      )}
    </div>
  );
};

export function App() {
  return (
    <PlatformProvider>
      <MediVoicePlatformShell />
    </PlatformProvider>
  );
}

export default App;
