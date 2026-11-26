import { LegalDisclaimer } from '@/components/LegalDisclaimer';
import { Navbar } from '@/components/Navbar';

interface AuthCardProps {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}

export function AuthCard({ title, subtitle, children }: AuthCardProps) {
  return (
    <div className="min-h-screen bg-surface-50 dark:bg-surface-950">
      <Navbar />
      <main className="mx-auto max-w-md px-4 py-12 sm:px-6">
        <div className="rounded-2xl border border-surface-200 bg-white p-6 shadow-sm sm:p-8 dark:border-surface-800 dark:bg-surface-900">
          <div className="mb-6">
            <h1 className="text-2xl font-bold tracking-tight text-surface-900 dark:text-surface-50">
              {title}
            </h1>
            <p className="mt-1.5 text-sm text-surface-600 dark:text-surface-400">{subtitle}</p>
          </div>
          {children}
        </div>
        <LegalDisclaimer />
      </main>
    </div>
  );
}
