"use client";

import { KodaMark } from "@/components/layout/koda-mark";
import { SetupFrame } from "@/components/setup/setup-frame";
import { InlineAlert } from "@/components/ui/inline-alert";
import { useAppI18n } from "@/hooks/use-app-i18n";

interface InsecureTransportScreenProps {
  /** The plain-HTTP origin the browser used, e.g. `http://192.168.1.10:3000`. */
  origin: string;
}

/**
 * Shown by /login, /setup and /forgot-password instead of their forms when the
 * browser reached the dashboard over plain HTTP from a non-loopback host. The
 * session cookies are Secure there, so the browser would drop them and every
 * sign-in would end back on /setup (J-14), and a recovery code would cross the
 * network in clear text. Nothing here submits.
 */
export function InsecureTransportScreen({ origin }: InsecureTransportScreenProps) {
  const { t } = useAppI18n();

  return (
    <SetupFrame>
      <div className="auth-form">
        <div className="auth-form__hero">
          <KodaMark className="auth-form__logo" />
          <div className="auth-form__title-block">
            <h1 className="auth-form__title">{t("auth.insecure_transport.title")}</h1>
            <p className="auth-form__subtitle">
              {t("auth.insecure_transport.subtitle", { origin })}
            </p>
          </div>
        </div>

        <InlineAlert tone="warning">{t("auth.insecure_transport.reason")}</InlineAlert>

        <ul className="flex flex-col gap-2 pl-4 text-[0.8125rem] leading-relaxed text-[var(--text-secondary)] list-disc">
          <li>{t("auth.insecure_transport.fix_proxy")}</li>
          <li>{t("auth.insecure_transport.fix_localhost")}</li>
        </ul>
      </div>
    </SetupFrame>
  );
}
