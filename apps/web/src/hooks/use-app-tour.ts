"use client";

import { useContext } from "react";
import { AppTourContext } from "@/components/providers/app-tour-provider";

export function useAppTour() {
  const context = useContext(AppTourContext);

  if (!context) {
    throw new Error("useAppTour must be used within AppTourProvider");
  }

  return context;
}
