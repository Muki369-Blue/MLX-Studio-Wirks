"use client";

import { useState, useRef, useCallback } from "react";

function isAnimatedFile(path: string): boolean {
  const lower = path.toLowerCase();
  return lower.endsWith(".gif") || lower.endsWith(".webp");
}

export default function AnimatedPreview({
  src,
  alt,
  filePath,
  className,
  onClick,
}: {
  src: string;
  alt: string;
  filePath: string;
  className?: string;
  onClick?: (e: React.MouseEvent) => void;
}) {
  const [playing, setPlaying] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const capturedRef = useRef(false);

  const animated = isAnimatedFile(filePath);

  const captureFrame = useCallback(() => {
    if (capturedRef.current) return;
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (!img || !canvas || img.naturalWidth === 0) return;
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.drawImage(img, 0, 0);
      capturedRef.current = true;
    }
  }, []);

  if (!animated) {
    return <img src={src} alt={alt} className={className} loading="lazy" onClick={onClick} />;
  }

  return (
    <div
      className="relative w-full h-full cursor-pointer group"
      onClick={(e) => {
        if (onClick) {
          onClick(e);
        } else {
          setPlaying((p) => !p);
        }
      }}
      onMouseEnter={() => !onClick && setPlaying(true)}
      onMouseLeave={() => !onClick && setPlaying(false)}
    >
      {/* Hidden img to capture first frame */}
      <img
        ref={imgRef}
        src={src}
        alt=""
        className="hidden"
        onLoad={captureFrame}
      />

      {/* Static first frame (canvas) — shown when paused */}
      <canvas
        ref={canvasRef}
        className={`${className} ${playing ? "hidden" : "block"}`}
      />

      {/* Animated image — only rendered when playing */}
      {playing && (
        <img src={src} alt={alt} className={className} />
      )}

      {/* Play/Pause overlay */}
      {!playing && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/30 group-hover:bg-black/20 transition-colors">
          <div className="w-10 h-10 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center">
            <span className="text-white text-lg ml-0.5">▶</span>
          </div>
        </div>
      )}
      {playing && (
        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
          <div className="w-6 h-6 rounded-full bg-black/50 flex items-center justify-center">
            <span className="text-white text-xs">⏸</span>
          </div>
        </div>
      )}
    </div>
  );
}
