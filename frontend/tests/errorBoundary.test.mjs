import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToString } from 'react-dom/server';

import {
  ErrorBoundary,
} from '../src/components/ErrorBoundary.ts';
import {
  sanitizeErrorMessage,
  sanitizeComponentStack,
  logSanitizedError,
} from '../src/components/errorSanitizer.ts';

// Helper component that throws on render
function BrokenComponent({ errorMessage = 'Simulated crash' }) {
  throw new Error(errorMessage);
}

// Helper component that renders healthy content
function HealthyComponent({ text = 'Healthy workspace content' }) {
  return React.createElement('div', { id: 'healthy' }, text);
}

test('Sanitizer: redacts 10-digit Indian mobile numbers and +91 prefixes', () => {
  const input = 'Patient phone: 9876543210 or +91 9123456789 reported issue';
  const sanitized = sanitizeErrorMessage(input);
  assert.equal(sanitized.includes('9876543210'), false);
  assert.equal(sanitized.includes('9123456789'), false);
  assert.equal(sanitized.includes('[REDACTED_PHONE]'), true);
});

test('Sanitizer: redacts Bearer and JWT authentication tokens', () => {
  const input = 'Request failed with header: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret and token=abc123xyz';
  const sanitized = sanitizeErrorMessage(input);
  assert.equal(sanitized.includes('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9'), false);
  assert.equal(sanitized.includes('abc123xyz'), false);
  assert.equal(sanitized.includes('Bearer [REDACTED_TOKEN]'), true);
  assert.equal(sanitized.includes('token=[REDACTED_TOKEN]'), true);
});

test('Sanitizer: redacts patient references and email addresses', () => {
  const input = 'Patient ref PAT-20261108-001 with email kavitha.reddy@aarogyaone.org failed to load';
  const sanitized = sanitizeErrorMessage(input);
  assert.equal(sanitized.includes('PAT-20261108-001'), false);
  assert.equal(sanitized.includes('kavitha.reddy@aarogyaone.org'), false);
  assert.equal(sanitized.includes('PAT-[REDACTED]'), true);
  assert.equal(sanitized.includes('[REDACTED_EMAIL]'), true);
});

test('Sanitizer: redacts passwords, api keys, and secrets', () => {
  const input = 'Connection failed: password=SuperSecretPassword123, apikey=gnani_secret_key_8831';
  const sanitized = sanitizeErrorMessage(input);
  assert.equal(sanitized.includes('SuperSecretPassword123'), false);
  assert.equal(sanitized.includes('gnani_secret_key_8831'), false);
  assert.equal(sanitized.includes('password=[REDACTED]'), true);
  assert.equal(sanitized.includes('apikey=[REDACTED]'), true);
});

test('Sanitizer: safely handles empty, null, or undefined strings', () => {
  assert.equal(sanitizeErrorMessage(''), '');
  assert.equal(sanitizeErrorMessage(null), '');
  assert.equal(sanitizeErrorMessage(undefined), '');
  assert.equal(sanitizeComponentStack(null), '');
});

test('ErrorBoundary: renders children normally when no error occurs', () => {
  const html = renderToString(
    React.createElement(
      ErrorBoundary,
      { boundaryName: 'TestBoundary' },
      React.createElement(HealthyComponent, { text: 'Everything operational' })
    )
  );
  assert.equal(html.includes('Everything operational'), true);
  assert.equal(html.includes('alert'), false);
});

test('ErrorBoundary: getDerivedStateFromError captures error and assigns safe errorId', () => {
  const sampleError = new Error('Database connection failed');
  const state = ErrorBoundary.getDerivedStateFromError(sampleError);
  assert.equal(state.hasError, true);
  assert.equal(state.error, sampleError);
  assert.equal(typeof state.errorId, 'string');
  assert.equal(state.errorId.startsWith('ERR-'), true);
});

test('ErrorBoundary: resetErrorBoundary clears error state and triggers onReset callback', () => {
  let onResetCalled = false;
  const boundary = new ErrorBoundary({
    children: null,
    onReset: () => {
      onResetCalled = true;
    },
  });

  boundary.state = {
    hasError: true,
    error: new Error('Fatal rendering crash'),
    errorId: 'ERR-TEST1234',
  };

  boundary.setState = (newState) => {
    Object.assign(boundary.state, typeof newState === 'function' ? newState(boundary.state) : newState);
  };

  boundary.resetErrorBoundary();
  assert.equal(onResetCalled, true);
  assert.equal(boundary.state.hasError, false);
  assert.equal(boundary.state.error, null);
  assert.equal(boundary.state.errorId, null);
});

test('ErrorBoundary: logSanitizedError logs scrubbed error without exposing raw patient data', () => {
  const originalConsoleError = console.error;
  let loggedOutput = null;

  console.error = (tag, data) => {
    loggedOutput = { tag, data };
  };

  try {
    const errorWithPII = new Error('Failed to render patient with phone 9876543210 and Bearer secret_jwt_token_123');
    logSanitizedError(errorWithPII, { componentStack: 'in PatientView (at PatientWebsiteView.tsx:45)' }, 'PatientWorkspace');

    assert.notEqual(loggedOutput, null);
    assert.equal(loggedOutput.tag.includes('[MediVoice PatientWorkspace]'), true);
    assert.equal(loggedOutput.data.message.includes('9876543210'), false);
    assert.equal(loggedOutput.data.message.includes('secret_jwt_token_123'), false);
    assert.equal(loggedOutput.data.message.includes('[REDACTED_PHONE]'), true);
    assert.equal(loggedOutput.data.message.includes('[REDACTED_TOKEN]'), true);
  } finally {
    console.error = originalConsoleError;
  }
});

test('ErrorBoundary: renders workspace-level fallback with preservation notice and retry CTA', () => {
  const boundary = new ErrorBoundary({
    boundaryName: 'Doctor Clinical Workspace',
    level: 'workspace',
    fallbackTitle: 'Doctor Clinical Workspace Error',
    fallbackMessage: 'Clinical queues preserved safely.',
    children: React.createElement(HealthyComponent),
  });

  boundary.state = {
    hasError: true,
    error: new Error('Unexpected undefined in doctor schedule'),
    errorId: 'ERR-DOC001',
  };

  const html = renderToString(boundary.render());
  assert.equal(html.includes('Doctor Clinical Workspace Error'), true);
  assert.equal(html.includes('Clinical queues preserved safely.'), true);
  assert.equal(html.includes('ERR-DOC001'), true);
  assert.equal(html.includes('Retry Workspace'), true);
  assert.equal(html.includes('Return to Patient Portal'), true);
  // Stack trace must NEVER be rendered to the user
  assert.equal(html.includes('at BrokenComponent'), false);
});

test('ErrorBoundary: renders widget-level fallback for voice assistant without crashing parent', () => {
  const boundary = new ErrorBoundary({
    boundaryName: 'Voice Assistant',
    level: 'widget',
    fallbackTitle: 'Voice Assistant Temporarily Unavailable',
    children: React.createElement(HealthyComponent),
  });

  boundary.state = {
    hasError: true,
    error: new Error('AudioContext failed to start'),
    errorId: 'ERR-VOD002',
  };

  const html = renderToString(boundary.render());
  assert.equal(html.includes('Voice Assistant Temporarily Unavailable'), true);
  assert.equal(html.includes('Restart Component'), true);
  assert.equal(html.includes('ERR-VOD002'), true);
});

test('ErrorBoundary: renders app-level fallback for root failures', () => {
  const boundary = new ErrorBoundary({
    boundaryName: 'Application',
    level: 'app',
    fallbackTitle: 'Application Recovery',
    children: React.createElement(HealthyComponent),
  });

  boundary.state = {
    hasError: true,
    error: new Error('Root provider initialization crash'),
    errorId: 'ERR-APP003',
  };

  const html = renderToString(boundary.render());
  assert.equal(html.includes('Application Recovery'), true);
  assert.equal(html.includes('Reload Application'), true);
  assert.equal(html.includes('Patient Home'), true);
  assert.equal(html.includes('ERR-APP003'), true);
});

test('ErrorBoundary: supports custom fallback renderer function with error and reset props', () => {
  let resetInvoked = false;
  const customFallback = ({ error, reset }) => {
    return React.createElement(
      'div',
      { className: 'custom-card' },
      React.createElement('span', null, `Custom: ${error.message}`),
      React.createElement('button', { onClick: reset }, 'Custom Reset')
    );
  };

  const boundary = new ErrorBoundary({
    children: React.createElement(HealthyComponent),
    fallback: customFallback,
  });

  boundary.state = {
    hasError: true,
    error: new Error('Custom Error Trigger'),
    errorId: 'ERR-CUST01',
  };

  const html = renderToString(boundary.render());
  assert.equal(html.includes('custom-card'), true);
  assert.equal(html.includes('Custom: Custom Error Trigger'), true);
  assert.equal(html.includes('Custom Reset'), true);
});

test('ErrorBoundary: isolated workspace boundaries ensure error in one workspace does not crash sibling', () => {
  // Simulate workspace A in error state and workspace B in healthy state
  const doctorBoundary = new ErrorBoundary({
    boundaryName: 'Doctor Workspace',
    level: 'workspace',
    children: React.createElement(HealthyComponent, { text: 'Doctor Queue' }),
  });
  doctorBoundary.state = {
    hasError: true,
    error: new Error('Doctor view crashed'),
    errorId: 'ERR-DOC99',
  };

  const labBoundary = new ErrorBoundary({
    boundaryName: 'Laboratory Workspace',
    level: 'workspace',
    children: React.createElement(HealthyComponent, { text: 'Lab Verification Queue Active' }),
  });

  const doctorHtml = renderToString(doctorBoundary.render());
  const labHtml = renderToString(labBoundary.render());

  // Doctor workspace has fallback UI
  assert.equal(doctorHtml.includes('Doctor Workspace Temporarily Unavailable'), true);
  assert.equal(doctorHtml.includes('Retry Workspace'), true);

  // Laboratory workspace renders completely healthy without errors
  assert.equal(labHtml.includes('Lab Verification Queue Active'), true);
  assert.equal(labHtml.includes('Temporarily Unavailable'), false);
});
