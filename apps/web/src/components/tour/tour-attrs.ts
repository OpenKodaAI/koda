import type { TourVariant } from "@/lib/tour";

export function tourAnchor(anchor: string) {
  return { "data-tour-anchor": anchor } as const;
}

export function tourRoute(route: string, variant: TourVariant = "default") {
  return {
    "data-tour-route": route,
    "data-tour-variant": variant,
  } as const;
}
