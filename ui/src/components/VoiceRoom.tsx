/**
 * VoiceRoom — the realtime voice surface.
 *
 * Lifecycle:
 *   1. User clicks "Start" → POST /voice/token → receive {url, token, room}.
 *   2. Connect to LiveKit Cloud via `livekit-client`.
 *   3. Publish the local mic track.
 *   4. Wire two WebAudio AnalyserNodes:
 *        • local mic       → drives the "listening" bubble amplitude
 *        • agent audio out → drives the "speaking"  bubble amplitude
 *   5. Translate LiveKit + agent state events into a BubbleState.
 *
 * No backend changes here — the LiveKit voice worker (src/voice/run.py)
 * is dispatched into the room automatically by LiveKit Cloud and runs
 * the LangGraph orchestrator under the hood.
 *
 * Browser support: requires a Chromium-based browser for reliable
 * AudioContext + getUserMedia behaviour. Safari works but needs an
 * explicit user gesture to resume the AudioContext.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ConnectionState,
  LocalAudioTrack,
  LocalTrackPublication,
  RemoteAudioTrack,
  Room,
  RoomEvent,
  Track,
} from "livekit-client";
import { Mic, MicOff, PhoneOff } from "lucide-react";

import VoiceBubble, { type BubbleState } from "./VoiceBubble";

// Token endpoint exposed by FastAPI (`src/api/routers/voice.py`).
const TOKEN_ENDPOINT = "/api/v1/voice/token";

interface TokenResponse {
  url: string;
  token: string;
  room: string;
  identity: string;
}

async function fetchToken(userId?: string, sessionId?: string): Promise<TokenResponse> {
  const res = await fetch(TOKEN_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId ?? null, room: sessionId ?? null }),
  });
  if (!res.ok) {
    throw new Error(`Token request failed: ${res.status} ${await res.text()}`);
  }
  return res.json();
}

/** Attach an AnalyserNode to a MediaStreamTrack and call `onLevel` each frame. */
function attachAnalyser(
  ctx: AudioContext,
  track: MediaStreamTrack,
  onLevel: (level: number) => void,
): () => void {
  const stream = new MediaStream([track]);
  const source = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  analyser.smoothingTimeConstant = 0.6;
  source.connect(analyser);

  const data = new Uint8Array(analyser.frequencyBinCount);
  let raf = 0;
  let cancelled = false;
  const tick = () => {
    if (cancelled) return;
    analyser.getByteTimeDomainData(data);
    // RMS over [-1, 1] (data is 0..255 centred at 128).
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / data.length);
    // Light gain — typical speech RMS sits around 0.05–0.2.
    onLevel(Math.min(1, rms * 3.5));
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);

  return () => {
    cancelled = true;
    cancelAnimationFrame(raf);
    try { source.disconnect(); } catch { /* noop */ }
  };
}

interface VoiceRoomProps {
  userId?: string;
  sessionId?: string;
  onClose?: () => void;
  autoStart?: boolean;
}

export function VoiceRoom({ userId, sessionId, onClose, autoStart }: VoiceRoomProps) {
  const [bubbleState, setBubbleState] = useState<BubbleState>("idle");
  const [amplitude, setAmplitude] = useState(0);
  const [muted, setMuted] = useState(false);
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState("Tap to start the call");
  const [latencyHud, setLatencyHud] = useState<{ first?: number; total?: number }>({});

  const roomRef = useRef<Room | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const cleanupsRef = useRef<Array<() => void>>([]);
  // The bubble is driven by *whichever side is currently active*. We keep
  // both levels in refs and pick the right one based on bubbleState.
  const userLevelRef = useRef(0);
  const agentLevelRef = useRef(0);
  const lastUserSpeakAtRef = useRef(0);

  // Run a single RAF loop that picks the amplitude source based on state.
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      setAmplitude((prev) => {
        const target =
          bubbleState === "speaking"
            ? agentLevelRef.current
            : bubbleState === "listening"
            ? userLevelRef.current
            : 0;
        // Lerp toward target — caller still spring-smooths inside VoiceBubble.
        return prev + (target - prev) * 0.35;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [bubbleState]);


  const teardown = useCallback(() => {
    cleanupsRef.current.forEach((fn) => fn());
    cleanupsRef.current = [];
    roomRef.current?.disconnect().catch(() => {});
    roomRef.current = null;
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
    setConnected(false);
    setBubbleState("idle");
    setStatus("Disconnected");
  }, []);

  const connectingRef = useRef(false);

  const start = useCallback(async () => {
    if (connectingRef.current) return;
    connectingRef.current = true;
    try {
      setStatus("Requesting access...");
      setBubbleState("thinking");

      console.log("[VoiceRoom] requesting token...");
      const { url, token } = await fetchToken(userId, sessionId);
      console.log("[VoiceRoom] got token, connecting to", url);

      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
        // Tighter audio settings for a phone-call feel.
        audioCaptureDefaults: {
          autoGainControl: true,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      roomRef.current = room;

      const ctx = new AudioContext();
      audioCtxRef.current = ctx;
      // Safari needs an explicit resume tied to a user gesture.
      // Do not await this, as it may hang forever if the browser blocks it without a user gesture.
      if (ctx.state === "suspended") {
        ctx.resume().catch(err => console.warn("AudioContext resume blocked:", err));
      }

      // ── Wire LiveKit events BEFORE connect so we don't miss any ──
      room.on(RoomEvent.ConnectionStateChanged, (state) => {
        if (state === ConnectionState.Connected) {
          setConnected(true);
          setStatus("Connected — say hi");
          setBubbleState("listening");
        } else if (state === ConnectionState.Disconnected) {
          setConnected(false);
          setBubbleState("idle");
        }
      });

      // Agent (or any remote) speaking → bubble goes green and reacts.
      room.on(RoomEvent.TrackSubscribed, (track, _pub, _participant) => {
        if (track.kind !== Track.Kind.Audio) return;
        const audioTrack = track as RemoteAudioTrack;
        // Pipe the agent's audio to speakers.
        audioTrack.attach();
        const mediaTrack = audioTrack.mediaStreamTrack;
        if (mediaTrack && ctx) {
          const stop = attachAnalyser(ctx, mediaTrack, (lvl) => {
            agentLevelRef.current = lvl;
            // Heuristic: if agent is producing audio and the user hasn't
            // spoken in the last 600ms, we're in "speaking" state.
            if (lvl > 0.04 && Date.now() - lastUserSpeakAtRef.current > 600) {
              setBubbleState("speaking");
            }
          });
          cleanupsRef.current.push(stop);
        }
      });

      // Active-speaker change is the cleanest signal LiveKit emits.
      room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        const local = room.localParticipant;
        const userSpeaking = speakers.some((s) => s.identity === local.identity);
        const agentSpeaking = speakers.some((s) => s.identity !== local.identity);
        if (userSpeaking) {
          lastUserSpeakAtRef.current = Date.now();
          setBubbleState("listening");
        } else if (agentSpeaking) {
          setBubbleState("speaking");
        } else if (connected) {
          // Neither side speaking → idle listening pose.
          setBubbleState((s) => (s === "thinking" ? s : "listening"));
        }
      });

      // Latency telemetry from the voice worker (optional, future).
      room.on(RoomEvent.DataReceived, (payload) => {
        try {
          const text = new TextDecoder().decode(payload);
          const msg = JSON.parse(text);
          if (msg.type === "latency") {
            setLatencyHud({ first: msg.first_token_ms, total: msg.total_ms });
          }
        } catch {
          /* not JSON, ignore */
        }
      });

      room.on(RoomEvent.Disconnected, teardown);

      setStatus("Connecting...");
      await room.connect(url, token);
      console.log("[VoiceRoom] connected to room", room.name);

      // Wire the analyser when our local mic track gets published.
      // (LocalTrackPublished fires AFTER setMicrophoneEnabled below.)
      const attachLocalMic = (pub: LocalTrackPublication) => {
        if (pub.kind !== Track.Kind.Audio) return;
        const localTrack = pub.track as LocalAudioTrack | undefined;
        const localMedia = localTrack?.mediaStreamTrack;
        if (localMedia && ctx) {
          console.log("[VoiceRoom] attaching analyser to local mic");
          const stop = attachAnalyser(ctx, localMedia, (lvl) => {
            userLevelRef.current = lvl;
            if (lvl > 0.06) {
              lastUserSpeakAtRef.current = Date.now();
            }
          });
          cleanupsRef.current.push(stop);
        }
      };

      room.on(RoomEvent.LocalTrackPublished, attachLocalMic);

      // Publish the local mic — this will trigger LocalTrackPublished.
      try {
        await room.localParticipant.setMicrophoneEnabled(true);
        console.log("[VoiceRoom] mic published");
      } catch (micErr) {
        console.warn("[VoiceRoom] Auto-mic blocked by browser, user must unmute manually", micErr);
        setMuted(true);
      }

      // Fallback: if the publication already exists (no event fired), grab
      // it now via the v2 `trackPublications` Map.
      room.localParticipant.trackPublications.forEach((pub) => {
        if (pub.kind === Track.Kind.Audio && pub.track) {
          attachLocalMic(pub as LocalTrackPublication);
        }
      });
    } catch (err) {
      console.error("[VoiceRoom] start failed:", err);
      const msg = (err as Error)?.message || String(err);
      // Partial cleanup that does NOT call teardown() — teardown sets
      // status to "Disconnected" and would clobber our error message.
      cleanupsRef.current.forEach((fn) => fn());
      cleanupsRef.current = [];
      await roomRef.current?.disconnect().catch(() => {});
      roomRef.current = null;
      await audioCtxRef.current?.close().catch(() => {});
      audioCtxRef.current = null;
      setConnected(false);
      setStatus(`Error: ${msg}`);
      setBubbleState("error");
    } finally {
      connectingRef.current = false;
    }
  }, [userId, teardown, connected, sessionId]);

  const toggleMute = useCallback(async () => {
    const room = roomRef.current;
    if (!room) return;
    const next = !muted;
    await room.localParticipant.setMicrophoneEnabled(!next);
    setMuted(next);
  }, [muted]);

  useEffect(() => {
    if (autoStart && !connected && status === "Tap to start the call") {
      start();
    }
  }, [autoStart, connected, start, status]);

  useEffect(() => () => teardown(), [teardown]);

  return (
    <div className="voice-room-container">
      <VoiceBubble
        state={bubbleState}
        amplitude={amplitude}
        label={
          bubbleState === "listening"
            ? "LISTENING"
            : bubbleState === "speaking"
            ? "AGENT SPEAKING"
            : bubbleState === "thinking"
            ? "THINKING"
            : bubbleState === "error"
            ? "ERROR"
            : "ZUUSWARM-AI VOICE ASSISTANT"
        }
      />
      <p className="voice-status">{status}</p>

      {latencyHud.first !== undefined && (
        <p className="voice-hud">
          first&nbsp;tok&nbsp;{latencyHud.first}ms · total&nbsp;{latencyHud.total}ms
        </p>
      )}

      <div className="voice-controls">
        {!connected ? (
          <button
            onClick={start}
            className="voice-btn btn-start"
          >
            Start call
          </button>
        ) : (
          <>
            <button
              onClick={toggleMute}
              className="voice-btn btn-mute"
              title={muted ? "Unmute" : "Mute"}
            >
              {muted ? <MicOff size={20} /> : <Mic size={20} />}
            </button>
            <button
              onClick={() => { teardown(); onClose?.(); }}
              className="voice-btn btn-end"
              title="End call"
            >
              <PhoneOff size={20} />
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default VoiceRoom;
