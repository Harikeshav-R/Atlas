import { z } from 'zod';

export const EvaluationInputSchema = z.object({
  listingId: z.string().min(1),
});

export type EvaluationInput = z.infer<typeof EvaluationInputSchema>;

const BulletSchema = z.string().min(1);

const RoleSummaryBlockSchema = z.object({
  dayToDay: z.array(BulletSchema).min(1).max(5),
  reportingLine: z.string().optional(),
  teamShape: z.string().optional(),
  notableAbsences: z.array(z.string()).optional(),
});

const CvMatchItemSchema = z.object({
  requirement: z.string(),
  evidence: z.string().optional(),
  gap: z.boolean(),
  framingSuggestion: z.string().optional(),
});

const CvMatchBlockSchema = z.object({
  matches: z.array(CvMatchItemSchema).min(1),
  gapsSummary: z.string(),
});

const LevelStrategyBlockSchema = z.object({
  targetSeniority: z.string(),
  emphasize: z.array(z.string()),
  deemphasize: z.array(z.string()),
  expectedLoop: z.string().optional(),
});

const CompResearchBlockSchema = z.object({
  baseSalaryRange: z.string().optional(),
  totalCompRange: z.string().optional(),
  equityNotes: z.string().optional(),
  leveragePoints: z.array(z.string()),
  sources: z.array(z.string()),
  companyStage: z.string().optional(),
});

const PersonalizationBlockSchema = z.object({
  companyNews: z.array(z.string()),
  founderBackground: z.string().optional(),
  productLaunches: z.array(z.string()),
  engineeringBlog: z.array(z.string()),
  coverLetterHooks: z.array(z.string()),
});

const InterviewPrepItemSchema = z.object({
  stage: z.string(),
  likelyQuestions: z.array(z.string()),
  suggestedStories: z.array(z.string()),
});

const InterviewPrepBlockSchema = z.object({
  stages: z.array(InterviewPrepItemSchema),
  gaps: z.array(z.string()),
});

export const SixBlocksSchema = z.object({
  roleSummary: RoleSummaryBlockSchema,
  cvMatch: CvMatchBlockSchema,
  levelStrategy: LevelStrategyBlockSchema,
  compResearch: CompResearchBlockSchema,
  personalization: PersonalizationBlockSchema,
  interviewPrep: InterviewPrepBlockSchema,
});

export type SixBlocks = z.infer<typeof SixBlocksSchema>;

export const SCORING_DIMENSIONS = [
  'role_skill_alignment',
  'seniority_fit',
  'compensation',
  'growth_trajectory',
  'company_health',
  'mission_domain_fit',
  'work_model_fit',
  'geography_visa',
  'team_leadership_signal',
  'application_friction',
] as const;

export type ScoringDimension = typeof SCORING_DIMENSIONS[number];

export const DEFAULT_WEIGHTS: Readonly<Record<ScoringDimension, number>> = {
  role_skill_alignment: 0.18,
  seniority_fit: 0.10,
  compensation: 0.15,
  growth_trajectory: 0.12,
  company_health: 0.08,
  mission_domain_fit: 0.10,
  work_model_fit: 0.08,
  geography_visa: 0.07,
  team_leadership_signal: 0.06,
  application_friction: 0.06,
};

const DimensionScoreSchema = z.object({
  dimension: z.enum(SCORING_DIMENSIONS),
  score: z.number().min(0).max(10),
  justification: z.string().min(1),
});

export const ScorecardSchema = z.object({
  dimensions: z.array(DimensionScoreSchema).length(10),
});

export type Scorecard = z.infer<typeof ScorecardSchema>;

export const EvaluationOutputSchema = z.object({
  sixBlocks: SixBlocksSchema,
  scorecard: ScorecardSchema,
  grade: z.enum(['A', 'B', 'C', 'D', 'F']),
  score: z.number().min(0).max(10),
  summary: z.string().min(10),
});

export type EvaluationOutput = z.infer<typeof EvaluationOutputSchema>;

export function computeWeightedScore(
  dimensions: readonly z.infer<typeof DimensionScoreSchema>[],
  weights: Readonly<Record<ScoringDimension, number>> = DEFAULT_WEIGHTS,
): number {
  let total = 0;
  for (const dim of dimensions) {
    total += dim.score * (weights[dim.dimension] ?? 0);
  }
  return Math.round(total * 100) / 100;
}

export function scoreToGrade(score: number): 'A' | 'B' | 'C' | 'D' | 'F' {
  if (score >= 8.5) return 'A';
  if (score >= 7.0) return 'B';
  if (score >= 5.5) return 'C';
  if (score >= 4.0) return 'D';
  return 'F';
}
