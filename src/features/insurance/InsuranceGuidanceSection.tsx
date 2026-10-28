import React, { useState } from 'react';
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  FileQuestion,
  PhoneCall,
  Search,
  Send,
  ShieldCheck,
  Ticket,
} from 'lucide-react';
import { usePlatform } from '../../context/PlatformContext';
import { ApiError, medivoiceApi } from '../../services/api';
import {
  InsuranceProviderRead,
  InsuranceSupportTicketRead,
} from '../../types/api';

export const InsuranceGuidanceSection: React.FC = () => {
  const {
    insuranceProviders,
    insuranceContact,
    supportTickets,
    activePatientRef,
    refreshOperationalData,
  } = usePlatform();

  const [searchQuery, setSearchQuery] = useState<string>('');
  const [cashlessFilter, setCashlessFilter] = useState<'ALL' | 'CASHLESS' | 'REIMBURSEMENT'>('ALL');
  const [filteredProviders, setFilteredProviders] = useState<InsuranceProviderRead[] | null>(
    null
  );
  const [isSearching, setIsSearching] = useState<boolean>(false);

  // Human-Support Escalation Ticket Form State
  const [selectedProviderName, setSelectedProviderName] = useState<string>(
    'Aarogya Shield Health Insurance'
  );
  const [selectedPlanName, setSelectedPlanName] = useState<string>(
    'Aarogya Shield Gold Cashless Plus'
  );
  const [questionText, setQuestionText] = useState<string>('');
  const [contactPreference, setContactPreference] = useState<string>(
    'Ground Floor Insurance Desk Counter 3 / Phone Callback'
  );
  const [isSubmittingTicket, setIsSubmittingTicket] = useState<boolean>(false);
  const [createdTicket, setCreatedTicket] = useState<InsuranceSupportTicketRead | null>(null);
  const [ticketError, setTicketError] = useState<string | null>(null);

  const handleRunInsuranceSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setIsSearching(true);
    try {
      const cashlessParam =
        cashlessFilter === 'CASHLESS'
          ? true
          : cashlessFilter === 'REIMBURSEMENT'
          ? false
          : undefined;
      const res = await medivoiceApi.searchInsurance({
        q: searchQuery.trim() || undefined,
        cashless: cashlessParam,
      });
      setFilteredProviders(res.providers);
    } catch {
      setFilteredProviders(null);
    } finally {
      setIsSearching(false);
    }
  };

  const handleResetFilters = () => {
    setSearchQuery('');
    setCashlessFilter('ALL');
    setFilteredProviders(null);
  };

  const handleCreateSupportTicket = async (e: React.FormEvent) => {
    e.preventDefault();
    setTicketError(null);
    setCreatedTicket(null);

    if (questionText.trim().length < 5) {
      setTicketError(
        'Please describe your policy or pre-authorization question (at least 5 characters).'
      );
      return;
    }

    setIsSubmittingTicket(true);
    try {
      const ticket = await medivoiceApi.createInsuranceSupportTicket({
        patient_reference: activePatientRef.trim() || 'PAT-2026-4409',
        provider_name: selectedProviderName.trim() || null,
        plan_name: selectedPlanName.trim() || null,
        question: questionText.trim(),
        contact_preference: contactPreference.trim() || null,
      });
      setCreatedTicket(ticket);
      setQuestionText('');
      await refreshOperationalData();
    } catch (err) {
      setTicketError(
        err instanceof ApiError
          ? err.message
          : 'Failed to submit insurance support ticket. Please try again.'
      );
    } finally {
      setIsSubmittingTicket(false);
    }
  };

  const providersToDisplay = filteredProviders !== null ? filteredProviders : insuranceProviders;

  return (
    <section id="insurance-section" className="space-y-8">
      <div className="flex flex-col justify-between gap-4 border-b border-[#334155] pb-5 sm:flex-row sm:items-end">
        <div>
          <span className="font-mono text-xs font-semibold uppercase tracking-wider text-[#2DD4BF]">
            03 • Document-Grounded Coverage & TPA Escalation
          </span>
          <h2 className="mt-1 font-display text-2xl font-bold text-[#E5EDF7] sm:text-3xl">
            Hospital Insurance Providers & Plan Directory
          </h2>
          <p className="mt-1 text-sm text-[#94A3B8]">
            Synthetic insurance network directory with cashless vs. reimbursement rules, co-pay summaries, and human TPA desk escalation tickets.
          </p>
        </div>

        {insuranceContact && (
          <div className="flex items-center gap-2.5 rounded-xl border border-[#334155] bg-[#111B2E] px-4 py-2.5 text-xs">
            <PhoneCall className="h-4 w-4 text-[#2DD4BF] shrink-0" />
            <div>
              <span className="block font-semibold text-[#E5EDF7]">
                {insuranceContact.department}
              </span>
              <span className="font-mono text-[11px] text-[#38BDF8] tabular-nums">
                {insuranceContact.phone} • {insuranceContact.location}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Mandatory Non-Guarantee Coverage Disclaimer Banner */}
      <div className="flex items-start gap-3 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-xs text-amber-200">
        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
        <div>
          <p className="font-semibold text-amber-300">
            Non-Guarantee Coverage Notice (Synthetic Hospital Data)
          </p>
          <p className="mt-0.5 text-amber-100/90 leading-relaxed">
            {insuranceContact?.disclaimer ||
              'Informational only (Synthetic Demo Data): Listed insurance plan information does not guarantee coverage or claim approval. Final eligibility, co-pay, waiting periods, exclusions, pre-authorization, and cashless settlement depend on your specific policy terms and TPA verification at the Aarogya One Hospital Insurance Desk.'}
          </p>
        </div>
      </div>

      {/* Search & Filter Controls */}
      <form
        onSubmit={(e) => void handleRunInsuranceSearch(e)}
        className="flex flex-wrap items-center gap-3 rounded-xl border border-[#334155] bg-[#111B2E] p-4"
      >
        <div className="relative flex-1 min-w-[240px]">
          <Search className="pointer-events-none absolute left-3.5 top-2.5 h-4 w-4 text-[#94A3B8]" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search provider, plan type (Senior Citizen, Family Floater), or covered service (Cardiology, OPD)..."
            className="w-full rounded-lg border border-[#334155] bg-[#0B1020] pl-10 pr-4 py-2 text-xs text-[#E5EDF7] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none"
          />
        </div>

        <div className="flex items-center gap-1.5">
          {(['ALL', 'CASHLESS', 'REIMBURSEMENT'] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setCashlessFilter(mode)}
              className={`rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                cashlessFilter === mode
                  ? 'bg-[#2DD4BF] text-[#0B1020] font-semibold'
                  : 'border border-[#334155] bg-[#0B1020] text-[#94A3B8] hover:text-[#E5EDF7]'
              }`}
            >
              {mode === 'ALL'
                ? 'All Settlement Modes'
                : mode === 'CASHLESS'
                ? 'Cashless Enabled'
                : 'Reimbursement Only'}
            </button>
          ))}
        </div>

        <button
          type="submit"
          disabled={isSearching}
          className="rounded-lg border border-[#38BDF8]/50 bg-[#38BDF8]/15 px-4 py-2 text-xs font-semibold text-[#38BDF8] hover:bg-[#38BDF8]/25 disabled:opacity-50"
        >
          {isSearching ? 'Searching...' : 'Filter Plans'}
        </button>

        {filteredProviders !== null && (
          <button
            type="button"
            onClick={handleResetFilters}
            className="rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#94A3B8] hover:text-[#E5EDF7]"
          >
            Reset
          </button>
        )}
      </form>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left 7 Columns: Active Insurance Providers & Plans */}
        <div className="lg:col-span-7 space-y-4">
          {providersToDisplay.length === 0 ? (
            <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-6 text-xs text-[#94A3B8]">
              No active synthetic insurance plans matched your filter. Use the Human Support Escalation Desk on the right to submit a policy inquiry ticket to our TPA team.
            </div>
          ) : (
            providersToDisplay.map((prov) => (
              <div
                key={prov.id}
                className="rounded-xl border border-[#334155] bg-[#111B2E] p-5 space-y-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-2 border-b border-[#334155] pb-3.5">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#334155] bg-[#0B1020] text-[#2DD4BF]">
                      <Building2 className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-display text-base font-bold text-[#E5EDF7]">
                          {prov.name}
                        </h3>
                        <span className="rounded bg-[#0B1020] px-2 py-0.5 font-mono text-[10px] text-[#38BDF8] border border-[#334155]">
                          {prov.code}
                        </span>
                      </div>
                      <p className="mt-0.5 font-mono text-xs text-[#94A3B8] tabular-nums">
                        TPA Helpline: {prov.support_contact}
                      </p>
                    </div>
                  </div>
                  <span className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 font-mono text-[10px] font-semibold text-emerald-300">
                    ACTIVE NETWORK
                  </span>
                </div>

                <div className="space-y-3">
                  {prov.plans.map((plan) => (
                    <div
                      key={plan.id}
                      className="rounded-xl border border-[#334155] bg-[#0B1020] p-4 space-y-2.5"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <h4 className="font-display text-sm font-bold text-[#E5EDF7]">
                            {plan.plan_name}
                          </h4>
                          <span className="text-xs font-medium text-[#2DD4BF]">
                            {plan.plan_type}
                          </span>
                        </div>

                        <div className="flex flex-wrap items-center gap-1.5 font-mono text-[10px]">
                          <span
                            className={`rounded px-2 py-0.5 font-semibold ${
                              plan.cashless_available
                                ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                                : 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                            }`}
                          >
                            {plan.cashless_available ? 'CASHLESS AVAILABLE' : 'REIMBURSEMENT ONLY'}
                          </span>
                          {plan.preauthorization_required && (
                            <span className="rounded border border-[#38BDF8]/30 bg-[#38BDF8]/15 px-2 py-0.5 text-[#38BDF8]">
                              PRE-AUTH REQUIRED
                            </span>
                          )}
                        </div>
                      </div>

                      <p className="text-xs text-[#E5EDF7]/90 leading-relaxed">
                        {plan.coverage_summary}
                      </p>

                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 pt-1 text-xs">
                        <div className="rounded border border-[#334155]/80 bg-[#111B2E] p-2.5">
                          <span className="block font-mono text-[10px] uppercase text-[#94A3B8]">
                            Co-Pay & Deductible Rules
                          </span>
                          <span className="mt-0.5 block text-[#E5EDF7]">{plan.copay_summary}</span>
                        </div>
                        <div className="rounded border border-[#334155]/80 bg-[#111B2E] p-2.5">
                          <span className="block font-mono text-[10px] uppercase text-[#94A3B8]">
                            Hospital Network Notes
                          </span>
                          <span className="mt-0.5 block text-[#E5EDF7]">
                            {plan.network_notes || 'Verify policy card at Ground Floor TPA Desk.'}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center justify-between pt-1">
                        <span className="font-mono text-[11px] text-[#94A3B8] truncate max-w-[70%]">
                          Services: {plan.covered_services}
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedProviderName(prov.name);
                            setSelectedPlanName(plan.plan_name);
                          }}
                          className="text-xs font-semibold text-[#38BDF8] hover:underline"
                        >
                          Ask TPA Desk about this plan →
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Right 5 Columns: Unanswered Policy Question Escalation Ticket Workflow */}
        <div className="lg:col-span-5 space-y-5">
          <form
            onSubmit={(e) => void handleCreateSupportTicket(e)}
            className="rounded-xl border border-[#334155] bg-[#111B2E] p-5 space-y-4"
          >
            <div className="flex items-start justify-between gap-3 border-b border-[#334155] pb-3.5">
              <div>
                <div className="flex items-center gap-2">
                  <FileQuestion className="h-4 w-4 text-[#38BDF8]" />
                  <h3 className="font-display text-base font-bold text-[#E5EDF7]">
                    Human TPA Support Ticket Escalation
                  </h3>
                </div>
                <p className="mt-1 text-xs text-[#94A3B8]">
                  If your policy-specific question (waiting periods, room rent sub-limits, unlisted insurer, or custom surgical package) cannot be answered from the synthetic brief documents, generate a persisted TPA helpdesk ticket (`POST /api/v1/insurance/support-tickets`).
                </p>
              </div>
            </div>

            {ticketError && (
              <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-200">
                {ticketError}
              </div>
            )}

            {createdTicket && (
              <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-4 text-xs text-emerald-200 space-y-1.5">
                <div className="flex items-center gap-2 font-semibold text-emerald-300">
                  <CheckCircle2 className="h-4 w-4" />
                  <span>TPA Support Ticket Persisted in Backend</span>
                </div>
                <p className="font-mono text-[11px] tabular-nums">
                  Ticket ID: <strong>{createdTicket.ticket_id}</strong> • Status:{' '}
                  <strong>{createdTicket.status}</strong>
                </p>
                <p className="text-[11px] text-emerald-100/90">
                  Assigned to: {createdTicket.assigned_department}
                </p>
              </div>
            )}

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="ticket-provider-input"
                  className="block text-xs font-medium text-[#E5EDF7]"
                >
                  Insurance Provider
                </label>
                <input
                  id="ticket-provider-input"
                  type="text"
                  value={selectedProviderName}
                  onChange={(e) => setSelectedProviderName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                />
              </div>
              <div>
                <label
                  htmlFor="ticket-plan-input"
                  className="block text-xs font-medium text-[#E5EDF7]"
                >
                  Plan Name (or Unlisted)
                </label>
                <input
                  id="ticket-plan-input"
                  type="text"
                  value={selectedPlanName}
                  onChange={(e) => setSelectedPlanName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="ticket-question-input"
                className="block text-xs font-medium text-[#E5EDF7]"
              >
                Policy-Specific Question Requiring Human Verification
              </label>
              <textarea
                id="ticket-question-input"
                rows={3}
                value={questionText}
                onChange={(e) => setQuestionText(e.target.value)}
                placeholder="e.g., Does my corporate continuity rider waive the 24-month waiting period for knee arthroscopy?"
                className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] p-3 text-xs text-[#E5EDF7] placeholder-[#94A3B8]/50 focus:border-[#2DD4BF] focus:outline-none"
              />
            </div>

            <div>
              <label
                htmlFor="ticket-contact-pref"
                className="block text-xs font-medium text-[#E5EDF7]"
              >
                Preferred TPA Desk Follow-Up Channel
              </label>
              <input
                id="ticket-contact-pref"
                type="text"
                value={contactPreference}
                onChange={(e) => setContactPreference(e.target.value)}
                className="mt-1 w-full rounded-lg border border-[#334155] bg-[#0B1020] px-3 py-2 text-xs text-[#E5EDF7] focus:border-[#2DD4BF] focus:outline-none"
              />
            </div>

            <button
              type="submit"
              disabled={isSubmittingTicket}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-[#2DD4BF] px-4 py-2.5 text-xs font-semibold text-[#0B1020] transition-colors hover:bg-[#2DD4BF]/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#38BDF8] disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
              <span>
                {isSubmittingTicket
                  ? 'Creating Support Ticket...'
                  : 'Submit Human-Support Ticket to TPA Desk'}
              </span>
            </button>
          </form>

          {/* Persisted Support Tickets List */}
          <div className="rounded-xl border border-[#334155] bg-[#111B2E] p-5">
            <div className="flex items-center justify-between border-b border-[#334155] pb-3">
              <div className="flex items-center gap-2">
                <Ticket className="h-4 w-4 text-[#2DD4BF]" />
                <h3 className="font-display text-sm font-bold text-[#E5EDF7]">
                  Recent TPA Support Tickets
                </h3>
              </div>
              <span className="font-mono text-xs text-[#94A3B8] tabular-nums">
                {supportTickets.length} open
              </span>
            </div>

            <div className="mt-3 max-h-56 overflow-y-auto space-y-2.5 pr-1">
              {supportTickets.length === 0 ? (
                <p className="py-4 text-center text-xs text-[#94A3B8]">
                  No insurance escalation tickets submitted yet.
                </p>
              ) : (
                supportTickets.slice(0, 6).map((t) => (
                  <div
                    key={t.ticket_id}
                    className="rounded-lg border border-[#334155] bg-[#0B1020] p-3 text-xs space-y-1"
                  >
                    <div className="flex items-center justify-between font-mono text-[11px] tabular-nums">
                      <span className="text-[#38BDF8]">
                        Ticket #{t.ticket_id.slice(0, 8)} • {t.patient_reference}
                      </span>
                      <span className="rounded bg-[#2DD4BF]/15 px-1.5 py-0.5 text-[10px] font-semibold text-[#2DD4BF]">
                        {t.status}
                      </span>
                    </div>
                    <p className="text-[#E5EDF7] line-clamp-2 whitespace-pre-line">
                      {t.question}
                    </p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
