import { getPasswordRequirementsStatus } from '@/lib/validations/auth';

interface PasswordRulesListProps {
  id: string;
  password: string;
  showStatus?: boolean;
}

export function PasswordRulesList({ id, password, showStatus = false }: PasswordRulesListProps) {
  const rules = getPasswordRequirementsStatus(password);

  return (
    <ul
      id={id}
      className="mb-2 grid grid-cols-1 gap-1 rounded-lg bg-surface-50 p-2.5 text-xs text-surface-600 sm:grid-cols-2 dark:bg-surface-950 dark:text-surface-400"
    >
      {rules.map((rule) => (
        <li
          key={rule.label}
          className={`flex items-center gap-1.5 ${
            showStatus && rule.met ? 'font-medium text-green-700 dark:text-green-400' : ''
          }`}
        >
          <span aria-hidden="true">{showStatus && rule.met ? '✓' : '•'}</span>
          <span>{rule.label}</span>
        </li>
      ))}
    </ul>
  );
}
