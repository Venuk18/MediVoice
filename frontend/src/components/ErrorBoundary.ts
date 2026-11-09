import React, { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw, Home, ShieldAlert, ArrowLeft } from 'lucide-react';
import { logSanitizedError, sanitizeErrorMessage } from './errorSanitizer.ts';

export interface ErrorBoundaryProps {
  children: ReactNode;
  boundaryName?: string;
  level?: 'app' | 'workspace' | 'widget';
  fallbackTitle?: string;
  fallbackMessage?: string;
  onReset?: () => void;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  fallback?: ReactNode | ((props: { error: Error; reset: () => void }) => ReactNode);
}

export interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorId: string | null;
}

/**
 * Production-grade React Error Boundary component with sanitized error logging,
 * controlled healthcare fallback UIs, and non-destructive recovery actions.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorId: null,
    };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    const errorId = `ERR-${Math.random().toString(36).substring(2, 8).toUpperCase()}`;
    return {
      hasError: true,
      error,
      errorId,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    const boundaryName = this.props.boundaryName || 'Component';
    logSanitizedError(error, errorInfo, boundaryName);

    if (this.props.onError) {
      try {
        this.props.onError(error, errorInfo);
      } catch (handlerErr) {
        console.warn('[MediVoice ErrorBoundary] Error in custom onError handler:', handlerErr);
      }
    }
  }

  resetErrorBoundary = (): void => {
    if (this.props.onReset) {
      try {
        this.props.onReset();
      } catch (resetErr) {
        console.warn('[MediVoice ErrorBoundary] Error in custom onReset handler:', resetErr);
      }
    }
    this.setState({
      hasError: false,
      error: null,
      errorId: null,
    });
  };

  render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }

    const {
      fallback,
      level = 'workspace',
      fallbackTitle,
      fallbackMessage,
      boundaryName = 'Workspace',
    } = this.props;

    const { error, errorId } = this.state;

    // Support custom fallback function or node if provided
    if (typeof fallback === 'function' && error) {
      return fallback({ error, reset: this.resetErrorBoundary });
    }
    if (fallback && typeof fallback !== 'function') {
      return fallback;
    }

    // Default Widget Level Fallback (e.g. Chat or Voice Panel)
    if (level === 'widget') {
      return React.createElement(
        'div',
        {
          role: 'alert',
          'aria-live': 'polite',
          className:
            'rounded-2xl border border-amber-200 bg-amber-50/80 p-5 text-amber-950 shadow-sm backdrop-blur-sm',
        },
        React.createElement(
          'div',
          { className: 'flex items-start gap-3.5' },
          React.createElement(
            'div',
            { className: 'rounded-xl bg-amber-100 p-2 text-amber-700 shrink-0' },
            React.createElement(AlertTriangle, { className: 'h-5 w-5' })
          ),
          React.createElement(
            'div',
            { className: 'space-y-1 flex-1' },
            React.createElement(
              'h4',
              { className: 'font-semibold text-sm text-amber-900' },
              fallbackTitle || `${boundaryName} Temporarily Unavailable`
            ),
            React.createElement(
              'p',
              { className: 'text-xs text-amber-800 leading-relaxed' },
              fallbackMessage ||
                'The interactive component encountered an unexpected error. Your conversation data and session are safe.'
            ),
            errorId
              ? React.createElement(
                  'p',
                  { className: 'font-mono text-[10px] text-amber-600/80 pt-1' },
                  `Incident Reference: ${errorId}`
                )
              : null
          )
        ),
        React.createElement(
          'div',
          { className: 'mt-4 flex items-center justify-end gap-2.5' },
          React.createElement(
            'button',
            {
              type: 'button',
              onClick: this.resetErrorBoundary,
              className:
                'inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-amber-700 active:bg-amber-800 transition',
            },
            React.createElement(RefreshCw, { className: 'h-3.5 w-3.5' }),
            'Restart Component'
          )
        )
      );
    }

    // Default Application Level Fallback (Full Page)
    if (level === 'app') {
      return React.createElement(
        'div',
        {
          role: 'alert',
          className:
            'min-h-screen bg-[#0B1020] text-slate-100 flex flex-col justify-center items-center p-6 selection:bg-rose-500 selection:text-white',
        },
        React.createElement(
          'div',
          {
            className:
              'w-full max-w-lg rounded-3xl border border-rose-500/20 bg-[#121933] p-8 shadow-2xl space-y-6',
          },
          React.createElement(
            'div',
            { className: 'flex items-center gap-3' },
            React.createElement(
              'div',
              {
                className:
                  'rounded-2xl bg-rose-500/10 border border-rose-500/30 p-3 text-rose-400',
              },
              React.createElement(ShieldAlert, { className: 'h-8 w-8' })
            ),
            React.createElement(
              'div',
              null,
              React.createElement(
                'span',
                {
                  className:
                    'font-mono text-[11px] font-semibold text-rose-400 uppercase tracking-wider',
                },
                'MediVoice AI · System Recovery'
              ),
              React.createElement(
                'h1',
                { className: 'text-xl font-bold text-white' },
                fallbackTitle || 'Application Interface Error'
              )
            )
          ),
          React.createElement(
            'div',
            { className: 'space-y-2 text-sm text-slate-300 leading-relaxed' },
            React.createElement(
              'p',
              null,
              fallbackMessage ||
                'An unexpected system error occurred while rendering the application. Hospital operational data, appointment slots, and staff sessions remain intact.'
            ),
            React.createElement(
              'p',
              { className: 'text-xs text-slate-400' },
              'You can try reloading the application or clearing cached interface components without losing stored appointments.'
            )
          ),
          errorId
            ? React.createElement(
                'div',
                {
                  className:
                    'rounded-xl border border-slate-700/60 bg-[#0B1020] px-3.5 py-2 font-mono text-[11px] text-slate-400 flex items-center justify-between',
                },
                React.createElement('span', null, 'Incident Reference:'),
                React.createElement('span', { className: 'text-slate-200 font-bold' }, errorId)
              )
            : null,
          React.createElement(
            'div',
            { className: 'flex flex-col sm:flex-row gap-3 pt-2' },
            React.createElement(
              'button',
              {
                type: 'button',
                onClick: this.resetErrorBoundary,
                className:
                  'flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-violet-600/30 hover:bg-violet-500 active:bg-violet-700 transition',
              },
              React.createElement(RefreshCw, { className: 'h-4 w-4' }),
              'Reload Application'
            ),
            React.createElement(
              'button',
              {
                type: 'button',
                onClick: () => {
                  window.location.href = '/';
                },
                className:
                  'inline-flex items-center justify-center gap-2 rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-2.5 text-sm font-semibold text-slate-200 hover:bg-slate-700 transition',
              },
              React.createElement(Home, { className: 'h-4 w-4' }),
              'Patient Home'
            )
          )
        )
      );
    }

    // Default Workspace Level Fallback (Contained within Shell)
    return React.createElement(
      'div',
      {
        role: 'alert',
        'aria-live': 'polite',
        className: 'mx-auto my-12 max-w-2xl px-4 sm:px-6',
      },
      React.createElement(
        'div',
        { className: 'rounded-3xl border border-slate-200 bg-white p-8 shadow-sm space-y-6' },
        React.createElement(
          'div',
          { className: 'flex items-start gap-4' },
          React.createElement(
            'div',
            {
              className:
                'rounded-2xl bg-amber-50 border border-amber-200 p-3 text-amber-600 shrink-0',
            },
            React.createElement(AlertTriangle, { className: 'h-7 w-7' })
          ),
          React.createElement(
            'div',
            { className: 'space-y-1.5 flex-1' },
            React.createElement(
              'span',
              {
                className:
                  'font-mono text-[11px] font-bold uppercase tracking-wider text-amber-700',
              },
              `${boundaryName} Resilience Shield`
            ),
            React.createElement(
              'h2',
              { className: 'text-lg font-bold text-slate-900' },
              fallbackTitle || `${boundaryName} Temporarily Unavailable`
            ),
            React.createElement(
              'p',
              { className: 'text-sm text-slate-600 leading-relaxed' },
              fallbackMessage ||
                'An unexpected issue occurred in this workspace. Other hospital portals and active patient records remain unaffected.'
            )
          )
        ),
        React.createElement(
          'div',
          {
            className:
              'rounded-2xl bg-slate-50 border border-slate-100 p-4 text-xs text-slate-600 space-y-1.5',
          },
          React.createElement(
            'div',
            { className: 'font-semibold text-slate-700' },
            'Data & Session Preservation:'
          ),
          React.createElement(
            'ul',
            { className: 'list-disc list-inside space-y-0.5 text-slate-500' },
            React.createElement(
              'li',
              null,
              'Active bookings and verified patient references are preserved.'
            ),
            React.createElement(
              'li',
              null,
              'Staff authentication tokens remain valid in your browser.'
            ),
            React.createElement(
              'li',
              null,
              'Network telemetry and error diagnostics have been safely recorded.'
            )
          )
        ),
        errorId
          ? React.createElement(
              'div',
              {
                className:
                  'flex items-center justify-between text-[11px] font-mono text-slate-400 px-1',
              },
              React.createElement('span', null, 'Diagnostic Reference:'),
              React.createElement('span', { className: 'font-semibold text-slate-600' }, errorId)
            )
          : null,
        React.createElement(
          'div',
          { className: 'flex flex-col sm:flex-row items-center justify-end gap-3 pt-2' },
          React.createElement(
            'button',
            {
              type: 'button',
              onClick: () => {
                window.location.href = '/';
              },
              className:
                'w-full sm:w-auto inline-flex items-center justify-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition',
            },
            React.createElement(ArrowLeft, { className: 'h-3.5 w-3.5' }),
            'Return to Patient Portal'
          ),
          React.createElement(
            'button',
            {
              type: 'button',
              onClick: this.resetErrorBoundary,
              className:
                'w-full sm:w-auto inline-flex items-center justify-center gap-2 rounded-xl bg-violet-600 px-5 py-2 text-xs font-semibold text-white shadow-sm hover:bg-violet-700 active:bg-violet-800 transition',
            },
            React.createElement(RefreshCw, { className: 'h-3.5 w-3.5' }),
            'Retry Workspace'
          )
        )
      )
    );
  }
}
