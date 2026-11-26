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
import { configureAuthClient } from '@/lib/api';
import { authApi, AuthUser, TokenResponse } from '@/lib/auth';

interface AuthContextValue {
  user: AuthUser | null;
  accessToken: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  setSession: (tokens: TokenResponse) => void;
  clearSession: () => void;
  refreshSession: () => Promise<string | null>;
  refreshUser: () => Promise<AuthUser | null>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

interface AuthProviderProps {
  children: React.ReactNode;
  skipInitialRefresh?: boolean;
}

export function AuthProvider({ children, skipInitialRefresh = false }: AuthProviderProps) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(!skipInitialRefresh);
  const accessTokenRef = useRef<string | null>(null);

  const applySession = useCallback((tokens: TokenResponse) => {
    accessTokenRef.current = tokens.access_token;
    setAccessToken(tokens.access_token);
    setUser(tokens.user);
  }, []);

  const clearSession = useCallback(() => {
    accessTokenRef.current = null;
    setAccessToken(null);
    setUser(null);
  }, []);

  const refreshSession = useCallback(async (): Promise<string | null> => {
    try {
      const tokens = await authApi.refresh();
      applySession(tokens);
      return tokens.access_token;
    } catch {
      clearSession();
      return null;
    }
  }, [applySession, clearSession]);

  const refreshUser = useCallback(async (): Promise<AuthUser | null> => {
    try {
      const me = await authApi.getMe();
      setUser(me);
      return me;
    } catch {
      return null;
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const logoutAll = useCallback(async () => {
    try {
      await authApi.logoutAll();
    } finally {
      clearSession();
    }
  }, [clearSession]);

  useEffect(() => {
    configureAuthClient({
      getAccessToken: () => accessTokenRef.current,
      refreshAccessToken: refreshSession,
    });
    return () => configureAuthClient(null);
  }, [refreshSession]);

  useEffect(() => {
    if (skipInitialRefresh) {
      return;
    }
    let active = true;
    refreshSession().finally(() => {
      if (active) {
        setIsLoading(false);
      }
    });
    return () => {
      active = false;
    };
  }, [refreshSession, skipInitialRefresh]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      accessToken,
      isLoading,
      isAuthenticated: Boolean(user && accessToken),
      setSession: applySession,
      clearSession,
      refreshSession,
      refreshUser,
      logout,
      logoutAll,
    }),
    [
      accessToken,
      applySession,
      clearSession,
      isLoading,
      logout,
      logoutAll,
      refreshSession,
      refreshUser,
      user,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used inside an AuthProvider');
  }
  return ctx;
}

export function useOptionalAuth(): AuthContextValue | null {
  return useContext(AuthContext);
}
