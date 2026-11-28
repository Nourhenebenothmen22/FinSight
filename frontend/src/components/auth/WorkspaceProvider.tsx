'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useOptionalAuth } from '@/components/auth/AuthProvider';
import { configureTenantClient, extractApiErrorMessage } from '@/lib/api';
import { OrganizationSummary, orgsApi } from '@/lib/orgs';

const ACTIVE_ORG_STORAGE_KEY = 'finsight.active_org_id';

function readStoredOrgId(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return window.localStorage.getItem(ACTIVE_ORG_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredOrgId(orgId: string | null): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    if (orgId) {
      window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, orgId);
    } else {
      window.localStorage.removeItem(ACTIVE_ORG_STORAGE_KEY);
    }
  } catch {
    // Ignore storage quota or private-mode restrictions; backend membership remains source of truth.
  }
}

export interface WorkspaceContextValue {
  workspaces: OrganizationSummary[];
  activeOrgId: string | null;
  activeWorkspace: OrganizationSummary | null;
  isLoading: boolean;
  error: string | null;
  setActiveOrgId: (orgId: string | null) => void;
  reloadWorkspaces: () => Promise<OrganizationSummary[]>;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

interface WorkspaceProviderProps {
  children: React.ReactNode;
  skipInitialLoad?: boolean;
}

export function WorkspaceProvider({ children, skipInitialLoad = false }: WorkspaceProviderProps) {
  const auth = useOptionalAuth();
  const isAuthenticated = Boolean(auth?.isAuthenticated);
  const authLoading = Boolean(auth?.isLoading);

  const [workspaces, setWorkspaces] = useState<OrganizationSummary[]>([]);
  const [activeOrgId, setActiveOrgIdState] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const activeOrgIdRef = useRef<string | null>(null);
  activeOrgIdRef.current = activeOrgId;

  const setActiveOrgId = useCallback((orgId: string | null) => {
    activeOrgIdRef.current = orgId;
    setActiveOrgIdState(orgId);
    writeStoredOrgId(orgId);
  }, []);

  const syncWorkspaces = useCallback(
    async (isCancelled?: () => boolean): Promise<OrganizationSummary[]> => {
      if (!isAuthenticated) {
        if (!isCancelled?.()) {
          setWorkspaces([]);
          setActiveOrgId(null);
          setError(null);
        }
        return [];
      }

      if (!isCancelled?.()) {
        setIsLoading(true);
        setError(null);
      }
      try {
        const list = await orgsApi.list();
        if (isCancelled?.()) {
          return [];
        }
        setWorkspaces(list);

        const candidate = activeOrgIdRef.current ?? readStoredOrgId();
        const matched = candidate && list.some((org) => org.id === candidate);
        const nextId = matched ? candidate : list[0]?.id ?? null;
        setActiveOrgId(nextId);
        return list;
      } catch (err) {
        if (!isCancelled?.()) {
          setError(extractApiErrorMessage(err, 'Unable to load workspaces.'));
        }
        return [];
      } finally {
        if (!isCancelled?.()) {
          setIsLoading(false);
        }
      }
    },
    [isAuthenticated, setActiveOrgId]
  );

  const reloadWorkspaces = useCallback(() => syncWorkspaces(), [syncWorkspaces]);

  useEffect(() => {
    configureTenantClient(() => activeOrgIdRef.current);
    return () => configureTenantClient(null);
  }, []);

  useEffect(() => {
    if (skipInitialLoad || authLoading) {
      return;
    }
    let active = true;
    void syncWorkspaces(() => !active);
    return () => {
      active = false;
    };
  }, [authLoading, skipInitialLoad, syncWorkspaces]);

  const activeWorkspace = useMemo(
    () => workspaces.find((org) => org.id === activeOrgId) ?? null,
    [activeOrgId, workspaces]
  );

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      workspaces,
      activeOrgId,
      activeWorkspace,
      isLoading,
      error,
      setActiveOrgId,
      reloadWorkspaces,
    }),
    [activeOrgId, activeWorkspace, error, isLoading, reloadWorkspaces, setActiveOrgId, workspaces]
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error('useWorkspace must be used inside a WorkspaceProvider');
  }
  return ctx;
}

export function useOptionalWorkspace(): WorkspaceContextValue | null {
  return useContext(WorkspaceContext);
}
