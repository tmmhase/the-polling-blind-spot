export type ErrorStats = {
  mean_signed_error: number | null;
  median_signed_error: number | null;
  std_signed_error: number | null;
  mae: number | null;
  rmse: number | null;
  p10: number | null;
  p25: number | null;
  p75: number | null;
  p90: number | null;
};

export type Overview = {
  scored_questions: number;
  distinct_poll_ids: number;
  races: number;
  states_with_scored_questions: number;
  count_note: string;
  error_definition: string;
  margin_definition: string;
  poll_level: ErrorStats & { n: number };
  race_level_unweighted_mean: ErrorStats & { n: number };
  cycles: (ErrorStats & { cycle: number; n_questions: number; n_races: number })[];
  model: {
    equation: string;
    seed: number;
    burn_in: number;
    draws: number;
    thin: number;
    n_polls_modeled: number;
    n_questions_kept: number;
    median_sample_size: number;
    median_sampling_variance: number;
    mu_p50: number;
    sd_race_p50: number;
    sd_house_p50: number;
    sd_cycle_p50: number;
    phi_p50: number;
  };
};

export type MapState = {
  state_po: string;
  state_name: string;
  has_scored_questions: boolean;
  n_questions: number;
  n_races: number;
  mean_signed_error: number | null;
  median_signed_error: number | null;
  mae: number | null;
  rmse: number | null;
  exclusions: { reason: string; label: string; n_questions: number }[];
};

export type MapPayload = {
  cycles: number[];
  map_note: string;
  score_note: string;
  states: MapState[];
};

export type Histogram = {
  start: number;
  stop: number;
  step: number;
  edges: number[];
  counts: number[];
  underflow: number;
  overflow: number;
  n: number;
};

export type ErrorsPayload = {
  definition: string;
  histogram: Histogram;
  poll_level: ErrorStats & { n: number };
  cycles: (ErrorStats & { cycle: number; n_questions: number; n_races: number })[];
  timing: (ErrorStats & { timing: string; n: number })[];
};

export type PollsterRow = {
  pollster_key: string;
  pollster: string;
  n_questions: number;
  n_races: number;
  n_cycles: number;
  mean_signed_error: number | null;
  median_signed_error: number | null;
  mae: number | null;
  rmse: number | null;
  modal_methodology: string | null;
  modal_methodology_questions: number;
};

export type PollstersPayload = {
  count_note: string;
  methodology_rule: string;
  population_note: string;
  methodology: ({ methodology: string; n_questions: number } & Pick<
    ErrorStats,
    "mean_signed_error" | "median_signed_error" | "mae"
  >)[];
  population: ({ population: string; label: string; n: number } & ErrorStats)[];
  pollsters: PollsterRow[];
};

export type DesignSummary = {
  design: string;
  label: string;
  n_polls: number;
  n_pollsters: number;
  n_draws: number;
  mean: number;
  sd: number;
  p025: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
  p90: number;
  p975: number;
  histogram: Histogram;
};

export type UncertaintyPayload = {
  simulation_note: string;
  equation: string;
  error_definition: string;
  preparation: {
    n_questions: number;
    n_questions_kept: number;
    n_questions_excluded: number;
    exclusions_by_reason: Record<string, number>;
    n_polls: number;
    n_races: number;
    n_pollster_race_groups: number;
    median_sample_size: number;
    median_sampling_variance: number;
  };
  priors: Record<string, string>;
  sampler: {
    burn_in: number;
    draws: number;
    thin: number;
    seed: number;
    algorithm: string;
  };
  posterior: {
    parameter: string;
    label: string;
    unit: string;
    mean: number;
    p05: number;
    p50: number;
    p95: number;
    ess: number;
  }[];
  designs: DesignSummary[];
  variance_unweighted: {
    design: string;
    label: string;
    component: string;
    component_label: string;
    variance: number;
    share: number;
    sd_if_only_this_component: number;
    predictive_sd: number;
  }[];
  backtest: {
    protocol: string;
    estimand: string;
    cycle: string;
    n_races: number;
    coverage_50: number;
    coverage_80: number;
    coverage_95: number;
    mean_width_95: number;
    mean_pit: number;
    mean_actual_error: number;
    mean_predicted_median: number;
  }[];
  prior_sensitivity: {
    half_cauchy_scale: number;
    parameter: string;
    label: string;
    p50: number;
    p05: number;
    p95: number;
  }[];
  leakage_controls: string[];
  limitations: string[];
};

export type SourceCard = {
  id: string;
  title: string;
  role: string;
  file: string;
  url: string;
  snapshot_url: string | null;
  documentation_url: string;
  license: string;
  license_url: string;
  coverage: string;
  limitations: string[];
};

export type NotesPayload = {
  sources: SourceCard[];
  inclusion_rules: string[];
  analysis_leakage_controls: string[];
  model_leakage_controls: string[];
  limitations: string[];
  error_definition: string;
  margin_definition: string;
  model: string;
  priors: Record<string, string>;
  sampler: UncertaintyPayload["sampler"];
};

export type StateQuestion = {
  question_id: string;
  poll_id: string;
  pollster: string;
  cycle: number;
  contest_id: string;
  stage: string;
  end_date: string;
  days_before_election: number | null;
  sample_size: number | null;
  population: string | null;
  methodology: string | null;
  dem_candidate: string;
  rep_candidate: string;
  poll_margin_two_party: number | null;
  result_margin_two_party: number | null;
  error_two_party: number | null;
};

export type StateRace = {
  contest_id: string;
  cycle: number;
  election_year: number;
  stage: string;
  special: boolean;
  dem_candidate: string;
  rep_candidate: string;
  n_questions: number;
  poll_margin_two_party_mean: number | null;
  result_margin_two_party: number | null;
  error_of_unweighted_mean: number | null;
  result_unofficial: boolean;
};

export type StateDetail = {
  state_po: string;
  state_name: string;
  has_scored_questions: boolean;
  summary: (ErrorStats & { n_questions: number; n_races: number }) | null;
  exclusions: MapState["exclusions"];
  result_role: string;
  races: StateRace[];
  questions: StateQuestion[];
};

export type DashboardData = {
  overview: Overview;
  map: MapPayload;
  errors: ErrorsPayload;
  pollsters: PollstersPayload;
  uncertainty: UncertaintyPayload;
  notes: NotesPayload;
};
