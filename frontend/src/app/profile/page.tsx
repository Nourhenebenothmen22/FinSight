'use client';

import { useRouter } from 'next/navigation';
import { FormEvent, useCallback, useEffect, useState } from 'react';
import { useAuth } from '@/components/auth/AuthProvider';
import { PasswordInput } from '@/components/auth/PasswordInput';
import { PasswordRulesList } from '@/components/auth/PasswordRulesList';
import { LegalDisclaimer } from '@/components/LegalDisclaimer';
import { Navbar } from '@/components/Navbar';
import { extractApiErrorMessage } from '@/lib/api';
import { authApi, SessionInfo } from '@/lib/auth';
import { changePasswordSchema, updateProfileSchema } from '@/lib/validations/auth';

export default function ProfilePage() {
  const router = useRouter();
  const auth = useAuth();

  const [name, setName] = useState('');
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [savingProfile, setSavingProfile] = useState(false);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [savingPassword, setSavingPassword] = useState(false);

  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);

  const loadSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const list = await authApi.listSessions();
      setSessions(list);
    } catch {
      setSessions([]);
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!auth.isLoading && !auth.isAuthenticated) {
      router.replace('/login?next=/profile');
    }
  }, [auth.isAuthenticated, auth.isLoading, router]);

  useEffect(() => {
    if (auth.user) {
      setName(auth.user.name);
      loadSessions();
    }
  }, [auth.user, loadSessions]);

  if (auth.isLoading || !auth.isAuthenticated || !auth.user) {
    return (
      <div className="min-h-screen bg-surface-50 dark:bg-surface-950">
        <Navbar />
        <main className="mx-auto max-w-3xl px-4 py-16 text-center text-sm text-surface-600 dark:text-surface-400">
          Loading account profile...
        </main>
      </div>
    );
  }

  const handleUpdateProfile = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setProfileMessage(null);
    setProfileError(null);

    const parsed = updateProfileSchema.safeParse({ name });
    if (!parsed.success) {
      setProfileError(parsed.error.issues[0]?.message ?? 'Invalid name.');
      return;
    }

    setSavingProfile(true);
    try {
      await authApi.updateMe(parsed.data);
      await auth.refreshUser();
      setProfileMessage('Profile updated.');
    } catch (err) {
      setProfileError(extractApiErrorMessage(err, 'Unable to update profile.'));
    } finally {
      setSavingProfile(false);
    }
  };

  const handleChangePassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPasswordMessage(null);
    setPasswordError(null);

    const parsed = changePasswordSchema.safeParse({
      current_password: currentPassword || undefined,
      new_password: newPassword,
      requireCurrentPassword: auth.user?.has_password ?? true,
    });
    if (!parsed.success) {
      setPasswordError(parsed.error.issues[0]?.message ?? 'Invalid password input.');
      return;
    }

    setSavingPassword(true);
    try {
      const resp = await authApi.changePassword({
        current_password: parsed.data.current_password,
        new_password: parsed.data.new_password,
      });
      setCurrentPassword('');
      setNewPassword('');
      setPasswordMessage(resp.message);
      await auth.refreshUser();
      await loadSessions();
    } catch (err) {
      setPasswordError(extractApiErrorMessage(err, 'Unable to update password.'));
    } finally {
      setSavingPassword(false);
    }
  };

  const handleRevokeSession = async (sessionId: string) => {
    await authApi.revokeSession(sessionId);
    await loadSessions();
  };

  const handleLogoutAll = async () => {
    await auth.logoutAll();
    router.push('/login');
  };

  return (
    <div className="min-h-screen bg-surface-50 dark:bg-surface-950">
      <Navbar />
      <main className="mx-auto max-w-3xl space-y-8 px-4 py-10 sm:px-6 lg:px-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-surface-900 dark:text-surface-50">
            Account Profile
          </h1>
          <p className="mt-1 text-sm text-surface-600 dark:text-surface-400">
            Manage your FinSight identity, password, and active login sessions.
          </p>
        </div>

        {/* Account Summary & Update Name */}
        <section className="rounded-2xl border border-surface-200 bg-white p-6 shadow-sm dark:border-surface-800 dark:bg-surface-900">
          <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-surface-200 pb-4 dark:border-surface-800">
            <div>
              <p className="text-sm text-surface-500 dark:text-surface-400">Signed-in email</p>
              <p className="font-medium text-surface-900 dark:text-surface-50">{auth.user.email}</p>
            </div>
            <div className="flex items-center gap-2">
              {auth.user.email_verified_at ? (
                <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-medium text-green-800 dark:bg-green-900/40 dark:text-green-200">
                  Verified email
                </span>
              ) : (
                <span className="rounded-full bg-yellow-100 px-3 py-1 text-xs font-medium text-yellow-800">
                  Unverified
                </span>
              )}
              {auth.user.oauth_provider ? (
                <span className="rounded-full bg-primary-100 px-3 py-1 text-xs font-medium capitalize text-primary-800 dark:bg-primary-900/40 dark:text-primary-200">
                  {auth.user.oauth_provider} linked
                </span>
              ) : null}
            </div>
          </div>

          <form onSubmit={handleUpdateProfile} method="post" className="space-y-4">
            {profileError ? (
              <p
                role="alert"
                className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200"
              >
                {profileError}
              </p>
            ) : null}
            {profileMessage ? (
              <p
                role="status"
                className="rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-800 dark:border-green-900 dark:bg-green-950/30 dark:text-green-200"
              >
                {profileMessage}
              </p>
            ) : null}

            <div className="space-y-1.5">
              <label
                htmlFor="profile-name"
                className="block text-sm font-medium text-surface-800 dark:text-surface-200"
              >
                Full name
              </label>
              <input
                id="profile-name"
                name="name"
                type="text"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
                maxLength={120}
                autoComplete="name"
                className="min-h-[48px] w-full rounded-lg border border-surface-300 bg-white px-3.5 py-2.5 text-base text-surface-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 dark:border-surface-700 dark:bg-surface-950 dark:text-surface-50"
              />
            </div>

            <button
              type="submit"
              disabled={savingProfile}
              className="min-h-[44px] rounded-lg bg-primary-600 px-5 py-2 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60"
            >
              {savingProfile ? 'Saving...' : 'Save profile'}
            </button>
          </form>
        </section>

        {/* Password Change / Set */}
        <section className="rounded-2xl border border-surface-200 bg-white p-6 shadow-sm dark:border-surface-800 dark:bg-surface-900">
          <h2 className="mb-4 text-lg font-semibold text-surface-900 dark:text-surface-50">
            {auth.user.has_password ? 'Change password' : 'Set a local password'}
          </h2>
          <form onSubmit={handleChangePassword} method="post" className="space-y-4">
            {passwordError ? (
              <p
                role="alert"
                className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200"
              >
                {passwordError}
              </p>
            ) : null}
            {passwordMessage ? (
              <p
                role="status"
                className="rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-800 dark:border-green-900 dark:bg-green-950/30 dark:text-green-200"
              >
                {passwordMessage}
              </p>
            ) : null}

            {auth.user.has_password ? (
              <PasswordInput
                id="profile-current-password"
                name="current_password"
                label="Current password"
                value={currentPassword}
                onChange={setCurrentPassword}
                autoComplete="current-password"
                enterKeyHint="next"
              />
            ) : null}

            <PasswordInput
              id="profile-new-password"
              name="new_password"
              label="New password"
              value={newPassword}
              onChange={setNewPassword}
              autoComplete="new-password"
              minLength={12}
              enterKeyHint="done"
              hintId="profile-password-rules"
              hintAbove={
                <PasswordRulesList
                  id="profile-password-rules"
                  password={newPassword}
                  showStatus={newPassword.length > 0}
                />
              }
            />

            <button
              type="submit"
              disabled={savingPassword}
              className="min-h-[44px] rounded-lg bg-primary-600 px-5 py-2 text-sm font-semibold text-white hover:bg-primary-700 disabled:opacity-60"
            >
              {savingPassword ? 'Updating...' : 'Update password'}
            </button>
          </form>
        </section>

        {/* Active Sessions */}
        <section className="rounded-2xl border border-surface-200 bg-white p-6 shadow-sm dark:border-surface-800 dark:bg-surface-900">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-surface-900 dark:text-surface-50">
                Active sessions
              </h2>
              <p className="text-xs text-surface-500 dark:text-surface-400">
                Refresh tokens issued to your browsers and API clients.
              </p>
            </div>
            <button
              type="button"
              onClick={handleLogoutAll}
              className="min-h-[40px] rounded-lg border border-red-300 px-3.5 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950/30"
            >
              Sign out everywhere
            </button>
          </div>

          {sessionsLoading ? (
            <p className="text-sm text-surface-500">Loading sessions...</p>
          ) : sessions.length === 0 ? (
            <p className="text-sm text-surface-500">No active sessions recorded.</p>
          ) : (
            <ul className="divide-y divide-surface-200 dark:divide-surface-800">
              {sessions.map((session) => (
                <li
                  key={session.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm"
                >
                  <div>
                    <p className="font-medium text-surface-800 dark:text-surface-200">
                      {session.user_agent || 'Web / API Client'}
                      {session.is_current ? (
                        <span className="ml-2 rounded-full bg-primary-100 px-2 py-0.5 text-xs text-primary-800 dark:bg-primary-900/40 dark:text-primary-200">
                          Current
                        </span>
                      ) : null}
                    </p>
                    <p className="text-xs text-surface-500 dark:text-surface-400">
                      IP: {session.ip_address || 'Unknown'} • Started{' '}
                      {new Date(session.created_at).toLocaleString()}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRevokeSession(session.id)}
                    className="rounded-lg border border-surface-300 px-3 py-1.5 text-xs font-medium text-surface-700 hover:bg-surface-100 dark:border-surface-700 dark:text-surface-200 dark:hover:bg-surface-800"
                  >
                    Revoke
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* F2 Boundary Callout */}
        <section className="rounded-2xl border border-dashed border-surface-300 bg-surface-100/60 p-5 text-sm text-surface-600 dark:border-surface-700 dark:bg-surface-900/40 dark:text-surface-400">
          Workspaces, team invitations, and tenant RBAC roles (`owner`, `analyst`, `viewer`) will be
          introduced in <strong>F2</strong>.
        </section>

        <LegalDisclaimer />
      </main>
    </div>
  );
}
