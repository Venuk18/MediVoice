import React, { useState } from 'react';
import { AlertCircle, CheckCircle2, Clock, KeyRound, Search, ShieldCheck } from 'lucide-react';
import { ApiError, medivoiceApi } from '../../services/api';
import { LabVerificationResponse } from '../../types/api';

export const LabVerificationSection: React.FC = () => {
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<LabVerificationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const verify = async (event: React.FormEvent) => {
    event.preventDefault();
    const value = code.trim();
    if (!/^\d{6}$/.test(value)) {
      setResult(null);
      setError('Enter the six-digit code printed on your lab receipt.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setResult(await medivoiceApi.verifyLabOrderCode(value));
    } catch (cause) {
      setResult(null);
      setError(cause instanceof ApiError ? cause.message : 'Lab status is unavailable. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <section id="lab-verification-section" className="space-y-8">
      <header className="border-b border-slate-200 pb-5">
        <p className="text-xs font-semibold uppercase tracking-wider text-violet-700">Laboratory updates</p>
        <h2 className="mt-1 font-display text-2xl font-bold text-slate-900 sm:text-3xl">Check your lab status</h2>
        <p className="mt-1 text-sm text-slate-600">Enter the private six-digit code from your receipt. This page shows processing status, not clinical results.</p>
      </header>
      <div className="max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <form onSubmit={(event) => void verify(event)} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex-1 text-sm font-medium text-slate-800" htmlFor="lab-verification-code-input">
            Receipt verification code
            <span className="relative mt-2 block">
              <KeyRound className="pointer-events-none absolute left-3.5 top-3 h-4 w-4 text-violet-600" />
              <input id="lab-verification-code-input" type="text" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))} placeholder="Six-digit code" className="w-full rounded-xl border border-slate-300 py-2.5 pl-10 pr-4 font-mono text-base tracking-[0.25em] text-slate-900 placeholder:tracking-normal" />
            </span>
          </label>
          <button type="submit" disabled={loading || code.length !== 6} className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-violet-700 px-6 text-sm font-semibold text-white disabled:opacity-50"><Search className="h-4 w-4" />{loading ? 'Checking…' : 'Check status'}</button>
        </form>
        {error && <p role="alert" className="mt-4 flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900"><AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />{error}</p>}
        {result && <article className="mt-5 rounded-xl border border-violet-100 bg-violet-50/50 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-violet-100 pb-3"><h3 className="font-display text-lg font-bold text-slate-900">{result.test_name}</h3><span className="rounded-full bg-teal-50 px-3 py-1 font-mono text-xs font-semibold text-teal-900">{result.lab_status}</span></div>
          <p className="mt-4 text-sm leading-relaxed text-slate-800">{result.status_explanation}</p>
          <p className="mt-3 text-sm text-blue-900"><strong>Next step:</strong> {result.next_step}</p>
          <p className="mt-4 flex items-center gap-2 border-t border-violet-100 pt-3 text-xs text-slate-600"><Clock className="h-4 w-4" />Last updated {new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' }).format(new Date(result.last_updated_at))} IST</p>
          <p className="mt-3 flex items-start gap-2 text-xs text-slate-600"><ShieldCheck className="h-4 w-4 shrink-0 text-teal-700" />{result.disclaimer}</p>
          <p className="mt-3 flex items-center gap-2 text-xs font-medium text-teal-900"><CheckCircle2 className="h-4 w-4" />No clinical results are shown here.</p>
        </article>}
      </div>
    </section>
  );
};