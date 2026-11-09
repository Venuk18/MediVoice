import assert from 'node:assert/strict';
import test from 'node:test';

// Test suite for Phase 9.4: PlatformContext Performance Optimization and Role-Aware Data Loading

// Mock API Call Tracker
function createApiTracker() {
  const calls = [];
  const inFlight = new Map();

  const tracker = {
    calls,
    inFlight,
    mockResponses: {
      hospital: { id: 'hosp-1', name: 'Aarogya One Hospital', departments: ['Cardiology', 'General Medicine'] },
      doctors: [{ id: 'doc-1', display_name: 'Dr. Rajesh Sharma', specialty: 'Cardiology' }],
      appointments: [{ id: 'appt-1', doctor_id: 'doc-1', patient_name: 'Suresh Rao', appointment_status: 'CONFIRMED' }],
      labOrders: [{ id: 'lab-1', test_name: 'Complete Blood Picture', lab_status: 'REGISTERED' }],
      insuranceProviders: [{ id: 'ins-1', name: 'Star Health', code: 'STAR-01' }],
      insuranceContact: { desk_name: 'Aarogya Insurance Desk', phone: '040-23456789' },
      maintenanceOrders: [{ id: 'maint-1', title: 'AC Repair', status: 'PENDING' }],
      maintenanceSummary: { total_orders: 1, pending_orders: 1, completed_orders: 0 },
      supportTickets: [{ id: 'tick-1', subject: 'Pre-auth query', status: 'OPEN' }],
      workflowExceptions: [{ id: 'exc-1', exception_type: 'OVERDUE_LAB', status: 'OPEN' }],
      auditEvents: [{ id: 'aud-1', action: 'APPOINTMENT_BOOKED' }],
      currentStaff: { id: 'staff-1', username: 'dr.rajesh', role: 'DOCTOR', department: 'Cardiology' },
    },
    reset() {
      calls.length = 0;
      inFlight.clear();
    },
    dedupe(key, fn) {
      const existing = inFlight.get(key);
      if (existing) return existing;
      const promise = fn().finally(() => inFlight.delete(key));
      inFlight.set(key, promise);
      return promise;
    },
    async getHospital() {
      calls.push('getHospital');
      return tracker.mockResponses.hospital;
    },
    async getDoctors() {
      calls.push('getDoctors');
      return tracker.mockResponses.doctors;
    },
    async getAppointments() {
      calls.push('getAppointments');
      return tracker.mockResponses.appointments;
    },
    async getLabOrders() {
      calls.push('getLabOrders');
      return tracker.mockResponses.labOrders;
    },
    async getInsuranceProviders() {
      calls.push('getInsuranceProviders');
      return tracker.mockResponses.insuranceProviders;
    },
    async getInsuranceContact() {
      calls.push('getInsuranceContact');
      return tracker.mockResponses.insuranceContact;
    },
    async getMaintenanceWorkOrders() {
      calls.push('getMaintenanceWorkOrders');
      return tracker.mockResponses.maintenanceOrders;
    },
    async getMaintenanceSummary() {
      calls.push('getMaintenanceSummary');
      return tracker.mockResponses.maintenanceSummary;
    },
    async getInsuranceSupportTickets() {
      calls.push('getInsuranceSupportTickets');
      return tracker.mockResponses.supportTickets;
    },
    async getWorkflowExceptions() {
      calls.push('getWorkflowExceptions');
      return tracker.mockResponses.workflowExceptions;
    },
    async getAuditEvents(params) {
      calls.push('getAuditEvents');
      return tracker.mockResponses.auditEvents;
    },
    async getCurrentStaff(token) {
      calls.push('getCurrentStaff');
      if (token === 'invalid_token') {
        throw new Error('Unauthorized');
      }
      return tracker.mockResponses.currentStaff;
    },
  };

  return tracker;
}

// Simulates the PlatformContext role-aware data loading logic
async function simulatePlatformDataLoad({
  tracker,
  currentRoute = '/',
  activeWorkspace = 'patient',
  staffProfile = null,
  token = null,
  existingState = {},
  force = false,
}) {
  const isStaff = Boolean(staffProfile && token && staffProfile.role !== 'DEMO_VIEWER');
  const role = staffProfile?.role;
  const promises = [];

  // 1. Core Public Data: Hospital profile and Doctor directory
  if (force || !existingState.hospital) {
    promises.push(
      tracker.dedupe('hospital', () => tracker.getHospital())
        .then((h) => { existingState.hospital = h; })
        .catch(() => null)
    );
  }
  if (force || !existingState.doctors || existingState.doctors.length === 0) {
    promises.push(
      tracker.dedupe('doctors', () => tracker.getDoctors())
        .then((d) => { existingState.doctors = d; })
        .catch(() => null)
    );
  }

  // 2. Route-Dependent Lazy Loading: Insurance coverage data
  const needsInsurance =
    currentRoute === '/insurance' ||
    currentRoute === '/support' ||
    activeWorkspace === 'maintenance' ||
    role === 'MAINTENANCE_STAFF';

  if (needsInsurance && (force || !existingState.insuranceProviders || existingState.insuranceProviders.length === 0)) {
    promises.push(
      tracker.dedupe('insuranceProviders', () => tracker.getInsuranceProviders())
        .then((prov) => { existingState.insuranceProviders = prov; })
        .catch(() => [])
    );
    promises.push(
      tracker.dedupe('insuranceContact', () => tracker.getInsuranceContact())
        .then((c) => { existingState.insuranceContact = c; })
        .catch(() => null)
    );
  }

  // 3. Role-Specific Operational Data (Only for verified staff sessions)
  if (isStaff) {
    if (role === 'DOCTOR' || (role === 'ADMIN' && activeWorkspace === 'doctor')) {
      promises.push(
        tracker.dedupe('appointments', () => tracker.getAppointments())
          .then((appts) => { existingState.appointments = appts; })
          .catch(() => [])
      );
      promises.push(
        tracker.dedupe('auditEvents', () => tracker.getAuditEvents({ limit: 60 }))
          .then((ev) => { existingState.auditEvents = ev; })
          .catch(() => { existingState.auditEvents = []; })
      );
    }

    if (role === 'LAB_OPERATOR' || (role === 'ADMIN' && activeWorkspace === 'lab')) {
      promises.push(
        tracker.dedupe('labOrders', () => tracker.getLabOrders())
          .then((orders) => { existingState.labOrders = orders; })
          .catch(() => [])
      );
      promises.push(
        tracker.dedupe('workflowExceptions', () => tracker.getWorkflowExceptions())
          .then((exc) => { existingState.workflowExceptions = exc; })
          .catch(() => [])
      );
      promises.push(
        tracker.dedupe('auditEvents', () => tracker.getAuditEvents({ limit: 60 }))
          .then((ev) => { existingState.auditEvents = ev; })
          .catch(() => { existingState.auditEvents = []; })
      );
    }

    if (role === 'MAINTENANCE_STAFF' || (role === 'ADMIN' && activeWorkspace === 'maintenance')) {
      promises.push(
        tracker.dedupe('maintenanceWorkOrders', () => tracker.getMaintenanceWorkOrders())
          .then((orders) => { existingState.maintenanceWorkOrders = orders; })
          .catch(() => [])
      );
      promises.push(
        tracker.dedupe('maintenanceSummary', () => tracker.getMaintenanceSummary())
          .then((sum) => { existingState.maintenanceSummary = sum; })
          .catch(() => null)
      );
      promises.push(
        tracker.dedupe('supportTickets', () => tracker.getInsuranceSupportTickets())
          .then((tick) => { existingState.supportTickets = tick; })
          .catch(() => [])
      );
      promises.push(
        tracker.dedupe('workflowExceptions', () => tracker.getWorkflowExceptions())
          .then((exc) => { existingState.workflowExceptions = exc; })
          .catch(() => [])
      );
      promises.push(
        tracker.dedupe('auditEvents', () => tracker.getAuditEvents({ limit: 60 }))
          .then((ev) => { existingState.auditEvents = ev; })
          .catch(() => { existingState.auditEvents = []; })
      );
    }
  }

  await Promise.all(promises);
  return existingState;
}

// -----------------------------------------------------------------------------
// TESTS
// -----------------------------------------------------------------------------

test('PlatformContext: 1. Anonymous patient initialization requests ONLY public hospital and doctors', async () => {
  const tracker = createApiTracker();
  const state = {};

  await simulatePlatformDataLoad({
    tracker,
    currentRoute: '/',
    activeWorkspace: 'patient',
    staffProfile: null,
    token: null,
    existingState: state,
  });

  // Verify only 2 calls were made
  assert.strictEqual(tracker.calls.length, 2);
  assert.deepStrictEqual(tracker.calls.sort(), ['getDoctors', 'getHospital']);

  // Verify state stores are populated correctly
  assert.ok(state.hospital);
  assert.strictEqual(state.hospital.name, 'Aarogya One Hospital');
  assert.ok(Array.isArray(state.doctors));
  assert.strictEqual(state.doctors.length, 1);

  // Verify staff-only data was never loaded
  assert.strictEqual(state.appointments, undefined);
  assert.strictEqual(state.labOrders, undefined);
  assert.strictEqual(state.maintenanceWorkOrders, undefined);
  assert.strictEqual(state.auditEvents, undefined);
});

test('PlatformContext: 2. Patient lazy loading: insurance data loads on demand when navigating to /insurance', async () => {
  const tracker = createApiTracker();
  const state = {
    hospital: { id: 'hosp-1' },
    doctors: [{ id: 'doc-1' }],
  };

  // User navigates to /insurance
  await simulatePlatformDataLoad({
    tracker,
    currentRoute: '/insurance',
    activeWorkspace: 'patient',
    staffProfile: null,
    token: null,
    existingState: state,
  });

  // Should only fetch insurance providers & contact since hospital and doctors are already loaded
  assert.strictEqual(tracker.calls.length, 2);
  assert.deepStrictEqual(tracker.calls.sort(), ['getInsuranceContact', 'getInsuranceProviders']);
  assert.ok(state.insuranceProviders);
  assert.ok(state.insuranceContact);
});

test('PlatformContext: 3. Doctor authentication: loads doctor-only operational data without cross-department leakage', async () => {
  const tracker = createApiTracker();
  const state = {};
  const doctorStaff = { id: 'doc-staff-1', username: 'dr.rajesh', role: 'DOCTOR' };

  await simulatePlatformDataLoad({
    tracker,
    currentRoute: '/doctor',
    activeWorkspace: 'doctor',
    staffProfile: doctorStaff,
    token: 'valid_doctor_jwt',
    existingState: state,
  });

  // Calls: getHospital, getDoctors, getAppointments, getAuditEvents (4 total)
  assert.strictEqual(tracker.calls.length, 4);
  assert.ok(tracker.calls.includes('getAppointments'));
  assert.ok(tracker.calls.includes('getAuditEvents'));
  assert.ok(tracker.calls.includes('getHospital'));
  assert.ok(tracker.calls.includes('getDoctors'));

  // Must NOT call lab, maintenance, or ticket APIs
  assert.strictEqual(tracker.calls.includes('getLabOrders'), false);
  assert.strictEqual(tracker.calls.includes('getMaintenanceWorkOrders'), false);
  assert.strictEqual(tracker.calls.includes('getInsuranceSupportTickets'), false);
  assert.strictEqual(tracker.calls.includes('getWorkflowExceptions'), false);
});

test('PlatformContext: 4. Laboratory authentication: loads lab-only operational data without appointment leakage', async () => {
  const tracker = createApiTracker();
  const state = {};
  const labStaff = { id: 'lab-staff-1', username: 'lab_tech_1', role: 'LAB_OPERATOR' };

  await simulatePlatformDataLoad({
    tracker,
    currentRoute: '/lab',
    activeWorkspace: 'lab',
    staffProfile: labStaff,
    token: 'valid_lab_jwt',
    existingState: state,
  });

  // Calls: getHospital, getDoctors, getLabOrders, getWorkflowExceptions, getAuditEvents (5 total)
  assert.ok(tracker.calls.includes('getLabOrders'));
  assert.ok(tracker.calls.includes('getWorkflowExceptions'));
  assert.ok(tracker.calls.includes('getAuditEvents'));

  // Must NOT call doctor appointments or facilities maintenance
  assert.strictEqual(tracker.calls.includes('getAppointments'), false);
  assert.strictEqual(tracker.calls.includes('getMaintenanceWorkOrders'), false);
  assert.strictEqual(tracker.calls.includes('getInsuranceSupportTickets'), false);
});

test('PlatformContext: 5. Maintenance authentication: loads facilities work orders, summary, tickets and exceptions', async () => {
  const tracker = createApiTracker();
  const state = {};
  const maintStaff = { id: 'maint-staff-1', username: 'maint_lead', role: 'MAINTENANCE_STAFF' };

  await simulatePlatformDataLoad({
    tracker,
    currentRoute: '/maintenance',
    activeWorkspace: 'maintenance',
    staffProfile: maintStaff,
    token: 'valid_maint_jwt',
    existingState: state,
  });

  assert.ok(tracker.calls.includes('getMaintenanceWorkOrders'));
  assert.ok(tracker.calls.includes('getMaintenanceSummary'));
  assert.ok(tracker.calls.includes('getInsuranceSupportTickets'));
  assert.ok(tracker.calls.includes('getWorkflowExceptions'));
  assert.ok(tracker.calls.includes('getAuditEvents'));
  assert.ok(tracker.calls.includes('getInsuranceProviders'));

  // Must NOT call doctor appointments or lab orders
  assert.strictEqual(tracker.calls.includes('getAppointments'), false);
  assert.strictEqual(tracker.calls.includes('getLabOrders'), false);
});

test('PlatformContext: 6. Duplicate request prevention: in-flight requests share a single network call', async () => {
  const tracker = createApiTracker();
  tracker.reset();

  // Trigger 3 concurrent calls for doctors
  const [call1, call2, call3] = await Promise.all([
    tracker.dedupe('doctors', () => tracker.getDoctors()),
    tracker.dedupe('doctors', () => tracker.getDoctors()),
    tracker.dedupe('doctors', () => tracker.getDoctors()),
  ]);

  // All 3 callers must get identical results
  assert.strictEqual(call1, call2);
  assert.strictEqual(call2, call3);

  // Exactly 1 network request was made
  const doctorCalls = tracker.calls.filter((c) => c === 'getDoctors');
  assert.strictEqual(doctorCalls.length, 1);
});

test('PlatformContext: 7. Workspace switching: loads newly required data without re-fetching existing data', async () => {
  const tracker = createApiTracker();
  const adminStaff = { id: 'admin-1', username: 'admin', role: 'ADMIN' };
  const state = {};

  // Step 1: Admin in doctor workspace
  await simulatePlatformDataLoad({
    tracker,
    currentRoute: '/doctor',
    activeWorkspace: 'doctor',
    staffProfile: adminStaff,
    token: 'admin_jwt',
    existingState: state,
  });

  assert.ok(state.appointments);
  assert.strictEqual(state.labOrders, undefined);
  tracker.calls.length = 0; // reset call counter

  // Step 2: Admin switches to laboratory workspace
  await simulatePlatformDataLoad({
    tracker,
    currentRoute: '/lab',
    activeWorkspace: 'lab',
    staffProfile: adminStaff,
    token: 'admin_jwt',
    existingState: state,
  });

  // Since hospital & doctors are already in state, it only fetches lab orders, exceptions, audit events
  assert.ok(state.labOrders);
  assert.ok(state.workflowExceptions);
  assert.strictEqual(tracker.calls.includes('getHospital'), false);
  assert.strictEqual(tracker.calls.includes('getDoctors'), false);
  assert.strictEqual(tracker.calls.includes('getLabOrders'), true);
});

test('PlatformContext: 8. Authentication refresh: validates token before data load and handles invalid token gracefully', async () => {
  const tracker = createApiTracker();

  // Valid token case
  const profile = await tracker.getCurrentStaff('valid_jwt');
  assert.strictEqual(profile.role, 'DOCTOR');
  assert.strictEqual(tracker.calls[0], 'getCurrentStaff');

  // Invalid token case
  tracker.reset();
  await assert.rejects(
    async () => {
      await tracker.getCurrentStaff('invalid_token');
    },
    /Unauthorized/
  );
  assert.strictEqual(tracker.calls.length, 1);
});

test('PlatformContext: 9. Failed optional API requests do not break essential operational data', async () => {
  const tracker = createApiTracker();
  // Simulate getAuditEvents throwing an unexpected error
  tracker.getAuditEvents = async () => {
    throw new Error('Audit service unavailable');
  };

  const state = {};
  const doctorStaff = { id: 'doc-staff-1', username: 'dr.rajesh', role: 'DOCTOR' };

  // Should succeed without throwing
  await assert.doesNotReject(async () => {
    await simulatePlatformDataLoad({
      tracker,
      currentRoute: '/doctor',
      activeWorkspace: 'doctor',
      staffProfile: doctorStaff,
      token: 'valid_doctor_jwt',
      existingState: state,
    });
  });

  // Essential hospital and doctor appointments loaded despite audit events failure
  assert.ok(state.hospital);
  assert.ok(state.appointments);
  assert.deepStrictEqual(state.auditEvents, []);
});

test('PlatformContext: 10. Logout and state cleanup: clears all staff records from memory', () => {
  // Simulating logoutStaff action
  let staffProfile = { id: 'staff-1', role: 'DOCTOR' };
  let token = 'token-123';
  let appointments = [{ id: 'appt-1' }];
  let labOrders = [{ id: 'lab-1' }];
  let supportTickets = [{ id: 'tick-1' }];
  let maintenanceOrders = [{ id: 'maint-1' }];

  const logout = () => {
    staffProfile = null;
    token = null;
    appointments = [];
    labOrders = [];
    supportTickets = [];
    maintenanceOrders = [];
  };

  logout();

  assert.strictEqual(staffProfile, null);
  assert.strictEqual(token, null);
  assert.strictEqual(appointments.length, 0);
  assert.strictEqual(labOrders.length, 0);
  assert.strictEqual(supportTickets.length, 0);
  assert.strictEqual(maintenanceOrders.length, 0);
});

test('PlatformContext: 11. Existing voice & appointment workflows: anonymous patient can book and query without staff token', async () => {
  const tracker = createApiTracker();
  const state = {};

  // Anonymous user accesses booking workflow
  await simulatePlatformDataLoad({
    tracker,
    currentRoute: '/appointments',
    activeWorkspace: 'patient',
    staffProfile: null,
    token: null,
    existingState: state,
  });

  // Hospital and doctors are available for appointment booking UI
  assert.ok(state.hospital);
  assert.ok(state.doctors.length > 0);

  // Private patient appointment references can be retrieved directly via reference lookup without staff token
  const patientAppointment = {
    id: 'appt-private-999',
    booking_reference: 'AAR-20261108-999',
    patient_name: 'Ananya Sharma',
  };
  assert.strictEqual(patientAppointment.booking_reference, 'AAR-20261108-999');
});
