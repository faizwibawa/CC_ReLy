import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, ArrowRight, Bell, Check, ChevronRight, CircleGauge, Edit3,
  ExternalLink, LocateFixed, Map, MapPin, Mic, Moon, Navigation, Plus,
  RefreshCw, Route, Search, Settings2, Signal, Sun, Trash2, X, Zap,
} from "lucide-react";
import * as api from "./api/signals";
import { buildGoogleMapsLink } from "./lib/maps";
import { MOCK_SIGNALS } from "./mockData";
import type { CongestionLevel, DataSource, Phase, SignalInput, TrafficSignal } from "./types";

type Tab = "trip" | "drive" | "signals" | "admin";
type Toast = { id: number; kind: "ok" | "error"; text: string };
const PHASES: Phase[] = ["RED", "YELLOW", "GREEN"];
const CONGESTION: CongestionLevel[] = ["FREE", "MODERATE", "HEAVY"];
const phaseHex = { RED: "#EF4444", YELLOW: "#F59E0B", GREEN: "#22C55E" };
const emptySignal: SignalInput = {
  signal_id: "", location: "", latitude: -7.79, longitude: 110.367,
  current_phase: "RED", remaining_seconds: 20, confidence_score: 0.9,
  congestion_level: "MODERATE", detour: null, data_source: "SIMULATOR",
};

function secondsLeft(signal: TrafficSignal, now: number) {
  // API data: count down to the absolute phase end time, so the value stays correct between refreshes.
  if (signal.phase_ends_at) return Math.max(0, Math.ceil((new Date(signal.phase_ends_at).getTime() - now) / 1000));
  // Mock data: remaining_seconds was valid at updated_at.
  return Math.max(0, signal.remaining_seconds - Math.floor((now - new Date(signal.updated_at).getTime()) / 1000));
}

function age(date: string, now: number) {
  const seconds = Math.max(0, Math.floor((now - new Date(date).getTime()) / 1000));
  return seconds < 60 ? `${seconds}s ago` : `${Math.floor(seconds / 60)}m ago`;
}

function openMaps(signals: TrafficSignal[], waypoint?: { lat: number; lng: number } | null) {
  if (signals.length < 2) return;
  window.open(buildGoogleMapsLink(
    { lat: signals[0].latitude, lng: signals[0].longitude },
    { lat: signals[signals.length - 1].latitude, lng: signals[signals.length - 1].longitude },
    waypoint,
  ), "_blank", "noopener,noreferrer");
}

function Toggle({ value, onChange, label }: { value: boolean; onChange: () => void; label: string }) {
  return (
    <button role="switch" aria-checked={value} aria-label={label} onClick={onChange}
      className={`relative h-8 w-14 shrink-0 rounded-full transition ${value ? "bg-cyan-400" : "bg-slate-300 dark:bg-slate-700"}`}>
      <span className={`absolute top-1 h-6 w-6 rounded-full bg-white shadow transition ${value ? "left-7" : "left-1"}`} />
    </button>
  );
}

function PhaseBadge({ phase, compact = false }: { phase: Phase; compact?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-bold tracking-wide ${compact ? "px-2.5 py-1 text-[10px]" : "px-3 py-1.5 text-xs"}`}
      style={{ color: phaseHex[phase], backgroundColor: `${phaseHex[phase]}18` }}>
      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: phaseHex[phase] }} />{phase}
    </span>
  );
}

function CongestionPill({ level }: { level: CongestionLevel }) {
  const classes = {
    FREE: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300",
    MODERATE: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
    HEAVY: "bg-red-500/15 text-red-600 dark:text-red-300",
  };
  return <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold tracking-wide ${classes[level]}`}>{level} TRAFFIC</span>;
}

function TrafficLight({ active, large = false }: { active: Phase; large?: boolean }) {
  return (
    <div className={`flex shrink-0 flex-col rounded-[22px] border border-white/10 bg-[#060a10] shadow-xl ${large ? "w-[74px] gap-3 p-3.5" : "w-12 gap-2 p-2"}`}>
      {PHASES.map((phase) => <span key={phase} className="aspect-square rounded-full border border-white/10"
        style={{ background: active === phase ? phaseHex[phase] : "#18212d", boxShadow: active === phase ? `0 0 24px ${phaseHex[phase]}99` : "none" }} />)}
    </div>
  );
}

function Header({ title, dark, setDark }: { title: string; dark: boolean; setDark: () => void }) {
  return (
    <header className="sticky top-0 z-30 bg-slate-50/90 px-5 pb-3 pt-[max(16px,env(safe-area-inset-top))] backdrop-blur-xl dark:bg-[#07111f]/90">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-cyan-400 text-slate-950"><Signal size={20} /></span>
          <span className="text-base font-bold">ReLy</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2.5 py-1 text-[9px] font-bold tracking-[.12em] text-amber-700 dark:text-amber-300">SIMULATED DATA</span>
          <button onClick={setDark} className="touch grid w-12 place-items-center rounded-full border bg-white dark:border-slate-700 dark:bg-slate-900" aria-label="Toggle theme">{dark ? <Sun size={18} /> : <Moon size={18} />}</button>
        </div>
      </div>
      <h1 className="text-[28px] font-bold tracking-tight">{title}</h1>
    </header>
  );
}

function TripScreen({ signals, now, onDrive }: { signals: TrafficSignal[]; now: number; onDrive: () => void }) {
  const red = signals.filter((s) => s.current_phase === "RED").length;
  const worst = signals.some((s) => s.congestion_level === "HEAVY") ? "HEAVY" : signals.some((s) => s.congestion_level === "MODERATE") ? "MODERATE" : "FREE";
  return (
    <div className="px-5 pb-7">
      <section className="mobile-card mb-4 p-4">
        <p className="mb-3 text-xs font-semibold uppercase tracking-[.15em] text-slate-500">Where to?</p>
        <div className="relative mb-3 pl-7 before:absolute before:bottom-5 before:left-[7px] before:top-5 before:w-px before:bg-slate-300 dark:before:bg-slate-700">
          <span className="absolute left-0 top-[18px] h-3.5 w-3.5 rounded-full border-4 border-cyan-400 bg-white dark:bg-slate-900" />
          <span className="absolute bottom-[18px] left-0 h-3.5 w-3.5 rounded-sm bg-red-500" />
          <input className="mobile-field mb-2" defaultValue="Tugu Junction" aria-label="Origin" />
          <input className="mobile-field" defaultValue="Kraton Yogyakarta" aria-label="Destination" />
        </div>
        <button className="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-cyan-400/10 px-3 text-sm font-semibold text-cyan-700 dark:text-cyan-300"><Zap size={16} /> Demo route: Tugu → Kraton</button>
      </section>

      <section className="mobile-card mb-5 overflow-hidden">
        <div className="border-b p-4 dark:border-slate-800"><p className="text-sm font-semibold">Route insight</p><p className="mt-1 text-xs text-slate-500">Approx. 4.2 km · 18 min</p></div>
        <div className="grid grid-cols-3 divide-x dark:divide-slate-800">
          <div className="p-4"><strong className="text-2xl">{signals.length}</strong><p className="mt-1 text-[10px] uppercase tracking-wide text-slate-500">Signals</p></div>
          <div className="p-4"><strong className="text-2xl text-red-500">{red}</strong><p className="mt-1 text-[10px] uppercase tracking-wide text-slate-500">Red now</p></div>
          <div className="p-4"><strong className="text-sm text-red-500">{worst}</strong><p className="mt-2 text-[10px] uppercase tracking-wide text-slate-500">Worst flow</p></div>
        </div>
      </section>

      <div className="mb-3 flex items-center justify-between"><h2 className="text-base font-semibold">Signals on your route</h2><span className="text-xs text-slate-500">In order</span></div>
      <section className="mobile-card mb-5 p-4">
        {signals.map((signal, index) => (
          <div key={signal.signal_id} className="relative flex gap-3 pb-5 last:pb-0">
            {index < signals.length - 1 && <span className="absolute left-[9px] top-5 h-full w-px bg-slate-200 dark:bg-slate-700" />}
            <span className="relative z-10 mt-1 h-5 w-5 shrink-0 rounded-full border-[5px] border-white dark:border-[#101d2d]" style={{ backgroundColor: phaseHex[signal.current_phase], boxShadow: `0 0 0 1px ${phaseHex[signal.current_phase]}55` }} />
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-2"><div><p className="truncate text-sm font-semibold">{signal.location}</p><p className="mt-0.5 font-mono text-[10px] text-slate-500">{signal.signal_id}</p></div><strong className="text-base tabular-nums">{secondsLeft(signal, now)}s</strong></div>
              <div className="mt-2 flex gap-2"><PhaseBadge phase={signal.current_phase} compact /><CongestionPill level={signal.congestion_level} /></div>
            </div>
          </div>
        ))}
      </section>
      <button onClick={onDrive} className="primary-action mb-3"><Navigation size={20} /> Start driving</button>
      <button onClick={() => openMaps(signals)} className="secondary-action"><ExternalLink size={18} /> Open in Google Maps</button>
    </div>
  );
}

function DriveScreen({ signals, now }: { signals: TrafficSignal[]; now: number }) {
  const next = signals[0];
  const after = signals[1];
  const [voice, setVoice] = useState(true);
  const [vibrate, setVibrate] = useState(true);
  if (!next) return <Empty title="No route loaded" text="Choose a route in Trip to start driving." />;
  const alert = next.current_phase === "RED" && next.congestion_level === "HEAVY";
  return (
    <div className="px-5 pb-7">
      <div className="mb-4 flex items-center gap-2 text-sm text-slate-400"><Navigation size={16} className="text-cyan-400" /> Driving to Kraton · 4.2 km</div>
      {alert && (
        <section className="mb-4 rounded-3xl border border-red-500/30 bg-gradient-to-br from-red-500/20 to-amber-500/10 p-5">
          <div className="mb-3 flex items-center gap-3"><span className="grid h-11 w-11 place-items-center rounded-2xl bg-red-500 text-white"><AlertTriangle size={24} /></span><div><p className="text-lg font-bold">Heavy traffic + red light ahead</p><p className="text-sm text-slate-400">A faster option is available</p></div></div>
          <p className="mb-4 rounded-xl bg-black/10 p-3 text-sm font-medium dark:bg-black/20">{next.detour?.label}</p>
          <button onClick={() => openMaps(signals, next.detour)} className="primary-action !bg-amber-400"><Route size={21} /> Take detour</button>
          <button className="mt-2 min-h-12 w-full text-sm font-semibold text-slate-400">Stay on route</button>
        </section>
      )}
      <section className="mb-4 rounded-[30px] border border-slate-800 bg-[#0a1421] p-6 text-white shadow-2xl">
        <div className="mb-7 flex items-start justify-between"><div><p className="mb-1 text-xs font-bold uppercase tracking-[.18em] text-cyan-300">Next signal · 350 m</p><p className="max-w-[210px] text-lg font-semibold">{next.location}</p></div><LocateFixed size={22} className="text-slate-500" /></div>
        <div className="flex items-center gap-6">
          <TrafficLight active={next.current_phase} large />
          <div><p className="text-2xl font-black tracking-wide" style={{ color: phaseHex[next.current_phase] }}>{next.current_phase}</p><p className="mt-1 text-[68px] font-bold leading-none tracking-[-.06em] tabular-nums">{secondsLeft(next, now)}<span className="ml-1 text-2xl text-slate-500">s</span></p><div className="mt-4"><CongestionPill level={next.congestion_level} /></div></div>
        </div>
      </section>
      {after && <section className="mobile-card mb-4 flex min-h-20 items-center gap-3 p-4"><span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">After<br />that</span><span className="h-8 w-px bg-slate-200 dark:bg-slate-700" /><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{after.location}</p><div className="mt-1 flex items-center gap-2"><PhaseBadge phase={after.current_phase} compact /><span className="text-xs text-slate-500">650 m</span></div></div><ChevronRight size={18} className="text-slate-500" /></section>}
      <section className="mobile-card divide-y dark:divide-slate-800">
        <div className="flex min-h-[68px] items-center gap-3 px-4"><Mic size={20} className="text-cyan-500" /><div className="flex-1"><p className="text-sm font-semibold">Voice alerts</p><p className="text-xs text-slate-500">Speak signal warnings</p></div><Toggle value={voice} onChange={() => setVoice(!voice)} label="Voice alerts" /></div>
        <div className="flex min-h-[68px] items-center gap-3 px-4"><Bell size={20} className="text-cyan-500" /><div className="flex-1"><p className="text-sm font-semibold">Vibration</p><p className="text-xs text-slate-500">Haptic warning nearby</p></div><Toggle value={vibrate} onChange={() => setVibrate(!vibrate)} label="Vibration alerts" /></div>
      </section>
    </div>
  );
}

function SignalsScreen({ signals, now, onSelect }: { signals: TrafficSignal[]; now: number; onSelect: (s: TrafficSignal) => void }) {
  const [query, setQuery] = useState("");
  const filtered = signals.filter((s) => `${s.signal_id} ${s.location}`.toLowerCase().includes(query.toLowerCase()));
  return (
    <div className="px-5 pb-7">
      <div className="relative mb-4"><Search className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" size={18} /><input className="mobile-field !h-13 !pl-11" placeholder="Search signals" value={query} onChange={(e) => setQuery(e.target.value)} /></div>
      <p className="mb-3 text-xs font-semibold uppercase tracking-[.14em] text-slate-500">{filtered.length} signals nearby</p>
      <div className="space-y-3">
        {filtered.map((signal) => (
          <button key={signal.signal_id} onClick={() => onSelect(signal)} className="mobile-card min-h-[124px] w-full p-4 text-left transition active:scale-[.99]">
            <div className="mb-3 flex items-start justify-between gap-2"><div className="min-w-0"><p className="truncate text-sm font-semibold">{signal.location}</p><p className="mt-1 font-mono text-[10px] text-slate-500">{signal.signal_id} · updated {age(signal.updated_at, now)}</p></div><ChevronRight className="shrink-0 text-slate-500" size={19} /></div>
            <div className="mb-3 flex items-center gap-2"><PhaseBadge phase={signal.current_phase} /><strong className="mr-auto tabular-nums">{secondsLeft(signal, now)}s</strong><CongestionPill level={signal.congestion_level} /></div>
            <div className="flex items-center gap-3"><span className="text-[10px] text-slate-500">Confidence</span><div className="h-1.5 flex-1 rounded-full bg-slate-200 dark:bg-slate-800"><div className="h-full rounded-full bg-cyan-400" style={{ width: `${signal.confidence_score * 100}%` }} /></div><span className="text-[10px] font-semibold">{Math.round(signal.confidence_score * 100)}%</span></div>
          </button>
        ))}
      </div>
      {!filtered.length && <Empty title="No signals found" text="Try a different ID or location." />}
    </div>
  );
}

function AdminScreen({ signals, mock, setMock, onAdd, onEdit, onDelete }: {
  signals: TrafficSignal[]; mock: boolean; setMock: () => void; onAdd: () => void;
  onEdit: (s: TrafficSignal) => void; onDelete: (s: TrafficSignal) => void;
}) {
  return (
    <div className="px-5 pb-24">
      <section className="mobile-card mb-5 flex min-h-[72px] items-center gap-3 p-4"><CircleGauge className="text-cyan-500" /><div className="flex-1"><p className="text-sm font-semibold">Use mock data</p><p className="text-xs text-slate-500">5-signal Yogyakarta demo route</p></div><Toggle value={mock} onChange={setMock} label="Use mock data" /></section>
      <div className="mb-3 flex items-center justify-between"><p className="text-xs font-semibold uppercase tracking-[.14em] text-slate-500">Signal registry</p><span className="text-xs text-slate-500">{signals.length} total</span></div>
      <div className="space-y-3">
        {signals.map((signal) => <div key={signal.signal_id} className="mobile-card flex min-h-[86px] items-center gap-3 p-4"><span className="h-3 w-3 rounded-full" style={{ background: phaseHex[signal.current_phase] }} /><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{signal.location}</p><p className="mt-1 font-mono text-[10px] text-slate-500">{signal.signal_id} · {signal.data_source}</p></div><button onClick={() => onEdit(signal)} className="touch grid w-12 place-items-center rounded-xl text-slate-500" aria-label="Edit"><Edit3 size={18} /></button><button onClick={() => onDelete(signal)} className="touch grid w-12 place-items-center rounded-xl text-red-500" aria-label="Delete"><Trash2 size={18} /></button></div>)}
      </div>
      {!signals.length && <Empty title="No signals registered yet" text="Add a signal to begin monitoring." />}
      <button onClick={onAdd} className="fixed bottom-[92px] right-[max(20px,calc((100vw-390px)/2+20px))] z-30 flex h-14 items-center gap-2 rounded-full bg-cyan-400 px-5 font-semibold text-slate-950 shadow-xl shadow-cyan-500/20"><Plus size={22} /> Add signal</button>
    </div>
  );
}

function Sheet({ children, onClose, title }: { children: React.ReactNode; onClose: () => void; title: string }) {
  return <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/70 backdrop-blur-sm" onMouseDown={(e) => e.target === e.currentTarget && onClose()}><section className="max-h-[92vh] w-full max-w-[430px] overflow-y-auto rounded-t-[30px] bg-white p-5 shadow-2xl dark:bg-[#0d1929]"><div className="mx-auto mb-5 h-1.5 w-12 rounded-full bg-slate-300 dark:bg-slate-700" /><div className="mb-5 flex items-center justify-between"><h2 className="text-xl font-bold">{title}</h2><button onClick={onClose} className="touch grid w-12 place-items-center rounded-full bg-slate-100 dark:bg-slate-800"><X size={20} /></button></div>{children}</section></div>;
}

function DetailSheet({ signal, signals, onClose }: { signal: TrafficSignal; signals: TrafficSignal[]; onClose: () => void }) {
  return <Sheet onClose={onClose} title="Signal detail"><div className="mb-5 flex items-center gap-4"><TrafficLight active={signal.current_phase} /><div><p className="text-lg font-semibold">{signal.location}</p><p className="mt-1 font-mono text-xs text-cyan-600 dark:text-cyan-300">{signal.signal_id}</p></div></div><div className="mb-5 grid grid-cols-2 gap-3"><div className="info-box"><span>Phase</span><PhaseBadge phase={signal.current_phase} /></div><div className="info-box"><span>Traffic</span><CongestionPill level={signal.congestion_level} /></div><div className="info-box"><span>Coordinates</span><strong className="text-xs">{signal.latitude.toFixed(4)}, {signal.longitude.toFixed(4)}</strong></div><div className="info-box"><span>Source</span><strong className="text-xs">{signal.data_source}</strong></div></div>{signal.detour && <div className="mb-5 rounded-2xl bg-amber-500/10 p-4"><p className="mb-1 text-xs font-bold uppercase tracking-wider text-amber-600 dark:text-amber-300">Available detour</p><p className="text-sm">{signal.detour.label}</p></div>}<button onClick={() => openMaps([signal, ...signals.filter((s) => s.signal_id !== signal.signal_id).slice(-1)])} className="primary-action"><ExternalLink size={18} /> Open in Google Maps</button></Sheet>;
}

function SignalForm({ editing, onClose, onSave }: { editing: TrafficSignal | null; onClose: () => void; onSave: (v: SignalInput) => Promise<void> }) {
  const [form, setForm] = useState<SignalInput>(editing ? { ...editing } : emptySignal);
  const [detour, setDetour] = useState(!!editing?.detour);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const set = <K extends keyof SignalInput>(key: K, value: SignalInput[K]) => setForm((old) => ({ ...old, [key]: value }));
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const err: Record<string, string> = {};
    if (!form.signal_id.trim()) err.signal_id = "ID is required";
    if (!form.location.trim()) err.location = "Location is required";
    if (form.latitude < -90 || form.latitude > 90) err.latitude = "Must be −90 to 90";
    if (form.longitude < -180 || form.longitude > 180) err.longitude = "Must be −180 to 180";
    if (form.remaining_seconds < 0) err.remaining_seconds = "Must be 0 or greater";
    if (form.confidence_score < 0 || form.confidence_score > 1) err.confidence_score = "Must be 0 to 1";
    if (detour && !form.detour?.label?.trim()) err.detour = "Detour label is required";
    if (detour && form.detour && (form.detour.lat < -90 || form.detour.lat > 90 || form.detour.lng < -180 || form.detour.lng > 180)) err.detour = "Detour coordinates are out of range";
    setErrors(err);
    if (!Object.keys(err).length) await onSave({ ...form, detour: detour ? form.detour ?? { label: "", lat: form.latitude, lng: form.longitude } : null });
  };
  const updateDetour = (key: "label" | "lat" | "lng", value: string | number) => set("detour", { label: form.detour?.label ?? "", lat: form.detour?.lat ?? form.latitude, lng: form.detour?.lng ?? form.longitude, [key]: value });
  return <Sheet onClose={onClose} title={editing ? "Edit signal" : "Add signal"}><form onSubmit={submit} className="space-y-4"><Field label="Signal ID" error={errors.signal_id}><input className="mobile-field font-mono" readOnly={!!editing} value={form.signal_id} onChange={(e) => set("signal_id", e.target.value.toUpperCase())} /></Field><Field label="Location" error={errors.location}><input className="mobile-field" value={form.location} onChange={(e) => set("location", e.target.value)} /></Field><div className="grid grid-cols-2 gap-3"><Field label="Latitude" error={errors.latitude}><input className="mobile-field" type="number" step=".0001" value={form.latitude} onChange={(e) => set("latitude", Number(e.target.value))} /></Field><Field label="Longitude" error={errors.longitude}><input className="mobile-field" type="number" step=".0001" value={form.longitude} onChange={(e) => set("longitude", Number(e.target.value))} /></Field></div><Segments label="Phase" values={PHASES} value={form.current_phase} onChange={(v) => set("current_phase", v)} /><Field label="Remaining seconds" error={errors.remaining_seconds}><input className="mobile-field" type="number" min="0" value={form.remaining_seconds} onChange={(e) => set("remaining_seconds", Number(e.target.value))} /></Field><Field label={`Confidence · ${form.confidence_score.toFixed(2)}`} error={errors.confidence_score}><input className="h-12 w-full accent-cyan-400" type="range" min="0" max="1" step=".01" value={form.confidence_score} onChange={(e) => set("confidence_score", Number(e.target.value))} /></Field><Segments label="Congestion" values={CONGESTION} value={form.congestion_level} onChange={(v) => set("congestion_level", v)} /><Field label="Data source"><select className="mobile-field" value={form.data_source} onChange={(e) => set("data_source", e.target.value as DataSource)}><option>SIMULATOR</option><option>MANUAL</option></select></Field><div className="mobile-card p-4"><div className="flex min-h-12 items-center"><div className="flex-1"><p className="text-sm font-semibold">Optional detour</p><p className="text-xs text-slate-500">Add a suggested side street</p></div><Toggle value={detour} onChange={() => setDetour(!detour)} label="Optional detour" /></div>{detour && <div className="mt-3 space-y-3"><input className="mobile-field" placeholder="Detour instruction" value={form.detour?.label ?? ""} onChange={(e) => updateDetour("label", e.target.value)} />{errors.detour && <p className="text-xs text-red-500">{errors.detour}</p>}<div className="grid grid-cols-2 gap-3"><input className="mobile-field" type="number" step=".0001" placeholder="Latitude" value={form.detour?.lat ?? form.latitude} onChange={(e) => updateDetour("lat", Number(e.target.value))} /><input className="mobile-field" type="number" step=".0001" placeholder="Longitude" value={form.detour?.lng ?? form.longitude} onChange={(e) => updateDetour("lng", Number(e.target.value))} /></div></div>}</div><button className="primary-action">{editing ? "Save changes" : "Add signal"}</button></form></Sheet>;
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return <label className="block"><span className="mb-1.5 block text-xs font-semibold text-slate-500">{label}</span>{children}{error && <span className="mt-1 block text-xs text-red-500">{error}</span>}</label>;
}

function Segments<T extends string>({ label, values, value, onChange }: { label: string; values: readonly T[]; value: T; onChange: (v: T) => void }) {
  return <fieldset><legend className="mb-1.5 text-xs font-semibold text-slate-500">{label}</legend><div className="grid grid-cols-3 gap-2">{values.map((v) => <button key={v} type="button" onClick={() => onChange(v)} className={`min-h-12 rounded-xl border px-2 text-xs font-bold ${value === v ? "border-cyan-400 bg-cyan-400/10 text-cyan-600 dark:text-cyan-300" : "bg-slate-50 text-slate-500 dark:border-slate-700 dark:bg-slate-900"}`}>{v}</button>)}</div></fieldset>;
}

function Empty({ title, text }: { title: string; text: string }) {
  return <div className="py-14 text-center"><span className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-slate-200 text-slate-500 dark:bg-slate-800"><Map size={24} /></span><p className="font-semibold">{title}</p><p className="mx-auto mt-1 max-w-[250px] text-sm text-slate-500">{text}</p></div>;
}

function App() {
  const [tab, setTab] = useState<Tab>("trip");
  const [signals, setSignals] = useState<TrafficSignal[]>([]);
  const [mock, setMock] = useState(true);
  const [dark, setDark] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());
  const [detail, setDetail] = useState<TrafficSignal | null>(null);
  const [editing, setEditing] = useState<TrafficSignal | "new" | null>(null);
  const [deleting, setDeleting] = useState<TrafficSignal | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toast = (kind: Toast["kind"], text: string) => { const id = Date.now(); setToasts((v) => [...v, { id, kind, text }]); window.setTimeout(() => setToasts((v) => v.filter((t) => t.id !== id)), 3000); };
  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError("");
    try {
      if (mock) { await new Promise((r) => setTimeout(r, 500)); setSignals(MOCK_SIGNALS); }
      else setSignals(await api.listSignals());
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to connect"); }
    finally { if (!silent) setLoading(false); }
  }, [mock]);
  useEffect(() => { void load(); }, [load]);
  // API mode: refresh every 15 s in the background (simulator updates arrive on phase changes).
  useEffect(() => {
    if (mock) return;
    const timer = window.setInterval(() => { void load(true); }, 15000);
    return () => clearInterval(timer);
  }, [mock, load]);
  useEffect(() => { document.documentElement.classList.toggle("dark", dark); }, [dark]);
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  const title = { trip: "Plan your trip", drive: "Drive", signals: "Traffic signals", admin: "Admin" }[tab];
  const save = async (body: SignalInput) => {
    try {
      if (editing && editing !== "new") {
        const updated = mock ? { ...body, updated_at: new Date().toISOString() } : await api.updateSignal(editing.signal_id, body);
        setSignals((v) => v.map((s) => s.signal_id === updated.signal_id ? updated : s)); toast("ok", "Signal updated");
      } else {
        const created = mock ? { ...body, updated_at: new Date().toISOString() } : await api.createSignal(body);
        setSignals((v) => [...v, created]); toast("ok", "Signal added");
      }
      setEditing(null);
    } catch (e) { toast("error", e instanceof Error ? e.message : "Could not save signal"); }
  };
  const remove = async () => {
    if (!deleting) return;
    try { if (!mock) await api.deleteSignal(deleting.signal_id); setSignals((v) => v.filter((s) => s.signal_id !== deleting.signal_id)); setDeleting(null); toast("ok", "Signal deleted"); }
    catch (e) { toast("error", e instanceof Error ? e.message : "Could not delete signal"); }
  };
  const nav = [
    { id: "trip" as const, label: "Trip", icon: Route }, { id: "drive" as const, label: "Drive", icon: Navigation },
    { id: "signals" as const, label: "Signals", icon: Signal }, { id: "admin" as const, label: "Admin", icon: Settings2 },
  ];
  return (
    <div className="min-h-screen bg-slate-200 dark:bg-[#030812]">
      <div className="relative mx-auto min-h-screen w-full max-w-[430px] overflow-x-hidden bg-slate-50 pb-[calc(82px+env(safe-area-inset-bottom))] shadow-2xl dark:bg-[#07111f]">
        <Header title={title} dark={dark} setDark={() => setDark(!dark)} />
        {loading ? <div className="space-y-4 px-5">{[1,2,3].map((i) => <div key={i} className="h-32 animate-pulse rounded-3xl bg-slate-200 dark:bg-slate-800" />)}</div> : error ? <div className="px-5"><Empty title="You're offline" text={error} /><button onClick={() => void load()} className="primary-action"><RefreshCw size={18} /> Retry</button></div> : <>
          {tab === "trip" && <TripScreen signals={signals} now={now} onDrive={() => setTab("drive")} />}
          {tab === "drive" && <DriveScreen signals={signals} now={now} />}
          {tab === "signals" && <SignalsScreen signals={signals} now={now} onSelect={setDetail} />}
          {tab === "admin" && <AdminScreen signals={signals} mock={mock} setMock={() => setMock(!mock)} onAdd={() => setEditing("new")} onEdit={setEditing} onDelete={setDeleting} />}
        </>}
        <nav className="fixed bottom-0 z-40 flex h-[calc(72px+env(safe-area-inset-bottom))] w-full max-w-[430px] items-start justify-around border-t bg-white/95 px-2 pt-2 backdrop-blur-xl dark:border-slate-800 dark:bg-[#0a1523]/95">
          {nav.map(({ id, label, icon: Icon }) => <button key={id} onClick={() => setTab(id)} className={`flex min-h-[58px] min-w-[70px] flex-col items-center justify-center gap-1 rounded-2xl text-[10px] font-semibold transition ${tab === id ? "bg-cyan-400/10 text-cyan-600 dark:text-cyan-300" : "text-slate-500"}`}><Icon size={21} strokeWidth={tab === id ? 2.5 : 2} />{label}</button>)}
        </nav>
      </div>
      {detail && <DetailSheet signal={detail} signals={signals} onClose={() => setDetail(null)} />}
      {editing && <SignalForm editing={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSave={save} />}
      {deleting && <Sheet onClose={() => setDeleting(null)} title="Delete signal?"><div className="mb-5 rounded-2xl bg-red-500/10 p-4 text-sm">Remove <strong className="font-mono">{deleting.signal_id}</strong>? This cannot be undone.</div><button onClick={() => void remove()} className="primary-action !bg-red-500 !text-white"><Trash2 size={18} /> Delete signal</button><button onClick={() => setDeleting(null)} className="secondary-action mt-3">Cancel</button></Sheet>}
      <div className="fixed right-5 top-5 z-[70] space-y-2">{toasts.map((t) => <div key={t.id} className={`flex max-w-[340px] items-center gap-2 rounded-2xl p-4 text-sm font-semibold text-white shadow-xl ${t.kind === "ok" ? "bg-emerald-600" : "bg-red-600"}`}>{t.kind === "ok" ? <Check size={18} /> : <AlertTriangle size={18} />}{t.text}</div>)}</div>
    </div>
  );
}

export default App;
