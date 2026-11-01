import { useCallback, useEffect, useState } from 'react';
import { AppRoutePath, WorkspaceTab } from '../types/api';

const VALID_ROUTES: Set<AppRoutePath> = new Set([
  '/',
  '/doctors',
  '/appointments',
  '/lab-status',
  '/insurance',
  '/support',
  '/medivoice',
  '/staff/login',
  '/login',
  '/doctor',
  '/doctor/appointments',
  '/doctor/calendar',
  '/doctor/availability',
  '/doctor/profile',
  '/lab',
  '/lab/orders',
  '/maintenance',
  '/maintenance/work-orders',
  '/maintenance/new-request',
  '/maintenance/doctors',
  '/maintenance/insurance',
  '/maintenance/tickets',
]);

function normalizePathToRoute(pathname: string): AppRoutePath {
  const cleaned = (pathname || '/').replace(/\/+$/, '') || '/';
  if (cleaned === '/login' || cleaned === '/staff') {
    return '/staff/login';
  }
  if (VALID_ROUTES.has(cleaned as AppRoutePath)) {
    return cleaned as AppRoutePath;
  }
  return '/';
}

export function useMediVoiceRoute() {
  const [currentRoute, setCurrentRoute] = useState<AppRoutePath>(() => {
    try {
      return normalizePathToRoute(window.location.pathname);
    } catch {
      return '/';
    }
  });
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);

  useEffect(() => {
    const handlePopState = () => {
      setCurrentRoute(normalizePathToRoute(window.location.pathname));
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const navigate = useCallback((route: AppRoutePath, entityId?: string | null) => {
    const normalized = route === '/login' ? '/staff/login' : route;
    setCurrentRoute(normalized);
    setSelectedEntityId(entityId ?? null);
    try {
      if (window.location.pathname !== normalized) {
        window.history.pushState({}, '', normalized);
      }
    } catch {
      // ignore history errors in sandboxed frames
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const activeWorkspace: WorkspaceTab = currentRoute.startsWith('/doctor')
    ? 'doctor'
    : currentRoute.startsWith('/lab') && currentRoute !== '/lab-status'
    ? 'lab'
    : currentRoute.startsWith('/maintenance')
    ? 'maintenance'
    : 'patient';

  const setActiveWorkspace = useCallback(
    (tab: WorkspaceTab) => {
      if (tab === 'doctor') navigate('/doctor');
      else if (tab === 'lab') navigate('/lab');
      else if (tab === 'maintenance') navigate('/maintenance');
      else navigate('/');
    },
    [navigate]
  );

  return {
    currentRoute,
    selectedEntityId,
    navigate,
    activeWorkspace,
    setActiveWorkspace,
  };
}
