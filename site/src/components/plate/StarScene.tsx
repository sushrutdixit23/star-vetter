"use client";

import { useEffect, useRef } from "react";

// The two stars as a plasma surface, drawn by one WebGL fragment shader
// (no 3D library: the whole scene is two discs, so a fullscreen quad is
// enough). Each star is a sphere: limb darkening (bright centre, darker and
// redder rim), and a boiling granulation pattern (animated 3D cellular
// noise wrapped on the sphere, so granules shrink toward the limb the way
// they do on a real star). Colour follows the temperature the caller passes;
// granule contrast also rises with temperature, which is the real trend.
//
// What is real and what is not: the colour (temperature), the sizes, the
// positions and the glow brightness come from the data. The granule pattern
// itself is a generic texture - it is NOT a measurement of this star's surface.
//
// Everything degrades gracefully: no WebGL, a lost context or a shader that
// fails to compile reports "fail" and the caller keeps the SVG stars.

export interface SceneStar {
  cx: number;
  cy: number;
  r: number;
  dim: number;
  color: [number, number, number];
  edge: [number, number, number];
  glow: number;
  contrast: number;
  // unit vector from this star towards the other (x right, y down, z at viewer)
  axis: [number, number, number];
  // tidal stretch along the axis (0 = sphere): long axis = 1+e, short = 1/sqrt(1+e)
  elong: number;
  // extra brightness of the face turned toward the other star (0 = none)
  heat: number;
}

export type SceneStatus = "pending" | "ok" | "fail";

export const VIEW_W = 320;
export const VIEW_H = 160;

const VERT = `
attribute vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

const FRAG = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform vec2 uRes;
uniform float uTime;
uniform float uRad;
uniform float uFront;
uniform vec4 uS0;
uniform vec4 uS1;
uniform vec3 uC0;
uniform vec3 uE0;
uniform vec3 uC1;
uniform vec3 uE1;
uniform vec2 uGl;
uniform vec2 uCon;
uniform vec4 uA0;
uniform vec4 uA1;
uniform vec2 uHt;

vec3 hash33(vec3 p3) {
  p3 = fract(p3 * vec3(0.1031, 0.1030, 0.0973));
  p3 += dot(p3, p3.yxz + 33.33);
  return fract((p3.xxy + p3.yxx) * p3.zyx);
}

float worley(vec3 p, float t) {
  vec3 i = floor(p);
  vec3 f = fract(p);
  float d = 8.0;
  for (int x = -1; x <= 1; x++) {
    for (int y = -1; y <= 1; y++) {
      for (int z = -1; z <= 1; z++) {
        vec3 g = vec3(float(x), float(y), float(z));
        vec3 h = hash33(i + g);
        vec3 o = 0.5 + 0.42 * sin(t * (0.35 + 0.6 * h.zxy) + 6.2831 * h);
        vec3 r = g + o - f;
        d = min(d, dot(r, r));
      }
    }
  }
  return sqrt(d);
}

// Premultiplied RGBA of one star (halo + disc) at viewBox position p. The star
// is an ellipsoid stretched along "ax.xyz" by "ax.w" (0 = a sphere), seen
// orthographically from +z: solve P.M.P = 1 along the line of sight.
vec4 star(vec2 p, vec4 s, vec3 c0, vec3 e0, float gl, float contrast, float seed, vec4 ax, float heat) {
  float d = length(p - s.xy);
  float r = s.z;
  float dim = s.w;
  float glowAmt = clamp(max(dim, 0.12) * uRad, 0.0, 1.0);

  float bloom = pow(clamp(1.0 - d / (r * 3.8 * gl), 0.0, 1.0), 2.2) * 0.75;
  float haze = pow(clamp(1.0 - d / (r * 6.5 * gl), 0.0, 1.0), 2.0) * 0.22;
  float corona = (1.0 - smoothstep(r, r * 1.45, d)) * 0.5;
  float h = (bloom + haze + corona) * glowAmt;
  vec3 haloRgb = mix(c0, vec3(1.0), 0.25) * h;
  vec4 outc = vec4(haloRgb, h * 0.4);

  float aa = (${VIEW_W}.0 / uRes.x) * 1.2;
  vec2 q = (p - s.xy) / r;
  vec3 u = ax.xyz;
  float m = 1.0 + ax.w;
  float k = 1.0 / ((1.0 + ax.w) * (1.0 + ax.w)) - m;
  float uq = u.x * q.x + u.y * q.y;
  float qa = m + k * u.z * u.z;
  float qb = k * u.z * uq;
  float qc = m * dot(q, q) + k * uq * uq - 1.0;
  float disc = qb * qb - qa * qc;
  float dd = disc / (2.0 * qa) * r;
  float cov = smoothstep(-0.4 * aa, aa, dd);
  if (cov > 0.0) {
    float z = (-qb + sqrt(max(disc, 0.0))) / qa;
    vec3 P = vec3(q, z);
    vec3 N = normalize(m * P + k * u * dot(u, P));
    float mu = clamp(N.z, 0.0, 1.0);
    vec3 n = vec3(P.x, -P.y, P.z);
    float ang = uTime * 0.035 + seed * 6.0;
    float ca = cos(ang);
    float sa = sin(ang);
    n = vec3(ca * n.x + sa * n.z, n.y, -sa * n.x + ca * n.z);

    float gran = 1.0;
    if (r > 2.5) {
      float f1 = worley(n * 7.0 + seed * 13.0, uTime);
      float f2 = worley(n * 17.0 + seed * 5.0, uTime * 1.7);
      float lanes = (0.5 - f1) * 1.7 + (0.5 - f2) * 0.8;
      gran = 1.0 + contrast * lanes * (0.35 + 0.65 * mu);
    }

    float lm = 1.0 - mu;
    float ld = 1.0 - 0.58 * lm - 0.14 * lm * lm;
    vec3 col = mix(e0, c0, pow(mu, 0.55));
    col = mix(col, vec3(1.0), 0.22 * pow(mu, 4.0));
    float hot = heat * max(dot(N, u), 0.0);
    col = mix(col, vec3(1.0, 0.93, 0.8), min(hot, 1.0) * 0.35);
    col *= (1.0 + hot) * ld * gran * mix(0.6, 1.0, clamp(uRad, 0.0, 1.0));
    col *= 1.12 * (1.0 - (1.0 - dim) * 0.7);
    col = min(col, vec3(1.0));
    outc = vec4(col * cov, cov) + outc * (1.0 - cov);
  }
  return outc;
}

void main() {
  vec2 p = vec2(gl_FragCoord.x / uRes.x * ${VIEW_W}.0, (1.0 - gl_FragCoord.y / uRes.y) * ${VIEW_H}.0);
  vec4 a = star(p, uS0, uC0, uE0, uGl.x, uCon.x, 0.17, uA0, uHt.x);
  vec4 b = star(p, uS1, uC1, uE1, uGl.y, uCon.y, 0.61, uA1, uHt.y);
  vec4 back = uFront > 0.5 ? a : b;
  vec4 front = uFront > 0.5 ? b : a;
  vec4 col = front + back * (1.0 - front.a);
  float edge = smoothstep(0.0, 18.0, min(min(p.x, ${VIEW_W}.0 - p.x), min(p.y, ${VIEW_H}.0 - p.y)));
  gl_FragColor = mix(col * edge, col, step(0.5, col.a));
}
`;

function compile(gl: WebGLRenderingContext, type: number, src: string): WebGLShader | null {
  const sh = gl.createShader(type);
  if (!sh) return null;
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    gl.deleteShader(sh);
    return null;
  }
  return sh;
}

interface SceneProps {
  primary: SceneStar;
  companion: SceneStar;
  companionFront: boolean;
  radiance: number;
}

export default function StarScene({ primary, companion, companionFront, radiance, onStatus, className = "" }: SceneProps & { onStatus: (s: SceneStatus) => void; className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const propsRef = useRef<SceneProps>({ primary, companion, companionFront, radiance });
  const dirtyRef = useRef(true);
  const statusRef = useRef(onStatus);

  useEffect(() => {
    propsRef.current = { primary, companion, companionFront, radiance };
    dirtyRef.current = true;
    statusRef.current = onStatus;
  });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", { alpha: true, premultipliedAlpha: true, antialias: false, powerPreference: "low-power" }) as WebGLRenderingContext | null;
    if (!gl) {
      statusRef.current("fail");
      return;
    }
    const vs = compile(gl, gl.VERTEX_SHADER, VERT);
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG);
    const prog = vs && fs ? gl.createProgram() : null;
    if (!prog || !vs || !fs) {
      statusRef.current("fail");
      return;
    }
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      statusRef.current("fail");
      return;
    }
    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "aPos");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    gl.disable(gl.BLEND);
    gl.clearColor(0, 0, 0, 0);

    const U = (n: string) => gl.getUniformLocation(prog, n);
    const uRes = U("uRes");
    const uTime = U("uTime");
    const uRad = U("uRad");
    const uFront = U("uFront");
    const uS0 = U("uS0");
    const uS1 = U("uS1");
    const uC0 = U("uC0");
    const uE0 = U("uE0");
    const uC1 = U("uC1");
    const uE1 = U("uE1");
    const uGl = U("uGl");
    const uCon = U("uCon");
    const uA0 = U("uA0");
    const uA1 = U("uA1");
    const uHt = U("uHt");

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let visible = true;
    let lost = false;
    let raf = 0;
    let w = 0;
    let h = 0;
    const t0 = performance.now();

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const cw = Math.max(1, Math.round(canvas.clientWidth * dpr));
      const ch = Math.max(1, Math.round(canvas.clientHeight * dpr));
      if (cw !== w || ch !== h) {
        w = cw;
        h = ch;
        canvas.width = w;
        canvas.height = h;
        gl.viewport(0, 0, w, h);
        dirtyRef.current = true;
      }
    };

    const draw = () => {
      resize();
      const p = propsRef.current;
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform2f(uRes, w, h);
      gl.uniform1f(uTime, reduce ? 0 : (performance.now() - t0) / 1000);
      gl.uniform1f(uRad, p.radiance);
      gl.uniform1f(uFront, p.companionFront ? 1 : 0);
      gl.uniform4f(uS0, p.primary.cx, p.primary.cy, p.primary.r, p.primary.dim);
      gl.uniform4f(uS1, p.companion.cx, p.companion.cy, p.companion.r, p.companion.dim);
      gl.uniform3fv(uC0, p.primary.color);
      gl.uniform3fv(uE0, p.primary.edge);
      gl.uniform3fv(uC1, p.companion.color);
      gl.uniform3fv(uE1, p.companion.edge);
      gl.uniform2f(uGl, p.primary.glow, p.companion.glow);
      gl.uniform2f(uCon, p.primary.contrast, p.companion.contrast);
      gl.uniform4f(uA0, p.primary.axis[0], p.primary.axis[1], p.primary.axis[2], p.primary.elong);
      gl.uniform4f(uA1, p.companion.axis[0], p.companion.axis[1], p.companion.axis[2], p.companion.elong);
      gl.uniform2f(uHt, p.primary.heat, p.companion.heat);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };

    const tick = () => {
      raf = requestAnimationFrame(tick);
      if (lost || !visible || document.hidden) return;
      if (reduce && !dirtyRef.current) return;
      dirtyRef.current = false;
      draw();
    };

    const onLost = (ev: Event) => {
      ev.preventDefault();
      lost = true;
      statusRef.current("fail");
    };
    canvas.addEventListener("webglcontextlost", onLost);

    const io = new IntersectionObserver((entries) => {
      visible = entries.some((en) => en.isIntersecting);
    });
    io.observe(canvas);
    const ro = new ResizeObserver(() => {
      dirtyRef.current = true;
    });
    ro.observe(canvas);

    draw();
    statusRef.current("ok");
    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      ro.disconnect();
      canvas.removeEventListener("webglcontextlost", onLost);
    };
  }, []);

  return <canvas ref={canvasRef} className={className} aria-hidden="true" />;
}
