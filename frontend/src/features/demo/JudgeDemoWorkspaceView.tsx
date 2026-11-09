import React from 'react';
import { ArrowLeft, LogOut, ShieldCheck } from 'lucide-react';
import { usePlatform } from '../../app/PlatformContext';

const examples = [
  { title: 'Conversational scheduling', detail: 'A synthetic patient can ask for a specialty, compare example availability, and review a booking confirmation.' },
  { title: 'Voice interaction', detail: 'The public demo illustrates speech input and spoken assistant responses when voice services are available.' },
  { title: 'Staff workflow controls', detail: 'Role-specific workspaces protect operational actions behind staff authentication and authorization.' },
];

export const JudgeDemoWorkspaceView: React.FC = () => {
  const { staffProfile, navigate, logoutStaff } = usePlatform();

  if (!staffProfile || staffProfile.role !== 'DEMO_VIEWER') {
    return (
      <main className="min-h-screen bg-slate-50 px-4 py-12 text-slate-900">
        <section className="mx-auto max-w-xl rounded-2xl border border-slate-200 bg-white p-7 shadow-sm">
          <h1 className="text-xl font-bold">Evaluation portal access required</h1>
          <p className="mt-2 text-sm text-slate-600">Sign in with the dedicated read-only evaluation account to continue.</p>
          <button className="mt-5 rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white" onClick={() => navigate('/staff/login')}>Open staff sign-in</button>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8 text-slate-900 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl">
        <header className="flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-slate-950 p-6 text-white">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-teal-300">MediVoice AI · Evaluation</p>
            <h1 className="mt-2 text-2xl font-bold">Read-only demonstration portal</h1>
            <p className="mt-1 text-sm text-slate-300">Signed in as {staffProfile.display_name}</p>
          </div>
          <button onClick={logoutStaff} className="inline-flex items-center gap-2 rounded-lg border border-white/20 px-4 py-2 text-sm hover:bg-white/10">
            <LogOut className="h-4 w-4" /> Sign out
          </button>
        </header>

        <section className="mt-6 rounded-2xl border border-teal-200 bg-teal-50 p-5 text-sm text-teal-950">
          <div className="flex gap-3"><ShieldCheck className="h-5 w-5 shrink-0" /><p><strong>Limited access:</strong> This account has no access to patient records, appointment data, laboratory records, or staff administration. All examples below are synthetic and read-only.</p></div>
        </section>

        <section className="mt-8 grid gap-4 md:grid-cols-3">
          {examples.map((item) => (
            <article key={item.title} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wide text-teal-700">Demo scenario</p>
              <h2 className="mt-3 text-lg font-bold">{item.title}</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">{item.detail}</p>
            </article>
          ))}
        </section>

        <button onClick={() => navigate('/')} className="mt-8 inline-flex items-center gap-2 text-sm font-semibold text-slate-600 hover:text-teal-700">
          <ArrowLeft className="h-4 w-4" /> Return to public MediVoice experience
        </button>
      </div>
    </main>
  );
};
