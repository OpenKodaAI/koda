"use client";

import type { CSSProperties, RefObject } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTexture } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";

export type AgentState = null | "thinking" | "listening" | "talking";

export type OrbColorPair = { light: string; dark: string };

const PERLIN_NOISE_TEXTURE_URL = "/textures/perlin-noise.png";

const MAX_AGENT_COLORS = 8;

interface OrbProps {
  colors?: [string, string];
  // Multi-agent palette: each entry is the agent's lightened/darkened tonal
  // pair. When more than one entry is provided the shader divides the orb
  // into N angular wedges with smooth blending between adjacent agents, so
  // every selected agent's color is visible inside a single animated orb.
  // Falls back to `colors` (legacy single agent) when omitted.
  agentColors?: OrbColorPair[];
  colorsRef?: RefObject<[string, string]>;
  resizeDebounce?: number;
  seed?: number;
  agentState?: AgentState;
  volumeMode?: "auto" | "manual";
  manualInput?: number;
  manualOutput?: number;
  inputVolumeRef?: RefObject<number>;
  outputVolumeRef?: RefObject<number>;
  getInputVolume?: () => number;
  getOutputVolume?: () => number;
  className?: string;
  style?: CSSProperties;
}

export function Orb({
  colors = ["#CADCFC", "#A0B9D1"],
  agentColors,
  colorsRef,
  resizeDebounce = 100,
  seed,
  agentState = null,
  volumeMode = "auto",
  manualInput,
  manualOutput,
  inputVolumeRef,
  outputVolumeRef,
  getInputVolume,
  getOutputVolume,
  className,
  style,
}: OrbProps) {
  return (
    <div className={className ?? "relative h-full w-full"} style={style}>
      <Canvas
        resize={{ debounce: resizeDebounce }}
        gl={{
          alpha: true,
          antialias: true,
          premultipliedAlpha: true,
        }}
      >
        <Scene
          colors={colors}
          agentColors={agentColors}
          colorsRef={colorsRef}
          seed={seed}
          agentState={agentState}
          volumeMode={volumeMode}
          manualInput={manualInput}
          manualOutput={manualOutput}
          inputVolumeRef={inputVolumeRef}
          outputVolumeRef={outputVolumeRef}
          getInputVolume={getInputVolume}
          getOutputVolume={getOutputVolume}
        />
      </Canvas>
    </div>
  );
}

interface SceneProps {
  colors: [string, string];
  agentColors?: OrbColorPair[];
  colorsRef?: RefObject<[string, string]>;
  seed?: number;
  agentState: AgentState;
  volumeMode: "auto" | "manual";
  manualInput?: number;
  manualOutput?: number;
  inputVolumeRef?: RefObject<number>;
  outputVolumeRef?: RefObject<number>;
  getInputVolume?: () => number;
  getOutputVolume?: () => number;
}

function Scene({
  colors,
  agentColors,
  colorsRef,
  seed,
  agentState,
  volumeMode,
  manualInput,
  manualOutput,
  inputVolumeRef,
  outputVolumeRef,
  getInputVolume,
  getOutputVolume,
}: SceneProps) {
  const { gl } = useThree();
  const circleRef =
    useRef<THREE.Mesh<THREE.CircleGeometry, THREE.ShaderMaterial>>(null);
  const initialColorsRef = useRef<[string, string]>(colors);
  const targetColor1Ref = useRef(new THREE.Color(colors[0]));
  const targetColor2Ref = useRef(new THREE.Color(colors[1]));
  const animSpeedRef = useRef(0.1);
  const perlinNoiseTexture = useTexture(PERLIN_NOISE_TEXTURE_URL);

  const agentRef = useRef<AgentState>(agentState);
  const modeRef = useRef<"auto" | "manual">(volumeMode);
  const manualInRef = useRef<number>(manualInput ?? 0);
  const manualOutRef = useRef<number>(manualOutput ?? 0);
  const curInRef = useRef(0);
  const curOutRef = useRef(0);

  useEffect(() => {
    agentRef.current = agentState;
  }, [agentState]);

  useEffect(() => {
    modeRef.current = volumeMode;
  }, [volumeMode]);

  useEffect(() => {
    manualInRef.current = clamp01(
      manualInput ?? inputVolumeRef?.current ?? getInputVolume?.() ?? 0,
    );
  }, [manualInput, inputVolumeRef, getInputVolume]);

  useEffect(() => {
    manualOutRef.current = clamp01(
      manualOutput ?? outputVolumeRef?.current ?? getOutputVolume?.() ?? 0,
    );
  }, [manualOutput, outputVolumeRef, getOutputVolume]);

  const [resolvedSeed] = useState(
    () => seed ?? Math.floor(Math.random() * 2 ** 32),
  );
  const offsets = useMemo(() => {
    const random = splitmix32(resolvedSeed);
    return new Float32Array(
      Array.from({ length: 7 }, () => random() * Math.PI * 2),
    );
  }, [resolvedSeed]);

  useEffect(() => {
    targetColor1Ref.current = new THREE.Color(colors[0]);
    targetColor2Ref.current = new THREE.Color(colors[1]);
  }, [colors]);

  // Build the multi-agent palette: first slot is the legacy single-agent pair
  // (so single-agent rendering is unchanged), additional slots come from the
  // explicit agentColors array. Padded out to MAX_AGENT_COLORS so the shader's
  // fixed-size uniform array always has valid colors at every index.
  const palette = useMemo(() => {
    const pairs: OrbColorPair[] =
      agentColors && agentColors.length > 0
        ? agentColors
        : [{ light: colors[0], dark: colors[1] }];
    const lights: THREE.Color[] = [];
    const darks: THREE.Color[] = [];
    for (let i = 0; i < MAX_AGENT_COLORS; i += 1) {
      const pair = pairs[i % pairs.length];
      lights.push(new THREE.Color(pair.light));
      darks.push(new THREE.Color(pair.dark));
    }
    return { lights, darks, count: Math.min(pairs.length, MAX_AGENT_COLORS) };
  }, [agentColors, colors]);

  useEffect(() => {
    if (!circleRef.current) return;
    const u = circleRef.current.material.uniforms;
    u.uAgentColorsLight.value = palette.lights;
    u.uAgentColorsDark.value = palette.darks;
    u.uAgentColorCount.value = palette.count;
  }, [palette]);

  // Read the page canvas color so the shader's "gap" extreme (color1 in dark
  // mode, color4 in light mode) is set to the same color the wrapper paints
  // behind the canvas. This eliminates the hard pie-slice wedges that appear
  // when the shader's pure black/white background contrasts with the theme bg.
  useEffect(() => {
    const apply = () => {
      if (!circleRef.current) return;
      const isDark = document.documentElement.classList.contains("dark");
      const u = circleRef.current.material.uniforms;
      u.uInverted.value = isDark ? 1 : 0;
      const css = getComputedStyle(document.documentElement)
        .getPropertyValue("--canvas")
        .trim();
      if (css) {
        u.uCanvasBg.value.set(css);
      }
    };
    apply();
    const observer = new MutationObserver(apply);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  useFrame((_, delta: number) => {
    /* eslint-disable react-hooks/immutability --
       r3f drives shader uniforms by mutating the material's uniforms map every
       frame. This is the canonical render-loop pattern; the React compiler
       rule is intentionally relaxed for this idiomatic GL bridge. */
    const mat = circleRef.current?.material;
    if (!mat) return;
    const live = colorsRef?.current;
    if (live) {
      if (live[0]) targetColor1Ref.current.set(live[0]);
      if (live[1]) targetColor2Ref.current.set(live[1]);
    }
    const u = mat.uniforms;
    u.uTime.value += delta * 0.5;

    if (u.uOpacity.value < 1) {
      u.uOpacity.value = Math.min(1, u.uOpacity.value + delta * 2);
    }

    let targetIn = 0;
    let targetOut = 0.3;
    if (modeRef.current === "manual") {
      targetIn = clamp01(
        manualInput ?? inputVolumeRef?.current ?? getInputVolume?.() ?? 0,
      );
      targetOut = clamp01(
        manualOutput ?? outputVolumeRef?.current ?? getOutputVolume?.() ?? 0,
      );
    } else {
      const t = u.uTime.value * 2;
      if (agentRef.current === null) {
        targetIn = 0;
        targetOut = 0.3;
      } else if (agentRef.current === "listening") {
        targetIn = clamp01(0.55 + Math.sin(t * 3.2) * 0.35);
        targetOut = 0.45;
      } else if (agentRef.current === "talking") {
        targetIn = clamp01(0.65 + Math.sin(t * 4.8) * 0.22);
        targetOut = clamp01(0.75 + Math.sin(t * 3.6) * 0.22);
      } else {
        const base = 0.38 + 0.07 * Math.sin(t * 0.7);
        const wander = 0.05 * Math.sin(t * 2.1) * Math.sin(t * 0.37 + 1.2);
        targetIn = clamp01(base + wander);
        targetOut = clamp01(0.48 + 0.12 * Math.sin(t * 1.05 + 0.6));
      }
    }

    curInRef.current += (targetIn - curInRef.current) * 0.2;
    curOutRef.current += (targetOut - curOutRef.current) * 0.2;

    const targetSpeed = 0.1 + (1 - Math.pow(curOutRef.current - 1, 2)) * 0.9;
    animSpeedRef.current += (targetSpeed - animSpeedRef.current) * 0.12;

    u.uAnimation.value += delta * animSpeedRef.current;
    u.uInputVolume.value = curInRef.current;
    u.uOutputVolume.value = curOutRef.current;
    u.uColor1.value.lerp(targetColor1Ref.current, 0.08);
    u.uColor2.value.lerp(targetColor2Ref.current, 0.08);
    /* eslint-enable react-hooks/immutability */
  });

  useEffect(() => {
    const canvas = gl.domElement;
    const onContextLost = (event: Event) => {
      event.preventDefault();
      setTimeout(() => {
        gl.forceContextRestore();
      }, 1);
    };
    canvas.addEventListener("webglcontextlost", onContextLost, false);
    return () =>
      canvas.removeEventListener("webglcontextlost", onContextLost, false);
  }, [gl]);

  const uniforms = useMemo(() => {
    /* eslint-disable react-hooks/immutability --
       The Perlin texture is sampled with coordinates that exceed [0,1] (the
       flow/ring lookups use `uTime` directly). Without RepeatWrapping the
       sampler clamps and the noise pattern freezes, which manifests as a
       static pie-slice gradient instead of a smooth orb. Configure the
       wrap mode synchronously here so the GPU's first upload uses it. */
    perlinNoiseTexture.wrapS = THREE.RepeatWrapping;
    perlinNoiseTexture.wrapT = THREE.RepeatWrapping;
    /* eslint-enable react-hooks/immutability */
    const initialIsDark =
      typeof document !== "undefined" &&
      document.documentElement.classList.contains("dark");
    const initialCanvasCss =
      typeof document !== "undefined"
        ? getComputedStyle(document.documentElement)
            .getPropertyValue("--canvas")
            .trim()
        : "";
    const initialCanvas = new THREE.Color(
      initialCanvasCss || (initialIsDark ? "#0C0C0C" : "#f9f7f3"),
    );
    const initialLights: THREE.Color[] = [];
    const initialDarks: THREE.Color[] = [];
    for (let i = 0; i < MAX_AGENT_COLORS; i += 1) {
      initialLights.push(new THREE.Color(initialColorsRef.current[0]));
      initialDarks.push(new THREE.Color(initialColorsRef.current[1]));
    }
    return {
      uColor1: new THREE.Uniform(new THREE.Color(initialColorsRef.current[0])),
      uColor2: new THREE.Uniform(new THREE.Color(initialColorsRef.current[1])),
      uAgentColorsLight: { value: initialLights },
      uAgentColorsDark: { value: initialDarks },
      uAgentColorCount: { value: 1 },
      uOffsets: { value: offsets },
      uPerlinTexture: new THREE.Uniform(perlinNoiseTexture),
      uTime: new THREE.Uniform(0),
      uAnimation: new THREE.Uniform(0.1),
      uInverted: new THREE.Uniform(initialIsDark ? 1 : 0),
      uCanvasBg: new THREE.Uniform(initialCanvas),
      uInputVolume: new THREE.Uniform(0),
      uOutputVolume: new THREE.Uniform(0),
      uOpacity: new THREE.Uniform(0),
    };
  }, [perlinNoiseTexture, offsets]);

  return (
    <mesh ref={circleRef}>
      <circleGeometry args={[3.5, 64]} />
      <shaderMaterial
        uniforms={uniforms}
        fragmentShader={fragmentShader}
        vertexShader={vertexShader}
        transparent
      />
    </mesh>
  );
}

function splitmix32(a: number) {
  return function () {
    a |= 0;
    a = (a + 0x9e3779b9) | 0;
    let t = a ^ (a >>> 16);
    t = Math.imul(t, 0x21f0aaad);
    t = t ^ (t >>> 15);
    t = Math.imul(t, 0x735a2d97);
    return ((t = t ^ (t >>> 15)) >>> 0) / 4294967296;
  };
}

function clamp01(n: number) {
  if (!Number.isFinite(n)) return 0;
  return Math.min(1, Math.max(0, n));
}

const vertexShader = /* glsl */ `
uniform float uTime;
uniform sampler2D uPerlinTexture;
varying vec2 vUv;

void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const fragmentShader = /* glsl */ `
uniform float uTime;
uniform float uAnimation;
uniform float uInverted;
uniform float uOffsets[7];
uniform vec3 uColor1;
uniform vec3 uColor2;
uniform vec3 uCanvasBg;
uniform vec3 uAgentColorsLight[8];
uniform vec3 uAgentColorsDark[8];
uniform int uAgentColorCount;
uniform float uInputVolume;
uniform float uOutputVolume;
uniform float uOpacity;
uniform sampler2D uPerlinTexture;
varying vec2 vUv;

const float PI = 3.14159265358979323846;

bool drawOval(vec2 polarUv, vec2 polarCenter, float a, float b, bool reverseGradient, float softness, out vec4 color) {
    vec2 p = polarUv - polarCenter;
    float oval = (p.x * p.x) / (a * a) + (p.y * p.y) / (b * b);

    float edge = smoothstep(1.0, 1.0 - softness, oval);

    if (edge > 0.0) {
        float gradient = reverseGradient ? (1.0 - (p.x / a + 1.0) / 2.0) : ((p.x / a + 1.0) / 2.0);
        gradient = mix(0.5, gradient, 0.1);
        color = vec4(vec3(gradient), 0.85 * edge);
        return true;
    }
    return false;
}

vec3 colorRamp(float grayscale, vec3 color1, vec3 color2, vec3 color3, vec3 color4) {
    if (grayscale < 0.33) {
        return mix(color1, color2, grayscale * 3.0);
    } else if (grayscale < 0.66) {
        return mix(color2, color3, (grayscale - 0.33) * 3.0);
    } else {
        return mix(color3, color4, (grayscale - 0.66) * 3.0);
    }
}

vec2 hash2(vec2 p) {
    return fract(sin(vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)))) * 43758.5453);
}

float noise2D(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);

    vec2 u = f * f * (3.0 - 2.0 * f);
    float n = mix(
        mix(dot(hash2(i + vec2(0.0, 0.0)), f - vec2(0.0, 0.0)),
            dot(hash2(i + vec2(1.0, 0.0)), f - vec2(1.0, 0.0)), u.x),
        mix(dot(hash2(i + vec2(0.0, 1.0)), f - vec2(0.0, 1.0)),
            dot(hash2(i + vec2(1.0, 1.0)), f - vec2(1.0, 1.0)), u.x),
        u.y
    );

    return 0.5 + 0.5 * n;
}

float sharpRing(vec3 decomposed, float time) {
    float ringStart = 1.0;
    float ringWidth = 0.3;
    float noiseScale = 5.0;

    float noise = mix(
        noise2D(vec2(decomposed.x, time) * noiseScale),
        noise2D(vec2(decomposed.y, time) * noiseScale),
        decomposed.z
    );

    noise = (noise - 0.5) * 2.5;

    return ringStart + noise * ringWidth * 1.5;
}

float smoothRing(vec3 decomposed, float time) {
    float ringStart = 0.9;
    float ringWidth = 0.2;
    float noiseScale = 6.0;

    float noise = mix(
        noise2D(vec2(decomposed.x, time) * noiseScale),
        noise2D(vec2(decomposed.y, time) * noiseScale),
        decomposed.z
    );

    noise = (noise - 0.5) * 5.0;

    return ringStart + noise * ringWidth;
}

float flow(vec3 decomposed, float time) {
    return mix(
        texture(uPerlinTexture, vec2(time, decomposed.x / 2.0)).r,
        texture(uPerlinTexture, vec2(time, decomposed.y / 2.0)).r,
        decomposed.z
    );
}

void main() {
    vec2 uv = vUv * 2.0 - 1.0;

    float radius = length(uv);
    float theta = atan(uv.y, uv.x);
    if (theta < 0.0) theta += 2.0 * PI;

    vec3 decomposed = vec3(
        theta / (2.0 * PI),
        mod(theta / (2.0 * PI) + 0.5, 1.0) + 1.0,
        abs(theta / PI - 1.0)
    );

    float noise = flow(decomposed, radius * 0.03 - uAnimation * 0.2) - 0.5;
    theta += noise * mix(0.08, 0.25, uOutputVolume);

    vec4 color = vec4(1.0, 1.0, 1.0, 1.0);

    float originalCenters[7] = float[7](0.0, 0.5 * PI, 1.0 * PI, 1.5 * PI, 2.0 * PI, 2.5 * PI, 3.0 * PI);

    float centers[7];
    for (int i = 0; i < 7; i++) {
        centers[i] = originalCenters[i] + 0.5 * sin(uTime / 20.0 + uOffsets[i]);
    }

    float a, b;
    vec4 ovalColor;

    for (int i = 0; i < 7; i++) {
        float noise = texture(uPerlinTexture, vec2(mod(centers[i] + uTime * 0.05, 1.0), 0.5)).r;
        a = 0.5 + noise * 0.3;
        // Idle (uInputVolume ≈ 0) gets a slightly taller oval so the orb
        // reads as "softly filled" rather than thin petals; talking/listening
        // (high input) shrinks back to the ElevenLabs default.
        b = noise * mix(3.7, 2.5, uInputVolume);
        bool reverseGradient = (i % 2 == 1);

        float distTheta = min(
            abs(theta - centers[i]),
            min(
                abs(theta + 2.0 * PI - centers[i]),
                abs(theta - 2.0 * PI - centers[i])
            )
        );
        float distRadius = radius;

        float softness = 0.6;

        if (drawOval(vec2(distTheta, distRadius), vec2(0.0, 0.0), a, b, reverseGradient, softness, ovalColor)) {
            color.rgb = mix(color.rgb, ovalColor.rgb, ovalColor.a);
            color.a = max(color.a, ovalColor.a);
        }
    }

    float ringRadius1 = sharpRing(decomposed, uTime * 0.1);
    float ringRadius2 = smoothRing(decomposed, uTime * 0.1);

    float inputRadius1 = radius + uInputVolume * 0.2;
    float inputRadius2 = radius + uInputVolume * 0.15;
    float opacity1 = mix(0.2, 0.6, uInputVolume);
    float opacity2 = mix(0.15, 0.45, uInputVolume);

    float ringAlpha1 = (inputRadius2 >= ringRadius1) ? opacity1 : 0.0;
    float ringAlpha2 = smoothstep(ringRadius2 - 0.05, ringRadius2 + 0.05, inputRadius1) * opacity2;

    float totalRingAlpha = max(ringAlpha1, ringAlpha2);

    vec3 ringColor = vec3(1.0);
    color.rgb = 1.0 - (1.0 - color.rgb) * (1.0 - ringColor * totalRingAlpha);

    // The "gap" extreme of the ramp is locked to the surrounding canvas
    // color so the orb's empty regions blend seamlessly with the wrapper bg
    // in both light and dark themes — no hard pie-slice wedges.
    //   uInverted=0 (light): gaps map to color4 = canvas; accent = pure black
    //   uInverted=1 (dark):  gaps map to color1 = canvas; accent = pure white
    //
    // For the mid-tone color stops we sample the agent palette at this
    // pixel's angle. With one agent the array is filled with a single pair
    // (so behavior is unchanged); with N agents the orb is divided into N
    // angular wedges with smooth blending between adjacent agents — every
    // selected agent's color is visible inside the same animated orb.
    float wedgeCount = float(max(uAgentColorCount, 1));
    float scaledAngle = (theta / (2.0 * PI)) * wedgeCount;
    float idx1f = mod(floor(scaledAngle), wedgeCount);
    float idx2f = mod(idx1f + 1.0, wedgeCount);
    int idx1 = int(idx1f);
    int idx2 = int(idx2f);
    float wedgeT = smoothstep(0.0, 1.0, fract(scaledAngle));
    vec3 wedgeLight = mix(uAgentColorsLight[idx1], uAgentColorsLight[idx2], wedgeT);
    vec3 wedgeDark = mix(uAgentColorsDark[idx1], uAgentColorsDark[idx2], wedgeT);

    vec3 color1 = mix(vec3(0.0), uCanvasBg, uInverted);
    vec3 color2 = wedgeLight;
    vec3 color3 = wedgeDark;
    vec3 color4 = mix(uCanvasBg, vec3(1.0), uInverted);

    float luminance = mix(color.r, 1.0 - color.r, uInverted);
    color.rgb = colorRamp(luminance, color1, color2, color3, color4);

    color.a *= uOpacity;

    gl_FragColor = color;
}
`;
