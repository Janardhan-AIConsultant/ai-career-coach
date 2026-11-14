/** Closed value sets. These mirror the backend and are deliberately the only supported options. */
export const ROADMAP_DURATIONS = [7, 15, 60] as const;
export type RoadmapDuration = (typeof ROADMAP_DURATIONS)[number];

export const SHARE_PLATFORMS = ["linkedin", "whatsapp", "facebook"] as const;
export type SharePlatform = (typeof SHARE_PLATFORMS)[number];
export const PLATFORM_LABEL: Record<SharePlatform, string> = {
  linkedin: "LinkedIn",
  whatsapp: "WhatsApp",
  facebook: "Facebook",
};

export const FEEDBACK_FEATURES: Record<string, string> = {
  platform: "The platform overall",
  resume_analyzer: "Resume analysis",
  job_description_analyzer: "Job description analysis",
  career_match: "Career match",
  resume_optimizer: "Resume optimisation",
  interview_preparation: "Interview preparation",
  ai_career_coach: "AI Career Coach",
  learning_roadmap: "Learning roadmap",
};
