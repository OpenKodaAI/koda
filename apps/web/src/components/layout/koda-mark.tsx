import Image from "next/image";
import { cn } from "@/lib/utils";

interface KodaMarkProps {
  className?: string;
  title?: string;
  /** Beside a visible or aria-label "Koda", the mark adds nothing to the name (axe image-redundant-alt). */
  decorative?: boolean;
}

export function KodaMark({ className, title, decorative = false }: KodaMarkProps) {
  return (
    <Image
      src="/koda-mark-white.svg"
      alt={decorative ? "" : (title ?? "Koda")}
      width={40}
      height={40}
      className={cn("koda-mark object-contain", className)}
      priority
    />
  );
}
