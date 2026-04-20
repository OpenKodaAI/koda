"use client";

import type { ReactNode } from "react";
import { LanguageSwitcher } from "@/components/layout/language-switcher";
import { ThemeSwitcher } from "@/components/layout/theme-switcher";
import { GooeyFilter } from "@/components/ui/gooey-filter";
import { PixelTrail } from "@/components/ui/pixel-trail";
import { useScreenSize } from "@/hooks/use-screen-size";
import { cn } from "@/lib/utils";

interface SetupFrameProps {
  children: ReactNode;
  top?: ReactNode;
  className?: string;
}

export function SetupFrame({ children, top, className }: SetupFrameProps) {
  const screenSize = useScreenSize();
  const pixelSize = screenSize.lessThan("md") ? 28 : 40;

  return (
    <div
      className={cn(
        "relative flex min-h-[100dvh] w-full flex-col overflow-hidden bg-[var(--canvas)] text-[var(--text-primary)]",
        className,
      )}
    >
      {/* Ambient gooey + pixel-trail background — cursor reveals liquid pixel blobs.
          Sits on z-0, accepts pointer events so mousemove reaches it. The form and
          header sit above on z-10 with pointer-events-auto only on interactive islands,
          so the trail receives cursor moves across the empty canvas. */}
      <GooeyFilter id="setup-gooey-trail" strength={6} />
      <div
        className="pointer-events-auto absolute inset-0 z-0 motion-reduce:hidden"
        aria-hidden="true"
        style={{ filter: "url(#setup-gooey-trail)" }}
      >
        <PixelTrail
          pixelSize={pixelSize}
          fadeDuration={900}
          delay={120}
          pixelClassName="bg-[var(--accent)]"
        />
      </div>

      {/* Soft edge fade that blends the trail into the canvas at the borders.
          Uses --canvas so it works in both dark and light themes without color banding. */}
      <div
        className="pointer-events-none absolute inset-0 z-[1]"
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 0%, transparent 45%, var(--canvas) 95%)",
        }}
        aria-hidden="true"
      />

      <header className="relative z-10 flex h-14 shrink-0 items-center justify-end px-5 pointer-events-none">
        <div className="pointer-events-auto flex items-center gap-2">
          <LanguageSwitcher className="shrink-0" />
          <ThemeSwitcher className="shrink-0" />
        </div>
      </header>

      <main className="relative z-10 flex flex-1 flex-col items-center justify-center px-5 pb-16 pointer-events-none">
        <div className="pointer-events-auto flex w-full max-w-[440px] flex-col items-stretch gap-8">
          {top}
          <div className="min-h-[300px]">{children}</div>
        </div>
      </main>
    </div>
  );
}
