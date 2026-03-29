import Image from "next/image";
import { cn } from "@/lib/utils";

interface KodaMarkProps {
  className?: string;
  title?: string;
}

export function KodaMark({ className, title }: KodaMarkProps) {
  return (
    <Image
      src="/koda-mark-white.svg"
      alt={title ?? "Koda"}
      width={40}
      height={40}
      className={cn("object-contain", className)}
      priority
    />
  );
}
