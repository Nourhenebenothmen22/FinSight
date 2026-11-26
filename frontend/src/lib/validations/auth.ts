/** Zod validation schemas matching FinSight backend F1 auth constraints. */

import { z } from 'zod';

export const MIN_PASSWORD_LENGTH = 12;
export const MAX_PASSWORD_LENGTH = 128;

const emailSchema = z
  .string()
  .trim()
  .toLowerCase()
  .email('Enter an email address in the format you@example.com.');

const nameSchema = z
  .string()
  .trim()
  .min(1, 'Please enter your name.')
  .max(120, 'Name must be at most 120 characters.');

export const passwordSchema = z
  .string()
  .min(MIN_PASSWORD_LENGTH, `Password must be at least ${MIN_PASSWORD_LENGTH} characters long.`)
  .max(MAX_PASSWORD_LENGTH, `Password must be at most ${MAX_PASSWORD_LENGTH} characters long.`)
  .refine((val) => /[a-z]/.test(val), 'Password must contain at least one lowercase letter.')
  .refine((val) => /[A-Z]/.test(val), 'Password must contain at least one uppercase letter.')
  .refine((val) => /\d/.test(val), 'Password must contain at least one digit.')
  .refine(
    (val) => /[^A-Za-z0-9]/.test(val),
    'Password must contain at least one special character.'
  );

export const registerSchema = z.object({
  name: nameSchema,
  email: emailSchema,
  password: passwordSchema,
});

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, 'Please enter your password.').max(MAX_PASSWORD_LENGTH),
});

export const forgotPasswordSchema = z.object({
  email: emailSchema,
});

export const resetPasswordSchema = z.object({
  token: z.string().trim().min(16, 'Invalid verification or reset token.'),
  new_password: passwordSchema,
});

export const updateProfileSchema = z.object({
  name: nameSchema,
});

export const changePasswordSchema = z
  .object({
    current_password: z.string().max(MAX_PASSWORD_LENGTH).optional(),
    new_password: passwordSchema,
    requireCurrentPassword: z.boolean().optional(),
  })
  .superRefine((data, ctx) => {
    if (data.requireCurrentPassword && !data.current_password) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['current_password'],
        message: 'Please enter your current password.',
      });
    }
    if (data.current_password && data.current_password === data.new_password) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['new_password'],
        message: 'New password must differ from your current password.',
      });
    }
  });

export function getPasswordRequirementsStatus(password: string) {
  return [
    {
      label: `At least ${MIN_PASSWORD_LENGTH} characters`,
      met: password.length >= MIN_PASSWORD_LENGTH,
    },
    { label: 'One uppercase letter', met: /[A-Z]/.test(password) },
    { label: 'One lowercase letter', met: /[a-z]/.test(password) },
    { label: 'One number', met: /\d/.test(password) },
    { label: 'One special character', met: /[^A-Za-z0-9]/.test(password) },
  ];
}
