import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FlaskConical,
  KeyRound,
  Search,
  ShieldCheck,
} from 'lucide-react';
import { usePlatform } from '../../context/PlatformContext';
import { ApiError, medivoiceApi } from '../../services/api';
import {
  CanonicalLabStatus,
  LabOrderDemoPortalRead,
  LabVerificationResponse,
} from '../../types/api';

const LAB_STAGES: CanonicalLabStatus[] = [
  'REGISTERED',
  'SAMPLE_COLLECTED',
  'PROCESSING',
  'COMPLETED',
];

const DEMO_PATIENTS = [
  'PAT-2024-9182',
  'PAT-2024-3310',
  'PAT-2024-7744',
  'PAT-2026-4409',
  'PAT-2024-5501',
];

export const LabVerificationSection: React.FC = () => {
  const { activePatientRef, setActivePatientRef, lastSyncedAt } = usePlatform();

  const [codeInput, setCodeInput] = useState<string>('048271');
  const [isVerifying, setIsVerifying] = useState<boolean>(false);
  const [verifyResult, setVerifyResult] = useState<LabVerificationResponse | null>(null);
  const [verifyError, setVerifyError] = useState<{ code: string; message: string } | null>(
    null
  );

  const [demoReceipts, setDemoReceipts] = useState<LabOrderDemoPortalRead[]>([]);
  const [loadingReceipts, setLoadingReceipts] = useState<boolean>(false);

  const handleVerifyCode = async (overrideCode?: string) => {
    const cleaned = (overrideCode !== undefined ? overrideCode : codeInput).trim();
    if (overrideCode !== undefined) {
      setCodeInput(cleaned);
    }

    setVerifyError(null);
    if (!/^\d{6}$/.test(cleaned)) {
      setVerifyResult(null);
      setVerifyError({
        code: 'INVALID_CODE_FORMAT',
        message:
          'Verification code must be an exact 6-digit string ("000000" through "999999"), preserving leading zeros.',
      });
      return;
    }

    setIsVerifying(true);
    try {
      const res = await medivoiceApi.verifyLabOrderCode(cleaned, `web-${activePatientRef}`);
      setVerifyResult(res);
    } catch (err) {
      setVerifyResult(null);
      if (err instanceof ApiError) {
        setVerifyError({ code: err.code, message: err.message });
      } else {
        setVerifyError({
          code: 'SERVICE_UNAVAILABLE',
          message: 'Unable to verify lab order status at this time.',
        });
      }
    } finally {
      setIsVerifying(false);
    }
  };

  const loadDemoPatientReceipts = async (patientRef: string) => {
    if (!patientRef.trim()) return;
    setLoadingReceipts(true);
    try {
      const rows = await medivoiceApi.getDemoPatientLabReceipts(patientRef.trim());
      setDemoReceipts(rows);
    } catch {
      setDemoReceipts([]);
    } finally {
      setLoadingReceipts(false);
    }
  };

  useEffect(() => {
    void loadDemoPatientReceipts(activePatientRef);
  }, [activePatientRef, lastSyncedAt]);

  // Automatically verify initial seeded code on mount
  useEffect(() => {
    void handleVerifyCode('048271');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const currentStageIndex = verifyResult
    ? LAB_STAGES.indexOf(verifyResult.lab_status)
    : -1;

  return (
    <section id="lab-verification-section" className="space-y-8">
      <div className="flex flex-col justify-between gap-4 border-b border-[#334155] pb-5 sm:flex-row sm:items-end">
        <div>
          <span className="font-mono text-xs font-semibold uppercase tracking-wider text-[#38BDF8]">
            02 • Privacy-Preserving Diagnostics Status
          </span>
          <h2 className="mt-1 font-display text-2xl font-bold text-[#E5EDF7] sm:text-3xl">
            Six-Digit Lab Report Status Verification
          </h2>
          <p className="mt-1 text-sm text-[#94A3B8]">
            Verify live specimen processing stage using your 6-digit receipt code without exposing patient identifiers or clinical test values.
          </p>
        </div>

        <div className="flex items-center gap-2 font-mono text-xs text-[#2DD4BF]">
          <ShieldCheck className="h-4 w-4" />
          <span>POST /api/v1/lab-orders/verify-status</span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left 7 Columns: 6-Digit Verification Form & Live Status Result */}
        <div className="lg:col-span-7 space-y-5">
          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-6">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void handleVerifyCode();
              }}
              className="flex flex-col gap-3 sm:flex-row sm:items-end"
            >
              <div className="flex-1">
                <label
                  htmlFor="lab-verification-code-input"
                  className="block text-xs font-semibold uppercase tracking-wider text-[#94A3B8]"
                >
                  Enter 6-Digit Verification Code (Leading Zeros Preserved)
                </label>
                <div className="relative mt-2">
                  <KeyRound className="pointer-events-none absolute left-3.5 top-3 h-4 w-4 text-[#2DD4BF]" />
                  <input
                    id="lab-verification-code-input"
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    value={codeInput}
                    onChange={(e) => setCodeInput(e.target.value)}
                    placeholder="048271"
                    className="w-full rounded-xl border border-[#334155] bg-[#0B1020] pl-10 pr-4 py-2.5 font-mono text-base font-bold tracking-[0.25em] text-[#E5EDF7] placeholder-[#94A3B8]/40 focus:border-[#2DD4BF] focus:outline-none tabular-nums"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={isVerifying}
                className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-xl bg-[#2DD4BF] px-6 text-xs font-semibold text-[#0B1020] transition-colors hover:bg-[#2DD4BF]/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#38BDF8] disabled:opacity-50"
              >
                <Search className="h-4 w-4" />
                <span>{isVerifying ? 'Verifying...' : 'Verify Status'}</span>
              </button>
            </form>

            {/* Quick Sample Codes Bar */}
            <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[#334155]/70 pt-3.5 text-xs">
              <span className="font-mono text-[11px] text-[#94A3B8]">Seeded Codes:</span>
              {[
                { code: '048271', label: '048271 (Troponin • PROCESSING)' },
                { code: '384920', label: '384920 (Electrolytes • COMPLETED)' },
                { code: '729104', label: '729104 (HbA1c • REGISTERED)' },
                { code: '019482', label: '019482 (CBC • SAMPLE_COLLECTED)' },
                { code: '905318', label: '905318 (Synovial • CANCELLED)' },
              ].map((item) => (
                <button
                  key={item.code}
                  type="button"
                  onClick={() => void handleVerifyCode(item.code)}
                  className={`rounded-lg border px-2.5 py-1 font-mono text-[11px] transition-colors tabular-nums ${
                    codeInput === item.code
                      ? 'border-[#2DD4BF] bg-[#2DD4BF]/15 text-[#2DD4BF]'
                      : 'border-[#334155] bg-[#0B1020] text-[#94A3B8] hover:border-[#38BDF8] hover:text-[#E5EDF7]'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>

            {verifyError && (
              <div className="mt-5 flex items-start gap-3 rounded-xl border border-rose-500/40 bg-rose-500/10 p-4 text-xs text-rose-200">
                <AlertCircle className="h-4 w-4 shrink-0 text-rose-400 mt-0.5" />
                <div>
                  <span className="font-mono font-semibold text-rose-300">
                    {verifyError.code}
                  </span>
                  <p className="mt-1">{verifyError.message}</p>
                </div>
              </div>
            )}

            {verifyResult && (
              <div className="mt-5 rounded-xl border border-[#334155] bg-[#0B1020] p-5 space-y-4">
                <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#334155] pb-3.5">
                  <div>
                    <span className="font-mono text-[11px] text-[#94A3B8]">
                      DIAGNOSTIC TEST PANEL
                    </span>
                    <h3 className="mt-0.5 font-display text-lg font-bold text-[#E5EDF7]">
                      {verifyResult.test_name}
                    </h3>
                  </div>

                  <span
                    className={`rounded-lg px-3 py-1 font-mono text-xs font-bold ${
                      verifyResult.lab_status === 'COMPLETED'
                        ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                        : verifyResult.lab_status === 'CANCELLED'
                        ? 'bg-rose-500/15 text-rose-300 border border-rose-500/30'
                        : 'bg-[#38BDF8]/15 text-[#38BDF8] border border-[#38BDF8]/30'
                    }`}
                  >
                    {verifyResult.lab_status}
                  </span>
                </div>

                {/* 4-Stage Visual Progress Bar */}
                {verifyResult.lab_status !== 'CANCELLED' && (
                  <div className="grid grid-cols-4 gap-2 pt-1">
                    {LAB_STAGES.map((stage, idx) => {
                      const reached = idx <= currentStageIndex;
                      return (
                        <div key={stage} className="space-y-1.5">
                          <div
                            className={`h-1.5 rounded-full transition-colors ${
                              reached ? 'bg-[#2DD4BF]' : 'bg-[#334155]'
                            }`}
                          />
                          <span
                            className={`block font-mono text-[10px] ${
                              reached ? 'text-[#2DD4BF] font-semibold' : 'text-[#94A3B8]'
                            }`}
                          >
                            {stage.replace('_', ' ')}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 text-xs">
                  <div className="rounded-lg border border-[#334155]/80 bg-[#111B2E] p-3.5">
                    <span className="font-mono text-[10px] font-semibold uppercase text-[#2DD4BF]">
                      Status Explanation
                    </span>
                    <p className="mt-1 text-[#E5EDF7] leading-relaxed">
                      {verifyResult.status_explanation}
                    </p>
                  </div>
                  <div className="rounded-lg border border-[#334155]/80 bg-[#111B2E] p-3.5">
                    <span className="font-mono text-[10px] font-semibold uppercase text-[#38BDF8]">
                      Recommended Next Step
                    </span>
                    <p className="mt-1 text-[#E5EDF7] leading-relaxed">
                      {verifyResult.next_step}
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[#334155]/70 pt-3 font-mono text-[11px] text-[#94A3B8] tabular-nums">
                  <span className="flex items-center gap-1.5">
                    <Clock className="h-3.5 w-3.5 text-[#38BDF8]" />
                    Updated: {new Date(verifyResult.last_updated_at).toLocaleString()}
                  </span>
                  <span className="flex items-center gap-1 text-emerald-300">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Zero PII / Clinical Results Exposed
                  </span>
                </div>

                <p className="text-[11px] text-[#94A3B8] italic">{verifyResult.disclaimer}</p>
              </div>
            )}
          </div>
        </div>

        {/* Right 5 Columns: Synthetic Demo Patient Portal Receipt Lookup */}
        <div className="lg:col-span-5">
          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-[#334155] pb-3">
              <div>
                <h3 className="font-display text-base font-bold text-[#E5EDF7]">
                  Synthetic Patient Lab Receipt Lookup
                </h3>
                <p className="text-xs text-[#94A3B8]">
                  Retrieve active 6-digit verification codes issued to synthetic patients (`GET /api/v1/lab-orders/demo/patient-portal/{'{patient_ref}'}`)
                </p>
              </div>
              <FlaskConical className="h-5 w-5 text-[#38BDF8] shrink-0" />
            </div>

            <div className="flex flex-wrap gap-1.5">
              {DEMO_PATIENTS.map((pat) => (
                <button
                  key={pat}
                  type="button"
                  onClick={() => setActivePatientRef(pat)}
                  className={`rounded-lg border px-2.5 py-1 font-mono text-xs transition-colors ${
                    activePatientRef === pat
                      ? 'border-[#38BDF8] bg-[#38BDF8]/15 text-[#38BDF8] font-semibold'
                      : 'border-[#334155] bg-[#0B1020] text-[#94A3B8] hover:text-[#E5EDF7]'
                  }`}
                >
                  {pat}
                </button>
              ))}
            </div>

            {loadingReceipts ? (
              <div className="h-28 animate-pulse rounded-lg border border-[#334155] bg-[#0B1020]" />
            ) : demoReceipts.length === 0 ? (
              <div className="rounded-lg border border-[#334155] bg-[#0B1020] p-4 text-xs text-[#94A3B8]">
                No lab order receipts found for synthetic patient {activePatientRef}.
              </div>
            ) : (
              <div className="space-y-2.5">
                {demoReceipts.map((rec) => (
                  <div
                    key={rec.verification_code}
                    className="flex flex-col justify-between gap-3 rounded-lg border border-[#334155] bg-[#0B1020] p-3.5 sm:flex-row sm:items-center"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-display text-xs font-bold text-[#E5EDF7]">
                          {rec.test_name}
                        </span>
                        <span className="rounded bg-[#111B2E] px-2 py-0.5 font-mono text-[10px] text-[#38BDF8] border border-[#334155]">
                          {rec.lab_status}
                        </span>
                      </div>
                      <p className="mt-1 font-mono text-xs text-[#2DD4BF] tabular-nums">
                        Verification Code: <strong>{rec.verification_code}</strong>
                      </p>
                    </div>

                    <button
                      type="button"
                      onClick={() => void handleVerifyCode(rec.verification_code)}
                      className="shrink-0 rounded-lg border border-[#2DD4BF]/50 bg-[#2DD4BF]/10 px-3 py-1.5 text-xs font-semibold text-[#2DD4BF] hover:bg-[#2DD4BF]/20"
                    >
                      Verify This Code
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
};
