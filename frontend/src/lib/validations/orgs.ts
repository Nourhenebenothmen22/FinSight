/** Zod validation schemas matching FinSight backend F2 workspace & RBAC constraints. */

import { z } from 'zod';

const orgNameSchema = z
  .string()
  .trim()
  .min(1, 'Please enter a workspace name.')
  .max(120, 'Workspace name must be at most 120 characters.');

const emailSchema = z
  .string()
  .trim()
  .toLowerCase()
  .email('Enter an email address in the format colleague@example.com.');

export const createOrgSchema = z.object({
  name: orgNameSchema,
});

export const updateOrgSchema = z.object({
  name: orgNameSchema,
});

export const inviteMemberSchema = z.object({
  email: emailSchema,
  role: z.enum(['analyst', 'viewer']),
});

export const updateMemberRoleSchema = z.object({
  role: z.enum(['owner', 'analyst', 'viewer']),
});

export const acceptInvitationSchema = z.object({
  token: z.string().trim().min(16, 'Invitation token is invalid or incomplete.').max(512),
});
