"use client";

import { useAppI18n } from "@/hooks/use-app-i18n";

export function TourProgress({
  current,
  total,
}: {
  current: number;
  total: number;
}) {
  const { t } = useAppI18n();

  if (current <= 0 || total <= 0) {
    return (
      <span className="tour-coachmark__progress">
        {t("tour.progress.start")}
      </span>
    );
  }

  return (
    <span className="tour-coachmark__progress">
      {t("tour.progress.value", { current, total })}
    </span>
  );
}
