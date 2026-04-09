import { z } from 'zod';

/** Canonical profile YAML schema (see technical-design.md Section 22). */
export const ProfileExperienceSchema = z.object({
  company: z.string(),
  title: z.string(),
  start: z.string(),
  end: z.string().nullable(),
  summary: z.string().optional(),
  highlights: z.array(z.string()).default([]),
});

export const ProfileSchema = z.object({
  version: z.literal(1),
  name: z.string(),
  contact: z.object({
    email: z.email(),
    phone: z.string().optional(),
    location: z.string().optional(),
    links: z.array(z.url()).default([]),
  }),
  headline: z.string().optional(),
  summary: z.string().optional(),
  experience: z.array(ProfileExperienceSchema).default([]),
  education: z
    .array(
      z.object({
        school: z.string(),
        degree: z.string().optional(),
        start: z.string().optional(),
        end: z.string().optional(),
      }),
    )
    .default([]),
  skills: z.array(z.string()).default([]),
  preferences: z
    .object({
      roles: z.array(z.string()).default([]),
      locations: z.array(z.string()).default([]),
      remote: z.enum(['remote', 'hybrid', 'onsite', 'any']).default('any'),
      minSalary: z.number().nonnegative().optional(),
    })
    .default({}),
});

export type Profile = z.infer<typeof ProfileSchema>;
