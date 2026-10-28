import React from 'react';
import { AppRoutePath } from '../types/api';
import { usePlatform } from '../app/PlatformContext';

const PATIENT_NAV_LINKS: Array<{ label: string; route: AppRoutePath }> = [
  { label: 'Home', route: '/' },
  { label: 'Find Doctors', route: '/doctors' },
  { label: 'Appointments', route: '/appointments' },
  { label: 'Lab Status', route: '/lab-status' },
  { label: 'Insurance Help', route: '/insurance' },
];

export const TopNav: React.FC = () => {
  const { currentRoute, navigate, launchMediVoiceWithPrompt } = usePlatform();

  return (
    <header className="sticky top-0 z-40 border-b border-[#334155]/80 bg-[#0B1020]/95 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between gap-8 px-4 sm:px-6 lg:px-8">
        {/* Zone 1: Single text element wordmark */}
        <button
          type="button"
          onClick={() => navigate('/')}
          className="font-display text-lg font-bold tracking-tight text-[#E5EDF7] hover:text-[#2DD4BF] transition-colors whitespace-nowrap shrink-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#38BDF8] rounded"
        >
          MediVoice AI
        </button>

        {/* Zone 2: 5 clean single-line text navigation links */}
        <nav
          aria-label="Patient Website Navigation"
          className="hidden md:flex items-center gap-7 text-sm font-medium text-[#94A3B8]"
        >
          {PATIENT_NAV_LINKS.map((item) => {
            const isActive = currentRoute === item.route;
            return (
              <button
                key={item.route}
                type="button"
                onClick={() => navigate(item.route)}
                className={`py-1 transition-colors whitespace-nowrap shrink-0 border-b-2 ${
                  isActive
                    ? 'border-[#2DD4BF] text-[#E5EDF7]'
                    : 'border-transparent text-[#94A3B8] hover:text-[#E5EDF7] hover:border-[#334155]'
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </nav>

        {/* Zone 3: 1 primary action */}
        <div className="flex items-center gap-3 shrink-0">
          <button
            type="button"
            onClick={() => launchMediVoiceWithPrompt()}
            className="rounded-lg bg-[#2DD4BF] px-4 py-2 text-xs font-semibold text-[#0B1020] transition-colors hover:bg-[#2DD4BF]/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#38BDF8] whitespace-nowrap shrink-0"
          >
            Talk to MediVoice
          </button>
        </div>
      </div>

      {/* Mobile horizontal nav links */}
      <div className="flex md:hidden items-center gap-5 overflow-x-auto border-t border-[#334155]/60 px-4 py-2 text-xs font-medium text-[#94A3B8]">
        {PATIENT_NAV_LINKS.map((item) => {
          const isActive = currentRoute === item.route;
          return (
            <button
              key={item.route}
              type="button"
              onClick={() => navigate(item.route)}
              className={`whitespace-nowrap shrink-0 pb-0.5 border-b-2 ${
                isActive
                  ? 'border-[#2DD4BF] text-[#E5EDF7]'
                  : 'border-transparent text-[#94A3B8]'
              }`}
            >
              {item.label}
            </button>
          );
        })}
      </div>
    </header>
  );
};
