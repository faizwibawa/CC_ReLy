export type Phase = "RED" | "YELLOW" | "GREEN";
export type DataSource = "MANUAL" | "SIMULATOR";
export type CongestionLevel = "FREE" | "MODERATE" | "HEAVY";

export interface Detour {
  label: string;
  lat: number;
  lng: number;
}

export interface TrafficSignal {
  signal_id: string;
  location: string;
  latitude: number;
  longitude: number;
  current_phase: Phase;
  remaining_seconds: number;
  confidence_score: number;
  congestion_level: CongestionLevel;
  detour: Detour | null;
  updated_at: string;
  data_source: DataSource;
  /** Absolute end time of the current phase (set by the API; absent in mock data). */
  phase_ends_at?: string;
}

export type SignalInput = Omit<TrafficSignal, "updated_at" | "phase_ends_at">;
